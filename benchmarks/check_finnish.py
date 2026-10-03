"""Offline Finnish checker and span-scored accuracy benchmark using upstream bindings."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libvoikko/python"))
from libvoikko import Token, Voikko  # noqa: E402

# Schemeless domain, optionally with a hyphen-attached Finnish ending:
# kela.fi, Suomi.fi-tunnisteella. Restricted to common TLDs so a missing space
# after a full stop (kissa.koira) is still checked as a word.
DOMAIN = re.compile(r"(?i)^(?:[a-z0-9][a-z0-9-]*\.)+(?:fi|ax|eu|se|ee|no|dk|com|org|net|info|io|gov|edu)"
                    r"(?:-(?P<suffix>\w+))?$")


def _domain_valid(checker, word):
    match = DOMAIN.match(word)
    return bool(match) and (match.group("suffix") is None or checker.spell(match.group("suffix")))


def configure(checker, profile):
    if profile not in {"prose", "title", "list", "message"}:
        raise ValueError(f"Unknown profile: {profile}")
    checker.setIgnoreDot(False)
    checker.setIgnoreNumbers(False)
    checker.setIgnoreUppercase(False)
    checker.setAcceptFirstUppercase(True)
    checker.setAcceptAllUppercase(True)
    checker.setIgnoreNonwords(True)
    checker.setAcceptExtraHyphens(False)
    checker.setAcceptMissingHyphens(False)
    checker.setAcceptTitlesInGc(profile in {"title", "message"})
    checker.setAcceptUnfinishedParagraphsInGc(profile == "message")
    checker.setAcceptBulletedListsInGc(profile == "list")
    checker._finnish_text_profile = profile


def _base_forms(checker, word, cache):
    key = word.lower()
    if key not in cache:
        cache[key] = {a["BASEFORM"].lower() for a in checker.analyze(key) if a.get("BASEFORM")} or {key}
    return cache[key]


def apply_document_names(checker, document):
    """Drop "write in lowercase" (code 6) for words the document consistently
    capitalizes: a base form capitalized mid-sentence at least twice and never
    written in lowercase is a name (Kela, Kelan, Kelassa), not a slip.

    document: list of (text, diagnostics) pairs belonging to one document.
    """
    cache = {}
    capitalized = {}
    for _, diags in document:
        for d in diags:
            if d["kind"] == "grammar" and d.get("code") == 6:
                for base in _base_forms(checker, d["text"], cache):
                    capitalized[base] = capitalized.get(base, 0) + 1
    candidates = {base for base, count in capitalized.items() if count >= 2}
    if candidates:
        for text, _ in document:
            for token in checker.tokens(text):
                word = token.tokenText
                if token.tokenType == Token.WORD and word[:1].islower():
                    candidates -= _base_forms(checker, word, cache)
    return [(text, [d for d in diags if not (
                d["kind"] == "grammar" and d.get("code") == 6
                and _base_forms(checker, d["text"], cache) & candidates)])
            for text, diags in document]

# Closing formulas listed in Kielitoimiston ohjepankki, "Sähköposti, kirje ja
# muut viestit": "Lopputervehdyksen jäljessä ei käytetä pilkkua".
CLOSING_FORMULAS = {
    "terveisin", "ystävällisin terveisin", "yhteistyöterveisin", "lämpimin terveisin",
    "parhain terveisin", "ystävällisesti", "kunnioittavasti", "kunnioittaen", "kiitoksin",
    "monin kiitoksin", "kiittäen", "aurinkoisen kesän toivotuksin",
    "hyvää viikonloppua toivottaen", "lämpimästi", "rakkaudella", "terv.",
}


def _closing_comma_diagnostics(text):
    """Comma after a closing formula on its own line, followed by a name line."""
    result = []
    lines = text.split("\n")
    offset = 0
    for index, raw in enumerate(lines):
        stripped = raw.rstrip("\r").rstrip()
        following = next((l for l in lines[index + 1:] if l.strip()), None)
        if (stripped.endswith(",") and stripped[:-1].strip().casefold() in CLOSING_FORMULAS
                and following is not None):
            start = offset + len(stripped) - 1
            result.append({"kind": "grammar", "code": 4, "start": start, "end": start + 1,
                           "text": ",", "description": "Lopputervehdyksen jäljessä ei käytetä pilkkua.",
                           "suggestions": [""]})
        offset += len(raw) + 1
    return result


def diagnostics(checker, text, document_names=True):
    result = []
    offset = 0
    for token in checker.tokens(text):
        word = token.tokenText
        if text[offset:offset + len(word)] != word:
            raise RuntimeError("Tokenizer lost text alignment")
        # Letterless tokens (Y-tunnus 1234567-8, phone numbers, ISO dates) are
        # identifiers, not words that can be misspelled.
        if token.tokenType == Token.WORD and any(c.isalpha() for c in word):
            valid = checker.spell(word) or _domain_valid(checker, word)
            if not valid and text[offset + len(word):offset + len(word) + 1] == ".":
                # The default tokenizer leaves abbreviation/date dots separate.
                valid = checker.spell(word + ".")
            if not valid:
                result.append({"kind": "spelling", "start": offset, "end": offset + len(word),
                               "text": word, "suggestions": checker.suggest(word)})
        offset += len(word)
    if offset != len(text):
        raise RuntimeError("Tokenizer did not consume the input")
    grammar_text = text
    boundaries = None
    if getattr(checker, "_finnish_text_profile", None) == "message":
        characters = []
        boundaries = [0]
        line_end = None
        for index, character in enumerate(text):
            if character == "\r" and text[index:index + 2] == "\r\n":
                continue
            if character == "\n":
                # A comma-ending line continues the same sentence, not a new paragraph.
                if line_end == ",":
                    character = " "
                line_end = None
            elif character not in " \t":
                line_end = character
            characters.append(character)
            boundaries.append(index + 1)
        grammar_text = "".join(characters)
    for error in checker.grammarErrors(grammar_text, "fi"):
        start, end = error.startPos, error.startPos + error.errorLen
        if not 0 <= start <= end <= len(grammar_text):
            raise RuntimeError("Invalid normalized grammar diagnostic span")
        if boundaries is not None:
            start, end = boundaries[start], boundaries[end]
        if not 0 <= start <= end <= len(text):
            raise RuntimeError("Invalid grammar diagnostic span")
        result.append({"kind": "grammar", "code": error.errorCode, "start": start,
                       "end": end, "text": text[start:end],
                       "description": error.shortDescription,
                       "suggestions": list(error.suggestions)})
    if getattr(checker, "_finnish_text_profile", None) == "message":
        result.extend(_closing_comma_diagnostics(text))
    result = sorted(result, key=lambda d: (d["start"], d["end"], d["kind"]))
    if document_names:
        result = apply_document_names(checker, [(text, result)])[0][1]
    return result


def matches(expected, actual):
    if expected["kind"] != actual["kind"]:
        return False
    if "code" in expected and expected["code"] != actual.get("code"):
        return False
    # An error must locate the annotated error, not just flag the paragraph.
    return expected["start"] == actual["start"] and expected["end"] == actual["end"]


def benchmark(checker, corpus_path, report_path, dictionary_path):
    payload = corpus_path.read_bytes()
    corpus = json.loads(payload)
    ids = set()
    tp = fp = fn = clean = clean_failed = unsupported = unsupported_detected = 0
    correction_hits = correction_total = 0
    results = []
    for case in corpus["cases"]:
        if case["id"] in ids:
            raise ValueError(f"Duplicate case: {case['id']}")
        ids.add(case["id"])
        text = case["text"]
        expected = case["expected"]
        for error in expected:
            if not 0 <= error["start"] < error["end"] <= len(text):
                raise ValueError(f"Bad gold span: {case['id']}")
            if text[error["start"]:error["end"]] != error["text"]:
                raise ValueError(f"Gold text does not match span: {case['id']}")
        configure(checker, case["profile"])
        actual = diagnostics(checker, text)
        unmatched = list(actual)
        missing = []
        detected = []
        for error in expected:
            if case["status"] == "scored" and "correction" in error:
                correction_total += 1
            match = next((d for d in unmatched if matches(error, d)), None)
            if match is None:
                missing.append(error)
            else:
                unmatched.remove(match)
                detected.append(error)
                if case["status"] == "scored" and "correction" in error:
                    correction_hits += error["correction"] in match["suggestions"]
        if case["status"] == "limitation":
            unsupported += len(expected)
            unsupported_detected += len(detected)
            label = "limitation-detected" if not missing else "unsupported-check"
        elif case["status"] == "scored":
            tp += len(detected)
            fp += len(unmatched)
            fn += len(missing)
            if not expected:
                clean += 1
                clean_failed += bool(unmatched)
            labels = (["false-positive"] if unmatched else []) + (["false-negative"] if missing else [])
            label = "+".join(labels) if labels else "pass"
        else:
            raise ValueError(f"Unknown case status: {case['status']}")
        triage = []
        if case["status"] == "limitation":
            triage.append("unsupported-capability" if case["category"] != "input-coverage" else "unsupported-input")
        else:
            if missing:
                triage.append("silent-coverage-bug" if case["category"] == "coverage-boundary" else "missed-supported-error")
            if unmatched:
                triage.append("spelling-integration-or-dictionary-gap" if all(d["kind"] == "spelling" for d in unmatched) else "grammar-false-positive")
        results.append({**case, "label": label, "triage": triage, "actual": actual,
                        "false_positives": unmatched, "missed": missing})
        if label != "pass":
            spans = "; ".join(f"{d['kind']} {d.get('code', '')} [{d['start']}:{d['end']}] {d['text']!r}" for d in actual)
            excerpt = text if len(text) <= 180 else text[:160] + f"... ({len(text)} code points)"
            print(f"FINDING {case['id']} {label}: {excerpt!r} => {spans or 'no diagnostics'}")
    if not clean or not tp + fn:
        raise ValueError("Corpus needs both clean and error-bearing scored cases")
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn)
    metrics = {"quality_loss": 5 * fp + fn, "false_positives": fp, "false_negatives": fn,
               "true_positives": tp, "precision": precision, "recall": recall,
               "clean_cases": clean, "clean_cases_flagged": clean_failed,
               "unsupported_checks": unsupported, "unsupported_detected": unsupported_detected,
               "correction_hits": correction_hits, "correction_opportunities": correction_total,
               "cases": len(results)}
    dictionary_files = dictionary_path / "5/mor-standard"
    metadata = {"library_version": Voikko.getVersion(), "backend": "Finnish VFST",
                "dictionary_variant": "standard",
                "dictionary_sha256": {name: hashlib.sha256((dictionary_files / name).read_bytes()).hexdigest()
                                      for name in ("mor.vfst", "autocorr.vfst", "index.txt")},
                "offsets": "Unicode code points, zero-based half-open",
                "scoring": "5 * false_positives + false_negatives; unsupported checks excluded"}
    report = {"corpus_sha256": hashlib.sha256(payload).hexdigest(), "metadata": metadata,
              "metrics": metrics, "sources": corpus["sources"], "results": results}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"ASI corpus_sha256={report['corpus_sha256']}")
    for name, value in metrics.items():
        print(f"METRIC {name}={value}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--dictionary", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=ROOT / "benchmarks/finnish_cases.json")
    parser.add_argument("--report", type=Path, default=ROOT / ".bench-build/findings.json")
    parser.add_argument("--text-file", type=Path, help="Check a local UTF-8 plain-text document instead of benchmarking")
    parser.add_argument("--profile", choices=["prose", "title", "list", "message"], default="prose")
    args = parser.parse_args()
    # Do not silently load a system libvoikko if the benchmark library is missing.
    library_name = "libvoikko.1.dylib" if sys.platform == "darwin" else "libvoikko.so.1"
    if not (args.library / library_name).is_file():
        raise RuntimeError(f"Built library missing: {args.library / library_name}")
    Voikko.setLibrarySearchPath(str(args.library.resolve()))
    checker = Voikko("fi", path=str(args.dictionary.resolve()))
    try:
        if args.text_file:
            configure(checker, args.profile)
            print(json.dumps(diagnostics(checker, args.text_file.read_bytes().decode("utf-8")), ensure_ascii=False, indent=2))
        else:
            benchmark(checker, args.corpus, args.report, args.dictionary)
    finally:
        checker.terminate()


if __name__ == "__main__":
    main()
