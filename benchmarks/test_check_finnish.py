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

    def testSchemelessDomainsAreNotMisspellings(self):
        configure(self.checker, "prose")
        for text in ("Lisätietoja saat osoitteesta tietosuoja.fi.",
                     "Kirjaudu Suomi.fi-tunnisteella palveluun."):
            self.assertEqual([], diagnostics(self.checker, text), text)
        for text, word in (("Kirjaudu Suomi.fi-tunnisteela palveluun.", "Suomi.fi-tunnisteela"),
                           ("Tiedot kissa.koira poistetaan.", "kissa.koira")):
            self.assertEqual([("spelling", word)],
                             [(e["kind"], e["text"]) for e in diagnostics(self.checker, text)])

    def testKelaIsAProperNoun(self):
        configure(self.checker, "prose")
        # One mention: the document-name policy cannot apply, the lexicon must.
        for text in ("Tiedot ovat Kelan rekisterissä.", "Lähetä hakemus Kelalle."):
            self.assertEqual([], diagnostics(self.checker, text), text)
        # The common noun "kela" (reel) is still accepted in lowercase.
        self.assertEqual([], diagnostics(self.checker, "Lanka on kelalla."))

    def testEtaInflectsWithBackVowels(self):
        self.assertEqual([True, True, True, True, False, False],
                         [self.checker.spell(w) for w in
                          ("ETA", "ETA:n", "ETA:ssa", "ETA-maissa", "ETA:ssä", "XYZ-maissa")])

    def testPostOfficeBoxAbbreviation(self):
        configure(self.checker, "prose")
        self.assertEqual([], diagnostics(self.checker, "Lähetä se osoitteeseen Kela, PL 450, 00056 Kela."))
        self.assertEqual([True, False], [self.checker.spell(w) for w in ("PL", "PLL")])

    def testCorrespondenceAbbreviations(self):
        self.assertEqual([], diagnostics(self.checker, "Terv. Elias Laine"))
        self.assertEqual([], diagnostics(self.checker, "P.S. Muista kokous."))
        self.assertEqual([True, True, False, False],
                         [self.checker.spell(w) for w in ("terv.", "P.S.", "terw.", "p.s.")])

    def testCommaAfterClosingFormulaIsReported(self):
        for text in ("Terveisin,\nElias Laine", "Ystävällisin terveisin,\r\nElias Laine"):
            comma = text.index(",")
            self.assertEqual([("grammar", 4, comma, comma + 1)],
                             [(e["kind"], e.get("code"), e["start"], e["end"]) for e in diagnostics(self.checker, text)])
        # Correct closings, a greeting comma and a formula inside a sentence stay clean.
        for text in ("Terveisin\nElias Laine", "Hei,\nvoidaanko kokous aloittaa?",
                     "Lähetän kunnioittavasti, mutta päättäväisesti tämän viestin."):
            self.assertEqual([], diagnostics(self.checker, text), text)

    def testIpAddressTerm(self):
        self.assertEqual([True, True, True, True, False],
                         [self.checker.spell(w) for w in ("IP", "IP:tä", "IP-osoite", "IP-osoitteen", "IP:ta")])

    def testToisioPrefixCompounds(self):
        self.assertEqual([True, True, True, True, False, False],
                         [self.checker.spell(w) for w in ("toisiokäyttö", "toisiolaki", "toisiolain",
                                                          "toisiokäyttöä", "toisio", "toisiokäytö")])

    def testPdfBothCases(self):
        self.assertEqual([True, True, True, True, True, False],
                         [self.checker.spell(w) for w in ("PDF", "pdf", "PDF:nä", "pdf-tiedosto",
                                                          "PDF-tiedostona", "PDF:na")])

    def testNonEstablishedCompoundLinkingIsReported(self):
        configure(self.checker, "prose")
        text = "Asiakkaansuhteen aikana rekisteripitäjän on suojattava tiedot."
        self.assertEqual([("Asiakkaansuhteen", ["Asiakassuhteen"]), ("rekisteripitäjän", ["rekisterinpitäjän"])],
                         [(e["text"], e["suggestions"]) for e in diagnostics(self.checker, text)])
        # Established forms, comparatives and unlisted compounds stay clean.
        for text in ("Asiakassuhteen aikana rekisterinpitäjän on suojattava tiedot.",
                     "Ostimme suurempikokoisen kissakoiran.",
                     "Kansanedustaja vastasi."):
            self.assertEqual([], diagnostics(self.checker, text), text)


if __name__ == "__main__":
    unittest.main()
