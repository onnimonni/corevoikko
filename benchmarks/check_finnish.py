"""Offline Finnish checker and span-scored accuracy benchmark using upstream bindings."""
import argparse
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libvoikko/python"))
sys.path.insert(0, str(ROOT / "benchmarks"))
from libvoikko import Token, Voikko  # noqa: E402
from name_filter import TRADE_REGISTER_FORMS, NameFilter  # noqa: E402

# Schemeless domain, optionally with a hyphen-attached Finnish ending:
# kela.fi, Suomi.fi-tunnisteella. Restricted to common TLDs so a missing space
# after a full stop (kissa.koira) is still checked as a word.
DOMAIN = re.compile(r"(?i)^(?:[a-z0-9][a-z0-9-]*\.)+(?:fi|ax|eu|se|ee|no|dk|com|org|net|info|io|gov|edu)"
                    r"(?:-(?P<suffix>\w+))?$")


# Schemeless web address with a path: www.tietosuoja.fi/fi/index/yhteystiedot.html.
# The tokenizer splits it at "/", so its parts are excluded from spelling.
URL_PATH = re.compile(r"(?i)(?<![\w@.])(?:[a-z0-9][a-z0-9-]*\.)+(?:fi|ax|eu|se|ee|no|dk|com|org|net|info|io|gov|edu)"
                      r"/[^\s,;)\]”\"]*")
# Unknown capitalized name + hyphen + Finnish word: Kanta-palvelujen, Paytrail-tietosuojaseloste.
NAME_COMPOUND = re.compile(r"^[A-ZÅÄÖ][\w]*-(?P<suffix>[a-zåäö]\w*)$")
# A capitalized word mid-sentence directly before the compound: "käyttää Google Analytics-palvelua".
MULTIWORD_NAME_BEFORE = re.compile(r"(?<=[\w,] )(?P<prev>[A-ZÅÄÖ]\w*) $")
# Capitalized words followed by a company form: "Storia Oy", "CONCOCONNENTE Oy:lle".
_FORMS = "|".join(sorted(TRADE_REGISTER_FORMS, key=len, reverse=True))
COMPANY_MENTION = re.compile(r"(?P<name>(?:[A-ZÅÄÖ0-9][\w&'’.-]*[ ]){1,6})(?P<form>(?i:" + _FORMS + r"))(?::\w+)?(?![\w])")


def _domain_valid(checker, word):
    match = DOMAIN.match(word)
    return bool(match) and (match.group("suffix") is None or checker.spell(match.group("suffix")))


COMPOUND_INDEX = ROOT / "benchmarks/data/established_compounds.json.gz"
_SEGMENT = re.compile(r"\+([^+(]+)\(([^)]*)\)")
_established = None


def compound_readings(checker, word):
    """Per analysis: (first-part base, rest of base form, first-part surface), or
    None when that analysis has fewer than two lexical parts (a single lexeme or
    a derivation). Compound analyses whose first part is itself derived
    (myy+nti+edistäjä) are omitted: they neither block nor support a reading.
    Proper-name readings (Kansakorkeakoulu) are omitted for lowercase words."""
    readings = []
    for analysis in checker.analyze(word):
        if word[:1].islower() and analysis.get("CLASS") == "nimi":
            continue
        segments = _SEGMENT.findall(analysis.get("WORDBASES", ""))
        base = analysis.get("BASEFORM", "").lower()
        if sum(not s[1].startswith("+") for s in segments) < 2:
            readings.append(None)
        elif not segments[1][1].startswith("+"):
            surface, first_base = segments[0][0].lower(), segments[0][1].lower()
            readings.append((first_base, base[len(surface):], surface) if base.startswith(surface) else None)
    return readings


def _is_linking_form(checker, surface, first_base):
    """True if surface is the plain nominative or genitive singular of first_base
    (not e.g. a comparative: suurempi-, kauniimman-)."""
    return any(a.get("BASEFORM", "").lower() == first_base and a.get("NUMBER") == "singular"
               and a.get("SIJAMUOTO") in ("nimento", "omanto") and a.get("COMPARISON") in (None, "positive")
               for a in checker.analyze(surface))


def _established_index():
    global _established
    if _established is None:
        _established = json.loads(gzip.decompress(COMPOUND_INDEX.read_bytes()))["compounds"]
    return _established


def _is_established_compound(checker, word):
    """word (lowercase) is a listed compound with exactly this linking form:
    henkilötiedot, tietosuoja; not kantapalvelut."""
    index = _established_index()
    return any(reading and reading[2] in index.get(f"{reading[0]}|{reading[1]}", ())
               for reading in compound_readings(checker, word))


def established_compound_suggestions(checker, word):
    """Suggest the established linking form when every reading of a compound
    uses a nominative/genitive first part that no established compound with the
    same parts uses: asiakkaansuhteen -> asiakassuhteen, rekisteripitäjän ->
    rekisterinpitäjän. Compounds absent from the index are never flagged.
    Known risk: both linkings valid but only one listed (miehenkuva/mieskuva)."""
    _established = _established_index()
    readings = compound_readings(checker, word)
    if not readings or None in readings or "'" in word or "’" in word:
        return []
    suggestions = set()
    for first_base, rest, surface in readings:
        # The word itself may be a listed non-lemma headword (maateitse).
        if surface in _established.get(f"{first_base}|{word.lower()[len(surface):]}", ()):
            return []
        forms = _established.get(f"{first_base}|{rest}")
        if forms is None:
            continue
        if surface in forms:
            return []
        for form in forms:
            if not (_is_linking_form(checker, surface, first_base) and _is_linking_form(checker, form, first_base)):
                continue
            fixed = form + word[len(surface):].lower()
            suggestions.add(fixed[:1].upper() + fixed[1:] if word[:1].isupper() else fixed)
    return sorted(suggestions)


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


def _capitalized_name(word):
    """Name part of a capitalized, not all-caps word: Storian, Sava-Group -> Sava."""
    name = word.split("-")[0]
    return name if name[:1].isupper() and not name.isupper() and name.isalpha() else None


def _typo_like(checker, word):
    """A spelling suggestion one keystroke away: Sinlla -> Sinulla, Poito -> Poisto."""
    return any(_one_edit_apart(word, s) for s in checker.suggest(word))


def _known_name(checker, word):
    """The optional name filter knows the word as a name, or as a word of a
    multiword name and the word isn't a likely typo of a Finnish word."""
    names = getattr(checker, "_names", None)
    return bool(names) and (names.knows_name(word)
                            or (names.knows_name_word(word) and not _typo_like(checker, word)))


def _name_compound_valid(checker, word):
    """Name + hyphen + Finnish word: Kanta-palvelujen, Paytrail-tietosuojaseloste.
    The Finnish part must spell, and the joined form must not be an established
    compound (Henkilö-tiedot, Tieto-suoja are split common words). The name part
    must spell, be a known name, or be unknown and not one keystroke from a
    known word (Poito-oikeus is a typo of Poisto-)."""
    match = NAME_COMPOUND.match(word)
    if not (match and checker.spell(match.group("suffix"))):
        return False
    name = word.split("-")[0]
    if _is_established_compound(checker, (name + match.group("suffix")).lower()):
        return False
    return checker.spell(name) or _known_name(checker, name) or not _typo_like(checker, name)


def _multiword_name(checker, prev, word):
    """prev + word is a multiword name: prev is a nominative proper noun (Google,
    Microsoft; not genitive Kelan) or the filter knows "prev name"."""
    names = getattr(checker, "_names", None)
    if names and names.knows_full_name(f"{prev} {word.split('-')[0]}"):
        return True
    return not checker.spell(prev) or any(a.get("CLASS") in ("nimi", "etunimi", "sukunimi", "paikannimi")
                                          and a.get("SIJAMUOTO") == "nimento" for a in checker.analyze(prev))


# Default: a register snapshot older than this may miss newly registered companies.
REGISTER_MAX_AGE_DAYS = 30


def _company_diagnostics(checker, text):
    """With a filter built from the PRH register: report "<Name> Oy" mentions
    whose name is not a registered company name. A Bloom filter has no false
    negatives, so an unknown name is certainly absent from the filter's data."""
    names = getattr(checker, "_names", None)
    if not (names and names.covers_finnish_companies):
        return []
    result = []
    for match in COMPANY_MENTION.finditer(text):
        words = match.group("name").split()
        if any(names.knows_company(" ".join(words[i:]), match.group("form")) for i in range(len(words))):
            continue
        start = match.start("name")
        # A sentence-initial common word is not part of the name: "Asiakkaana CONCO Oy".
        if len(words) > 1 and re.search(r"(^|[.!?:]\s+)$", text[:start]) and checker.spell(words[0].lower()):
            start = text.index(words[1], start)
        end = match.end("form")
        as_of = datetime.date.fromisoformat(names.register_date)
        description = (f"Yritystä ei löydy kaupparekisteristä (PRH, tilanne "
                       f"{as_of.day}.{as_of.month}.{as_of.year}): tarkista nimi.")
        age = (datetime.date.today() - as_of).days
        stale = age > getattr(checker, "_register_max_age_days", REGISTER_MAX_AGE_DAYS)
        if stale:
            description += f" Rekisteritieto on {age} päivää vanha: uusi yritys voi puuttua."
        result.append({"kind": "name", "code": None, "start": start, "end": end, "text": text[start:end],
                       "description": description, "as_of": names.register_date,
                       "stale": stale, "suggestions": []})
    return result


def _one_edit_apart(a, b):
    """One insertion, deletion, substitution or adjacent transposition."""
    a, b = a.lower(), b.lower()
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                   and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def apply_document_names(checker, document):
    """Document-level name learning. document: list of (text, diagnostics).

    - "Write in lowercase" (code 6) is dropped for a base form capitalized
      mid-sentence at least twice and never written in lowercase (Kela,
      Kelan, Kelassa), and for a suspended compound part (Digi- ja ...).
    - A capitalized unknown word is accepted as a name when its name part
      recurs among the document's unknown capitalized words, either exactly or
      as a prefix of at least 4 letters (Storia, Storian; Sava, Sava-Group),
      is never written in lowercase, and at least one occurrence has no
      spelling suggestion one keystroke away. A repeated typo (Sinlla x4 ->
      Sinulla) therefore stays reported, as does a single unknown word.
    """
    cache = {}
    capitalized = {}
    names = []  # (name part, occurrence word)
    for text, diags in document:
        for d in diags:
            if d["kind"] == "grammar" and d.get("code") == 6:
                for base in _base_forms(checker, d["text"], cache):
                    capitalized[base] = capitalized.get(base, 0) + 1
            elif d["kind"] == "spelling" and (name := _capitalized_name(d["text"])):
                names.append((name, d["text"]))
        # Accepted name compounds (Paytrail-tietosuojaseloste) are occurrences too.
        for token in checker.tokens(text):
            if (NAME_COMPOUND.match(token.tokenText) and (name := _capitalized_name(token.tokenText))
                    and not checker.spell(name)):
                names.append((name, token.tokenText))
    candidates = {base for base, count in capitalized.items() if count >= 2}
    family = {n: [w for m, w in names if min(len(n), len(m)) >= 4 and (n.startswith(m) or m.startswith(n))]
              for n, _ in names}
    learned = {n for n, words in family.items() if len(words) >= 2 and any(
        not any(_one_edit_apart(w, s) for s in checker.suggest(w)) for w in set(words))}
    if candidates or learned:
        for text, _ in document:
            for token in checker.tokens(text):
                word = token.tokenText
                if token.tokenType == Token.WORD and word[:1].islower():
                    candidates -= _base_forms(checker, word, cache)
                    if word.isalpha():
                        learned = {n for n in learned if not word.startswith(n.lower())}

    def keep(d):
        if d["kind"] == "grammar" and d.get("code") == 6:
            names = getattr(checker, "_names", None)
            return not (d["text"].endswith("-") or _base_forms(checker, d["text"], cache) & candidates
                        or (names and names.knows_name(d["text"])))
        # Learned names only excuse the name itself: not compound-linking
        # findings, and not a typo in a Finnish part after a hyphen
        # (Abitreeni-palveussa); a capitalized part continues the name (Sava-Group).
        if d["kind"] != "spelling" or _capitalized_name(d["text"]) not in learned or checker.spell(d["text"]):
            return True
        _, _, rest = d["text"].partition("-")
        return bool(rest) and not (rest[:1].isupper() or checker.spell(rest))
    return [(text, [d for d in diags if keep(d)]) for text, diags in document]


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
    url_spans = [m.span() for m in URL_PATH.finditer(text)]
    for token in checker.tokens(text):
        word = token.tokenText
        if text[offset:offset + len(word)] != word:
            raise RuntimeError("Tokenizer lost text alignment")
        in_url = any(start <= offset and offset + len(word) <= end for start, end in url_spans)
        # Letterless tokens (Y-tunnus 1234567-8, phone numbers, ISO dates) are
        # identifiers, not words that can be misspelled.
        if token.tokenType == Token.WORD and any(c.isalpha() for c in word) and not in_url:
            valid = (checker.spell(word) or _domain_valid(checker, word)
                     or _name_compound_valid(checker, word)
                     or (any(c.isupper() for c in word) and _known_name(checker, word)))
            if not valid and text[offset + len(word):offset + len(word) + 1] == ".":
                # The default tokenizer leaves abbreviation/date dots separate.
                valid = checker.spell(word + ".")
            if not valid:
                result.append({"kind": "spelling", "start": offset, "end": offset + len(word),
                               "text": word, "suggestions": checker.suggest(word)})
            elif "-" not in word and (fixes := established_compound_suggestions(checker, word)):
                result.append({"kind": "spelling", "start": offset, "end": offset + len(word),
                               "text": word, "suggestions": fixes})
            elif (NAME_COMPOUND.match(word) and not checker.spell(word)
                  and (before := MULTIWORD_NAME_BEFORE.search(text[:offset]))
                  and _multiword_name(checker, before.group("prev"), word)):
                # Kotus: a multiword name takes a space before the hyphen
                # (Google Analytics -palvelu), not Google Analytics-palvelu.
                result.append({"kind": "grammar", "code": 1, "start": offset, "end": offset + len(word),
                               "text": word, "description": "Monisanaisen nimen jälkeen: välilyönti ennen yhdysmerkkiä.",
                               "suggestions": [word.replace("-", " -", 1)]})
        offset += len(word)
    if offset != len(text):
        raise RuntimeError("Tokenizer did not consume the input")
    companies = _company_diagnostics(checker, text)
    # A register finding covers the whole name; drop spelling warnings inside it.
    result = [d for d in result if not (d["kind"] == "spelling" and any(
        c["start"] <= d["start"] and d["end"] <= c["end"] for c in companies))] + companies
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
    parser.add_argument("--names", type=Path,
                        help="Name Bloom filter from build_name_filter.py (company/product names)")
    parser.add_argument("--register-max-age-days", type=int, default=REGISTER_MAX_AGE_DAYS,
                        help="Mark unknown-company findings stale when the PRH snapshot is older (default: %(default)s)")
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
            if args.names:
                checker._names = NameFilter.load(args.names)
                checker._register_max_age_days = args.register_max_age_days
            print(json.dumps(diagnostics(checker, args.text_file.read_bytes().decode("utf-8")), ensure_ascii=False, indent=2))
        else:
            benchmark(checker, args.corpus, args.report, args.dictionary)
    finally:
        checker.terminate()


if __name__ == "__main__":
    main()
