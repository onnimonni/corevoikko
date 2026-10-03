"""Native integration regressions; run after bash autoresearch.sh."""
import unittest

from benchmarks.check_finnish import ROOT, Voikko, configure, diagnostics


class TextCheckerTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(Voikko.setLibrarySearchPath, Voikko._sharedLibrarySearchPath)
        Voikko.setLibrarySearchPath(str(ROOT / ".bench-build/library/src/.libs"))
        self.checker = Voikko("fi", path=str(ROOT / ".bench-build/dictionaries"))
        self.addCleanup(self.checker.terminate)
        configure(self.checker, "message")


    def testCommaContinuationPreservesOriginalCrLfSpan(self):
        for newline in ("\n", "\r\n"):
            text = newline.join(("Hei,", "voidaanko kokous aloittaa?", "Se oli joten kuten."))
            errors = diagnostics(self.checker, text)
            start = text.index("joten kuten")
            self.assertEqual([("grammar", 1, start, start + 11)],
                             [(e["kind"], e.get("code"), e["start"], e["end"]) for e in errors])

    def testExclamationStillRequiresSentenceCapitalization(self):
        errors = diagnostics(self.checker, "Hei!\nsopiiko kokous?")
        self.assertEqual([("grammar", 7, 5, 12)],
                         [(e["kind"], e.get("code"), e["start"], e["end"]) for e in errors])

    def testIdentifiersAndGdprAreNotMisspellings(self):
        configure(self.checker, "prose")
        clean = ("Y-tunnus 1234567-8 on yrityksen tunniste.",
                 "Päivitetty 2026-10-03.",
                 "Noudatamme GDPR-vaatimuksia.")
        for text in clean:
            self.assertEqual([], diagnostics(self.checker, text), text)
        for text, typo in (("Tiedot kissa2 poistetaan.", "kissa2"),
                           ("Noudatamme GDRP:tä.", "GDRP:tä")):
            self.assertEqual([("spelling", typo)],
                             [(e["kind"], e["text"]) for e in diagnostics(self.checker, text)])

    def testMisspelledSignOffIsAutocorrected(self):
        errors = diagnostics(self.checker, "Ystävälisin terveisin\nElias Laine")
        self.assertEqual([("grammar", 1, 0, 11, ["Ystävällisin"])],
                         [(e["kind"], e.get("code"), e["start"], e["end"], e["suggestions"]) for e in errors])
        self.assertEqual([], diagnostics(self.checker, "Ystävällisin terveisin\nElias Laine"))

    def testGdprInflectsWithFrontVowels(self):
        self.assertEqual([True, True, True, False],
                         [self.checker.spell(w) for w in ("GDPR:n", "GDPR:ää", "GDPR:ssä", "GDPR:aa")])

    def testConsistentlyCapitalizedNamesAreLearnedPerDocument(self):
        configure(self.checker, "prose")
        text = "Tiedot ovat Kelan rekisterissä. Kela ei poista niitä, vaan Kelalle ne kuuluvat."
        self.assertEqual([], diagnostics(self.checker, text))
        # A single capitalized slip is still reported.
        single = diagnostics(self.checker, "Avaimet löytyivät Reetan Taskun pohjalta.")
        self.assertEqual([("grammar", 6, "Taskun")], [(e["kind"], e.get("code"), e["text"]) for e in single])
        # Capitalized twice but also written in lowercase: inconsistent, still reported.
        mixed = diagnostics(self.checker,
                            "Avaimet ovat Taskun pohjalla ja Taskun reunalla, mutta taskun pohja on tyhjä.")
        self.assertEqual(["Taskun", "Taskun"],
                         [e["text"] for e in mixed if e.get("code") == 6])


if __name__ == "__main__":
    unittest.main()
