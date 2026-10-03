"""Name Bloom filter: filter properties and checker integration (real Voikko)."""
import datetime
import random
import string
import tempfile
import unittest
import zipfile
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
        built = NameFilter.build(["Storia Oy"], {"sources": [{"name": "test"}], "prh_complete": True,
                                                 "prh_register_date": "2025-06-03"})
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
        prh, _, _ = prh_names(DATA / "prh_sample.json")
        # Simulates a complete register snapshot; the sample itself is not one.
        self.checker._names = NameFilter.build(prh + seed_names(DATA / "name_seed.tsv"),
                                               {"prh_complete": True, "prh_register_date": "2025-06-03"})

    def found(self, text):
        return [(d["kind"], d["text"]) for d in diagnostics(self.checker, text)]

    def testUnknownCompanyIsReported(self):
        found = diagnostics(self.checker, "Rekisterinpitäjänä toimii CONCOCONNENTE Oy.")
        self.assertEqual([("name", "CONCOCONNENTE Oy", "2025-06-03")], [(d["kind"], d["text"], d["as_of"]) for d in found])
        self.assertIn("tilanne 3.6.2025", found[0]["description"])
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

    def testIncompleteRegisterNeverCallsCompanyUnknown(self):
        self.checker._names = NameFilter.build(["Storia Oy"], {"prh_complete": False, "prh_register_date": "2025-06-03"})
        found = self.found("Rekisterinpitäjänä toimii CONCOCONNENTE Oy.")
        self.assertEqual([], [d for d in found if d[0] == "name"])

    def testStaleRegisterIsFlaggedAfter30Days(self):
        def finding(age):
            date = (datetime.date.today() - datetime.timedelta(days=age)).isoformat()
            self.checker._names = NameFilter.build(["Storia Oy"], {"prh_complete": True, "prh_register_date": date})
            return diagnostics(self.checker, "Rekisterinpitäjänä toimii CONCOCONNENTE Oy.")[0]
        self.assertFalse(finding(30)["stale"])
        self.assertNotIn("päivää vanha", finding(30)["description"])
        self.assertTrue(finding(31)["stale"])
        self.assertIn("Rekisteritieto on 31 päivää vanha", finding(31)["description"])
        self.checker._register_max_age_days = 7
        self.assertFalse(finding(7)["stale"])
        self.assertTrue(finding(8)["stale"])

    def testSnapshotDateComesFromPrhZip(self):
        from build_name_filter import prh_names
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "all_companies.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(zipfile.ZipInfo("companies.json", (2025, 6, 3, 4, 0, 0)),
                                 (DATA / "prh_sample.json").read_bytes())
            names, companies, snapshot = prh_names(path)
        self.assertEqual((datetime.date(2025, 6, 3), 5), (snapshot, companies))
        self.assertIn("Storia Oy", names)
        self.assertNotIn("Sava Group Oy", names)  # ended former name


if __name__ == "__main__":
    unittest.main()
