"""Bloom filter of company, product and service names.

A Bloom filter answers "definitely not in the set" exactly and "probably in the
set" with a tunable false-positive rate. That fits two checker uses:

- "CONCOCONNENTE Oy" is definitely not a registered company -> report it.
- "Storian", "Paytrail-tietosuojaseloste": the name is (probably) known ->
  don't report it as a misspelling.

Keys are namespaced:
  c:<name> <form>  registered company name with canonical company form ("storia oy")
  n:<name>         a name without company form ("storia", "google analytics")
  w:<word>         a single word of a multiword name ("analytics")
"""
import hashlib
import json
import math
import re
import struct
import unicodedata
from pathlib import Path

MAGIC = b"FNBF1\n"

# Company forms as written in names, mapped to a canonical form (PRH YRMU codes).
COMPANY_FORMS = {
    "oy": "oy", "oyj": "oyj",      # OY, OYJ
    "ab": "oy", "abp": "oyj",      # Swedish equivalents of oy/oyj
    "oy ab": "oy",                 # bilingual form, e.g. "Esimerkki Oy Ab"
    "ky": "ky", "kb": "ky",        # KY
    "ay": "ay", "tmi": "tmi",      # AY, toiminimi
    "ry": "ry", "rf": "ry",        # rekisteröity yhdistys
    "osk": "osk",                  # OK (osuuskunta)
}
# Forms whose companies are all on the Trade Register (YTJ all_companies). Not
# ry (Register of Associations) or Tmi (sole traders need not register a name).
TRADE_REGISTER_FORMS = ("oy", "oyj", "ab", "abp", "ky", "kb", "ay", "osk")
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014"), "-")
_QUOTES = dict.fromkeys(map(ord, "\u2019\u02bc"), "'")

# Finnish case endings stripped to find a name's base form: Storian -> Storia,
# Paytrailin -> Paytrail, Kelassa -> Kela. Longest first.
_ENDINGS = sorted({
    "n", "a", "ä", "ta", "tä", "na", "nä", "ssa", "ssä", "sta", "stä", "lla", "llä", "lta", "ltä",
    "lle", "ksi", "tta", "ttä", "in", "ia", "iä", "ina", "inä", "issa", "issä", "ista", "istä",
    "illa", "illä", "ilta", "iltä", "ille", "iksi", "iin", "hin", "seen", "ineen", "en",
}, key=len, reverse=True)


def normalize(name):
    """NFC, casefolded, unified dashes/apostrophes, single spaces."""
    name = unicodedata.normalize("NFC", name).translate(_DASHES).translate(_QUOTES)
    return " ".join(name.casefold().split())


def split_company_form(normalized):
    """("storia", "oy") for "storia oy"; (normalized, None) without a trailing form."""
    for form in sorted(COMPANY_FORMS, key=len, reverse=True):
        if normalized.endswith(" " + form):
            return normalized[: -len(form) - 1].rstrip(" ,"), COMPANY_FORMS[form]
    return normalized, None


def name_keys(name):
    """All filter keys for one source name."""
    norm = normalize(name)
    if not norm:
        return set()
    base, form = split_company_form(norm)
    keys = {"n:" + base}
    if form:
        keys.add(f"c:{base} {form}")
    words = re.findall(r"[\w'&]+", base)
    if len(words) > 1:
        keys.update("w:" + w for w in words if len(w) >= 2)
    return keys


def inflection_candidates(token):
    """The token and plausible base forms after stripping one case ending."""
    norm = normalize(token)
    candidates = {norm}
    if ":" in norm:
        candidates.add(norm.split(":", 1)[0])  # Oy:n, GDPR:ää
    for ending in _ENDINGS:
        if norm.endswith(ending) and len(norm) - len(ending) >= 3:
            candidates.add(norm[: -len(ending)])
    return candidates


class BloomFilter:
    """Standard Bloom filter with double hashing (Kirsch-Mitzenmacher) over BLAKE2b."""

    def __init__(self, bits, hashes, data=None):
        self.bits = bits
        self.hashes = hashes
        self.data = bytearray(data) if data is not None else bytearray((bits + 7) // 8)

    @classmethod
    def for_capacity(cls, items, false_positive_rate):
        bits = max(8, math.ceil(-items * math.log(false_positive_rate) / math.log(2) ** 2))
        hashes = max(1, round(bits / max(items, 1) * math.log(2)))
        return cls(bits, hashes)

    def _positions(self, key):
        digest = hashlib.blake2b(key.encode("utf-8"), digest_size=16).digest()
        h1, h2 = struct.unpack("<QQ", digest)
        return ((h1 + i * h2) % self.bits for i in range(self.hashes))

    def add(self, key):
        for p in self._positions(key):
            self.data[p >> 3] |= 1 << (p & 7)

    def __contains__(self, key):
        return all(self.data[p >> 3] & (1 << (p & 7)) for p in self._positions(key))


class NameFilter:
    """Bloom filter plus provenance metadata, stored as one binary file."""

    def __init__(self, bloom, metadata):
        self.bloom = bloom
        self.metadata = metadata

    @classmethod
    def build(cls, names, metadata, false_positive_rate=1e-5):
        keys = set()
        for name in names:
            keys |= name_keys(name)
        bloom = BloomFilter.for_capacity(max(len(keys), 1), false_positive_rate)
        for key in keys:
            bloom.add(key)
        metadata = {**metadata, "keys": len(keys), "bits": bloom.bits, "hashes": bloom.hashes,
                    "target_false_positive_rate": false_positive_rate}
        return cls(bloom, metadata)

    def save(self, path):
        header = json.dumps(self.metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")
        Path(path).write_bytes(MAGIC + struct.pack("<I", len(header)) + header + bytes(self.bloom.data))

    @classmethod
    def load(cls, path):
        raw = Path(path).read_bytes()
        if not raw.startswith(MAGIC):
            raise ValueError(f"Not a name filter: {path}")
        (length,) = struct.unpack_from("<I", raw, len(MAGIC))
        start = len(MAGIC) + 4
        metadata = json.loads(raw[start:start + length])
        return cls(BloomFilter(metadata["bits"], metadata["hashes"], raw[start + length:]), metadata)

    @property
    def covers_finnish_companies(self):
        """Only a filter built from the complete PRH register may call a company unknown."""
        return bool(self.metadata.get("prh_complete")) and bool(self.register_date)

    @property
    def register_date(self):
        """Date of the PRH register snapshot (ISO), or None."""
        return self.metadata.get("prh_register_date")

    def knows_name(self, token):
        """A (possibly inflected) token is itself a known name: Storian, Kanta-, Paytrailin."""
        return any(("n:" + c) in self.bloom for c in inflection_candidates(token))

    def knows_name_word(self, token):
        """A (possibly inflected) token is one word of a known multiword name."""
        return any(("w:" + c) in self.bloom for c in inflection_candidates(token))

    def knows_full_name(self, phrase):
        return ("n:" + split_company_form(normalize(phrase))[0]) in self.bloom

    def knows_company(self, name, form):
        canonical = COMPANY_FORMS.get(normalize(form))
        return canonical is not None and f"c:{normalize(name)} {canonical}" in self.bloom
