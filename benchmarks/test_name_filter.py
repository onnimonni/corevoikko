"""Name Bloom filter: filter properties and checker integration (real Voikko)."""
import random
import string
import tempfile
import unittest
from pathlib import Path

from benchmarks.check_finnish import ROOT, Voikko, configure, diagnostics
from name_filter import BloomFilter, NameFilter, inflection_candidates, normalize

DATA = ROOT / "benchmarks/data"


class BloomFilterTest(unittest.TestCase):
    def testNoFalseNegativesAndMeasuredFalsePositiveRate(self):
        rng = random.Random(0)
        words = lambda n: {"".join(rng.choices(string.ascii_lowercase, k=12)) for _ in range(n)}
        members, others = words(5000), words(100000)
        others -= members
        bloom = BloomFilter.for_capacity(len(members), 1e-3)
        for word in members:
            bloom.add(word)
        self.assertTrue(all(word in bloom for word in members))
        rate = sum(word in bloom for word in others) / len(others)
        self.assertLess(rate, 2e-3)

    def testSaveLoadRoundTripKeepsMetadata(self):
        built = NameFilter.build(["Storia Oy"], {"sources": [{"name": "test"}], "prh_companies": 1})
        with tempfile.TemporaryDirectory() as tmp:
            built.save(Path(tmp) / "names.bloom")
            loaded = NameFilter.load(Path(tmp) / "names.bloom")
        self.assertEqual(built.metadata, loaded.metadata)
        self.assertTrue(loaded.knows_company("Storia", "Oy"))
        self.assertFalse(loaded.knows_company("Storja", "Oy"))

    def testNormalizationAndInflection(self):
        self.assertEqual(normalize("STORIA  Oy"), normalize("storia oy"))
        self.assertEqual(normalize("Kela\u2013kortti"), "kela-kortti")
        self.assertIn("storia", inflection_candidates("Storian"))
        self.assertIn("paytrail", inflection_candidates("Paytrailin"))


class NameFilterCheckerTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(Voikko.setLibrarySearchPath, Voikko._sharedLibrarySearchPath)
        Voikko.setLibrarySearchPath(str(ROOT / ".bench-build/library/src/.libs"))
        self.checker = Voikko("fi", path=str(ROOT / ".bench-build/dictionaries"))
        self.addCleanup(self.checker.terminate)
        configure(self.checker, "prose")
        from build_name_filter import prh_names, seed_names
        prh, companies = prh_names(DATA / "prh_sample.json")
        self.checker._names = NameFilter.build(prh + seed_names(DATA / "name_seed.tsv"),
                                               {"prh_companies": companies})

    def found(self, text):
        return [(d["kind"], d["text"]) for d in diagnostics(self.checker, text)]

    def testUnknownCompanyIsReported(self):
        self.assertEqual([("name", "CONCOCONNENTE Oy")],
                         self.found("Rekisterinpitäjänä toimii CONCOCONNENTE Oy."))
        self.assertEqual([("name", "Stoira Oy")], self.found("Tiedot käsittelee Stoira Oy."))
        for text in ("Rekisterinpitäjänä toimii Storia Oy.", "Tiedot siirretään Storia Oy:lle.",
                     "Rekisterinpitäjä Yleisradio Oy vastaa tiedoista."):
            self.assertEqual([], self.found(text), text)
        # Associations are not in the trade register: never reported as unknown companies.
        self.assertEqual([], [d for d in self.found("Jäsenrekisteriä ylläpitää Esimerkkiseura ry.") if d[0] == "name"])

    def testKnownNamesAreNotMisspellings(self):
        for text in ("Tiedot ovat Storian palvelimella.", "Paytrailin maksupalvelu on turvallinen.",
                     "Katso Kanta-palvelujen tietosuojaseloste."):
            self.assertEqual([], self.found(text), text)

    def testHyphenationAndMultiwordNameRules(self):
        # Wrong hyphenation of common words stays reported; Kela-kortti is correct.
        self.assertEqual([("spelling", "Henkilö-tiedot")], self.found("Mukana ovat Henkilö-tiedot."))
        self.assertEqual([], self.found("Tiedot ovat Kelan Kela-kortissa."))
        self.assertEqual([("grammar", "Analytics-palvelua")],
                         self.found("Sivustomme käyttää Google Analytics-palvelua."))

    def testWithoutRegisterNoCompanyIsCalledUnknown(self):
        self.checker._names = NameFilter.build(["Storia Oy"], {"prh_companies": 0})
        found = self.found("Rekisterinpitäjänä toimii CONCOCONNENTE Oy.")
        self.assertEqual([], [d for d in found if d[0] == "name"])


if __name__ == "__main__":
    unittest.main()
