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


if __name__ == "__main__":
    unittest.main()
