"""Build benchmarks/data/established_compounds.json.gz.

Sources:
- Kotimaisten kielten keskus, Nykysuomen sanalista 2024 (CC BY 4.0),
  https://kaino.kotus.fi/lataa/nykysuomensanalista2024.csv
- Lexicalized compounds (forms containing "=") in voikko-fi/vocabulary/joukahainen.xml.

Each compound is indexed by (first-part base form, rest of base form) -> the
first-part surface forms that established compounds use. The raw word list is
not committed; download it and pass it with --kotus.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from check_finnish import ROOT, Voikko, compound_readings

KOTUS_URL = "https://kaino.kotus.fi/lataa/nykysuomensanalista2024.csv"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kotus", type=Path, required=True, help="downloaded Nykysuomen sanalista TSV")
    parser.add_argument("--library", type=Path, default=ROOT / ".bench-build/library/src/.libs")
    parser.add_argument("--dictionary", type=Path, default=ROOT / ".bench-build/dictionaries")
    parser.add_argument("--out", type=Path, default=ROOT / "benchmarks/data/established_compounds.json.gz")
    args = parser.parse_args()

    raw = args.kotus.read_bytes()
    kotus = [line.split("\t")[0] for line in raw.decode("utf-8").splitlines()[1:]]
    joukahainen = [form.text.replace("=", "") for form in
                   ET.parse(ROOT / "voikko-fi/vocabulary/joukahainen.xml").iter("form")
                   if form.text and "=" in form.text]

    Voikko.setLibrarySearchPath(str(args.library.resolve()))
    checker = Voikko("fi", path=str(args.dictionary.resolve()))
    compounds = {}
    try:
        for word in kotus + joukahainen:
            if not (word.isalpha() and word.islower()):
                continue
            nominative = any(a.get("SIJAMUOTO") == "nimento" for a in checker.analyze(word))
            for reading in compound_readings(checker, word):
                if reading:
                    first_base, rest, surface = reading
                    keys = {rest}
                    if surface + rest != word:
                        # Not its own base form: index its surface; also its base
                        # form only if nominative (luonnonantimet), not for a
                        # lexicalized case form (maateitse, base "maatie").
                        keys = {word[len(surface):]} | ({rest} if nominative else set())
                    for key in keys:
                        compounds.setdefault(f"{first_base}|{key}", set()).add(surface)
    finally:
        checker.terminate()

    index = {
        "sources": [{"name": "Kotus Nykysuomen sanalista 2024", "url": KOTUS_URL, "license": "CC BY 4.0",
                     "sha256": hashlib.sha256(raw).hexdigest()},
                    {"name": "voikko-fi joukahainen.xml lexicalized compounds"}],
        "compounds": {key: sorted(forms) for key, forms in sorted(compounds.items())},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    args.out.write_bytes(gzip.compress(payload, mtime=0))
    print(f"{len(compounds)} compound keys -> {args.out} ({args.out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
