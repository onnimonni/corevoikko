"""Build a name Bloom filter from documented sources.

Sources (fetch them yourself; nothing here downloads data):

  prh       Finnish Patent and Registration Office (PRH), YTJ open data:
            all companies on the Trade Register, current names incl. parallel and
            auxiliary names.  CC BY 4.0.
            curl -L -o prh.zip https://avoindata.prh.fi/opendata-ytj-api/v3/all_companies
  wikidata  Wikidata labels and aliases of software, online/web services, apps,
            software and technology companies (fi, sv, en).  CC0.
            curl -G https://query.wikidata.org/sparql -H 'Accept: text/tab-separated-values' \\
                 --data-urlencode query@benchmarks/data/name_sources_wikidata.rq -o wikidata.tsv
  botocore  AWS service names (metadata.serviceFullName / serviceAbbreviation)
            from boto/botocore data/*/*/service-2.json.  Apache-2.0.
            git clone --depth 1 https://github.com/boto/botocore
  seed      Hand-collected names, one "name<TAB>kind<TAB>source URL" per line.

Example:
  python benchmarks/build_name_filter.py --prh prh.zip --wikidata wikidata.tsv \\
      --botocore botocore/botocore/data --seed benchmarks/data/name_seed.tsv --out names.bloom
"""
import argparse
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import zipfile

from name_filter import NameFilter

SOURCES = {
    "prh": {"name": "PRH YTJ open data, all companies",
            "url": "https://avoindata.prh.fi/opendata-ytj-api/v3/all_companies",
            "license": "CC BY 4.0", "attribution": "Patentti- ja rekisterihallitus (PRH)"},
    "wikidata": {"name": "Wikidata software, services and technology companies",
                 "url": "https://query.wikidata.org/sparql", "license": "CC0 1.0"},
    "botocore": {"name": "AWS service names from botocore",
                 "url": "https://github.com/boto/botocore", "license": "Apache-2.0"},
    "seed": {"name": "Hand-collected seed list (benchmarks/data/name_seed.tsv)", "license": "see per-row source"},
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prh_names(path):
    """Current names (version 1, no end date) of every company in the PRH bulk file.
    Accepts the downloaded ZIP or the JSON inside it; the JSON may be a list of
    companies or an object with a "companies" list (API search responses)."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            member = next(n for n in archive.namelist() if n.endswith(".json"))
            data = json.load(io.TextIOWrapper(archive.open(member), encoding="utf-8"))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    companies = data["companies"] if isinstance(data, dict) else data
    names = []
    for company in companies:
        for entry in company.get("names", []):
            if entry.get("version", 1) == 1 and not entry.get("endDate") and entry.get("name"):
                names.append(entry["name"])
    return names, len(companies)


def wikidata_names(path):
    """Label column(s) of a SPARQL TSV export (?label, optionally ?alias)."""
    names = []
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            for key in ("?label", "?alias", "label", "alias"):
                value = (row.get(key) or "").strip()
                if value:
                    names.append(value.split("@")[0].strip('"'))  # "Name"@en
    return names


def botocore_names(data_dir):
    names = []
    for service in Path(data_dir).glob("*/*/service-2.json"):
        metadata = json.loads(service.read_text(encoding="utf-8"))["metadata"]
        names += [metadata[k] for k in ("serviceFullName", "serviceAbbreviation") if metadata.get(k)]
    return names


def seed_names(path):
    names = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            names.append(line.split("\t")[0])
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prh", type=Path)
    parser.add_argument("--wikidata", type=Path)
    parser.add_argument("--botocore", type=Path)
    parser.add_argument("--seed", type=Path, action="append", default=[])
    parser.add_argument("--false-positive-rate", type=float, default=1e-5)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    names, used, prh_companies = [], [], 0
    if args.prh:
        prh, prh_companies = prh_names(args.prh)
        names += prh
        used.append({**SOURCES["prh"], "records": len(prh), "companies": prh_companies, "sha256": _sha256(args.prh)})
    if args.wikidata:
        found = wikidata_names(args.wikidata)
        names += found
        used.append({**SOURCES["wikidata"], "records": len(found), "sha256": _sha256(args.wikidata)})
    if args.botocore:
        found = botocore_names(args.botocore)
        names += found
        used.append({**SOURCES["botocore"], "records": len(found)})
    for seed in args.seed:
        found = seed_names(seed)
        names += found
        used.append({**SOURCES["seed"], "file": str(seed), "records": len(found), "sha256": _sha256(seed)})
    if not names:
        parser.error("no sources given")

    name_filter = NameFilter.build(names, {
        "built": datetime.date.today().isoformat(), "sources": used, "prh_companies": prh_companies,
    }, args.false_positive_rate)
    name_filter.save(args.out)
    meta = name_filter.metadata
    print(f"{len(names)} names -> {meta['keys']} keys, {meta['bits'] // 8} bytes, "
          f"{meta['hashes']} hashes, target false-positive rate {meta['target_false_positive_rate']}")


if __name__ == "__main__":
    main()
