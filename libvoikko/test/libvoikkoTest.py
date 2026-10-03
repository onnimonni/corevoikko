# -*- coding: utf-8 -*-

# Copyright 2009 - 2011 Harri Pitkänen (hatapitk@iki.fi)
# Test suite for testing public API of libvoikko and the Python interface.

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import re
import unittest

from libvoikko import (
    Dictionary,
    MAX_ANALYSIS_COUNT,
    MAX_WORD_CHARS,
    Sentence,
    SuggestionStrategy,
    Token,
    Voikko,
    VoikkoException
)
from TestUtils import MorphologyInfo, TestDataDir


class LibvoikkoTest(unittest.TestCase):

    def setUp(self):
        self.voikko = Voikko(u"fi")

    def tearDown(self):
        self.voikko.terminate()

    def testInitAndTerminate(self):
        pass  # do nothing, just check that setUp and tearDown complete succesfully

    def testTerminateCanBeCalledMultipleTimes(self):
        self.voikko.terminate()
        self.voikko.terminate()

    def testAnotherObjectCanBeCreatedUsedAndDeletedInParallel(self):
        medicalVoikko = Voikko(u"fi-x-medicine")
        self.assertTrue(medicalVoikko.spell(u"amifostiini"))
        self.assertFalse(self.voikko.spell(u"amifostiini"))
        del medicalVoikko
        self.assertFalse(self.voikko.spell(u"amifostiini"))

    def testDictionaryComparisonWorks(self):
        d1 = Dictionary(u"fi", u"", u"a", u"b")
        d2 = Dictionary(u"fi", u"", u"a", u"c")
        d3 = Dictionary(u"fi", u"", u"c", u"b")
        d4 = Dictionary(u"fi", u"", u"a", u"b")
        d5 = Dictionary(u"sv", u"", u"a", u"b")
        self.assertNotEqual(u"kissa", d1)
        self.assertNotEqual(d1, u"kissa")
        self.assertNotEqual(d1, d2)
        self.assertNotEqual(d1, d3)
        self.assertNotEqual(d4, d5)
        self.assertEqual(d1, d4)
        self.assertTrue(d1 < d2)
        self.assertTrue(d2 < d3)
        self.assertTrue(d4 < d5)

    def testDictionaryHashCodeWorks(self):
        d1 = Dictionary(u"fi", u"", u"a", u"b")
        d2 = Dictionary(u"fi", u"", u"a", u"c")
        d3 = Dictionary(u"fi", u"", u"c", u"b")
        d4 = Dictionary(u"fi", u"", u"a", u"b")
        d5 = Dictionary(u"sv", u"", u"a", u"b")
        self.assertNotEqual(hash(d1), hash(d2))
        self.assertNotEqual(hash(d1), hash(d3))
        self.assertNotEqual(hash(d4), hash(d5))
        self.assertEqual(hash(d1), hash(d4))

    def testListDictsWithoutPath(self):
        dicts = Voikko.listDicts()
        self.assertTrue(len(dicts) > 0)
        standard = dicts[0]
        self.assertEqual(u"standard", standard.variant,
                         u"Standard dictionary must be the default in test environment.")

    def testListSupportedSpellingLanguagesWithoutPath(self):
        langs = Voikko.listSupportedSpellingLanguages()
        self.assertTrue(u"fi" in langs, u"Finnish dictionary must be present in the test environment")

    def testListDictsWithPathAndAttributes(self):
        info = MorphologyInfo()
        info.variant = u"test-variant-name"
        info.description = u"Some test description sakldjasd"
        info.morphology = u"null"
        dataDir = TestDataDir()
        dataDir.createMorphology(info.variant, info)
        dicts = Voikko.listDicts(dataDir.getDirectory())
        dataDir.tearDown()
        dictsWithCorrectVariant = list(filter(lambda aDict: aDict.variant == info.variant, dicts))
        self.assertEqual(1, len(dictsWithCorrectVariant))
        theDict = dictsWithCorrectVariant[0]
        self.assertEqual(info.description, theDict.description)
        self.assertEqual(u"fi", theDict.language)
        self.assertEqual(u"", theDict.script)

    def testInitWithCorrectDictWorks(self):
        self.voikko.terminate()
        self.voikko = Voikko(u"fi-x-standard")
        self.assertFalse(self.voikko.spell(u"amifostiini"))
        self.voikko.terminate()
        self.voikko = Voikko(u"fi-x-medicine")
        self.assertTrue(self.voikko.spell(u"amifostiini"))

    def testInitWithNonExistentDictThrowsException(self):
        def tryInit():
            self.voikko = Voikko(u"fi-x-non-existent-variant")
        self.voikko.terminate()
        self.assertRaises(VoikkoException, tryInit)

    def testInitWithPathWorks(self):
        # TODO: better test
        self.voikko.terminate()
        self.voikko = Voikko(u"fi", path=u"/path/to/nowhere")
        self.assertTrue(self.voikko.spell(u"kissa"))

    def testSpellAfterTerminateThrowsException(self):
        def trySpell():
            self.voikko.spell(u"kissa")
        self.voikko.terminate()
        self.assertRaises(VoikkoException, trySpell)

    def testSpell(self):
        self.assertTrue(self.voikko.spell(u"määrä"))
        self.assertFalse(self.voikko.spell(u"määä"))

    def testSuggest(self):
        suggs = self.voikko.suggest(u"koirra")
        self.assertTrue(u"koira" in suggs)

    def testSuggestReturnsArgumentIfWordIsCorrect(self):
        suggs = self.voikko.suggest(u"koira")
        self.assertEqual(1, len(suggs))
        self.assertEqual(u"koira", suggs[0])

    def testGrammarErrorsAndExplanation(self):
        errors = self.voikko.grammarErrors(u"Minä olen joten kuten kaunis.", "fi")
        self.assertEqual(1, len(errors))
        error = errors[0]
        self.assertEqual(10, error.startPos)
        self.assertEqual(11, error.errorLen)
        self.assertEqual([u"jotenkuten"], error.suggestions)
        self.assertEqual(u"Virheellinen kirjoitusasu", error.shortDescription)

    def testNoGrammarErrorsInEmptyParagraph(self):
        errors = self.voikko.grammarErrors(u"Olen täi.\n\nOlen täi.", "fi")
        self.assertEqual(0, len(errors))

    def testGrammarErrorOffsetsInMultipleParagraphs(self):
        errors = self.voikko.grammarErrors(u"Olen täi.\n\nOlen joten kuten.", "fi")
        self.assertEqual(1, len(errors))
        error = errors[0]
        self.assertEqual(16, error.startPos)
        self.assertEqual(11, error.errorLen)

    def testGrammarErrorAfterTwoHundredSentences(self):
        prefix = u"Talo on talo. " * 200
        text = prefix + u"Se oli joten kuten."
        errors = self.voikko.grammarErrors(text, "fi")
        self.assertEqual([(1, len(prefix) + 7, 11)],
                         [(e.errorCode, e.startPos, e.errorLen) for e in errors])

    def testGrammarErrorsSurviveLongSentences(self):
        longSentence = u"Talo on " + u"talo ja " * 130 + u"talo."
        prefix = u"Se oli joten kuten. "
        suffix = u" Se oli joten kuten."
        errors = self.voikko.grammarErrors(prefix + longSentence + suffix, "fi")
        self.assertEqual([(1, 7, 11), (1, len(prefix + longSentence) + 8, 11)],
                         [(e.errorCode, e.startPos, e.errorLen) for e in errors])

    def testGrammarErrorsPreserveCrLfOffsets(self):
        prefix = u"Tietosuoja on tärkeää.\r\n\r\n"
        errors = self.voikko.grammarErrors(prefix + u"Olen joten kuten.", "fi")
        self.assertEqual([(1, len(prefix) + 5, 11)],
                         [(e.errorCode, e.startPos, e.errorLen) for e in errors])

    def testUrlTerminalPunctuationPreservesQuery(self):
        url = u"https://example.fi/?a=1&b=2"
        for punctuation in (u".", u"!", u"?"):
            tokens = self.voikko.tokens(url + punctuation)
            self.assertEqual([(url, Token.WORD), (punctuation, Token.PUNCTUATION)],
                             [(t.tokenText, t.tokenType) for t in tokens])
        text = u"Löytyvätkö tiedot osoitteesta https://www.kela.fi/tietosuoja?"
        self.assertEqual([], self.voikko.grammarErrors(text, "fi"))

    def testTrailingSymbolsDoNotHideMissingPunctuation(self):
        symbol = u"\U0001F60A"
        for suffix in (u" ", u" " + symbol):
            self.assertEqual([], self.voikko.grammarErrors(u"Kiitos!" + suffix, "fi"))
            errors = self.voikko.grammarErrors(u"Tiedot poistetaan" + suffix, "fi")
            self.assertEqual([(9, 7, 10)],
                             [(e.errorCode, e.startPos, e.errorLen) for e in errors])

    def testSymbolicFragmentsStillCheckLanguageAndCommas(self):
        self.voikko.setAcceptUnfinishedParagraphsInGc(True)
        self.assertEqual([], self.voikko.grammarErrors(u"Kiitos! :)", "fi"))
        errors = self.voikko.grammarErrors(u"Kiitos! ,,", "fi")
        self.assertEqual([(4, 8, 2)],
                         [(e.errorCode, e.startPos, e.errorLen) for e in errors])
        errors = self.voikko.grammarErrors(u"Kiitos! : Tiedot poistetaan.", "fi")
        self.assertIn(5, [e.errorCode for e in errors])

    def testGrammarCacheRespectsSuppliedLength(self):
        lib = self.voikko._Voikko__lib
        handle = self.voikko._Voikko__handle
        text = u"Olen joten kuten."
        error = lib.voikkoNextGrammarErrorUcs4(handle, text, len(text), 0, 0)
        self.assertEqual(1, lib.voikkoGetGrammarErrorCode(error))
        lib.voikkoFreeGrammarError(error)
        # Same text, shorter bound: analyse "Olen" itself, not the cached 5:16 span.
        error = lib.voikkoNextGrammarErrorUcs4(handle, text, 4, 0, 0)
        self.assertEqual((9, 0, 4), (lib.voikkoGetGrammarErrorCode(error),
                                     lib.voikkoGetGrammarErrorStartPos(error),
                                     lib.voikkoGetGrammarErrorLength(error)))
        lib.voikkoFreeGrammarError(error)

    def testForeignQuotationMarkAsFinalToken(self):
        text = u"Hän sanoi: \u201dTiedot poistetaan.\u201c"
        errors = self.voikko.grammarErrors(text, "fi")
        self.assertEqual([(11, len(text) - 1, 1, [u"\u201d"])],
                         [(e.errorCode, e.startPos, e.errorLen, e.suggestions) for e in errors])
        self.assertEqual([], self.voikko.grammarErrors(u"Hän sanoi: \u201dTiedot poistetaan.\u201d", "fi"))

    def testDecomposedTextIsTokenizedAsWholeWords(self):
        import unicodedata
        text = unicodedata.normalize("NFD", u"Säilytämme henkilötietoja.")
        tokens = self.voikko.tokens(text)
        self.assertEqual([Token.WORD, Token.WHITESPACE, Token.WORD, Token.PUNCTUATION],
                         [t.tokenType for t in tokens])
        self.assertTrue(all(self.voikko.spell(t.tokenText) for t in tokens if t.tokenType == Token.WORD))
        self.assertFalse(self.voikko.spell(unicodedata.normalize("NFD", u"säilytettään")))

    def testAnalyze(self):
        analysisList = self.voikko.analyze(u"kansaneläkehakemus")
        self.assertEqual(1, len(analysisList))
        analysis = analysisList[0]
        self.assertEqual(u"=pppppp=ppppp=ppppppp", analysis["STRUCTURE"])

    def testTokens(self):
        tokenList = self.voikko.tokens(u"kissa ja koira")
        self.assertEqual(5, len(tokenList))
        tokenJa = tokenList[2]
        self.assertEqual(Token.WORD, tokenJa.tokenType)
        self.assertEqual(u"ja", tokenJa.tokenText)

    def testSentences(self):
        sentences = self.voikko.sentences(u"Kissa ei ole koira. Koira ei ole kissa.")
        self.assertEqual(2, len(sentences))
        self.assertEqual(u"Kissa ei ole koira. ", sentences[0].sentenceText)
        self.assertEqual(Sentence.PROBABLE, sentences[0].nextStartType)
        self.assertEqual(u"Koira ei ole kissa.", sentences[1].sentenceText)
        self.assertEqual(Sentence.NONE, sentences[1].nextStartType)

    def testAttributeValuesForEnumeratedAttribute(self):
        values = self.voikko.attributeValues(u"NUMBER")
        self.assertEqual(2, len(values))
        self.assertTrue("singular" in values)
        self.assertTrue("plural" in values)

    def testAttributeValuesForNonEnumeratedAttribute(self):
        values = self.voikko.attributeValues(u"BASEFORM")
        self.assertEqual(None, values)

    def testAttributeValuesForUnknownAttribute(self):
        values = self.voikko.attributeValues(u"XYZ")
        self.assertEqual(None, values)

    def testAttributeValuesDoNotContainDuplicates(self):
        values = self.voikko.attributeValues(u"CLASS")
        self.assertEqual(1, values.count(u"lukusana"))

    def testHyphenationPattern(self):
        pattern = self.voikko.getHyphenationPattern(u"kissa")
        self.assertEqual("   - ", pattern)
        pattern = self.voikko.getHyphenationPattern(u"määrä")
        self.assertEqual("   - ", pattern)
        pattern = self.voikko.getHyphenationPattern(u"kuorma-auto")
        self.assertEqual("    - =  - ", pattern)
        pattern = self.voikko.getHyphenationPattern(u"vaa'an")
        self.assertEqual("   =  ", pattern)
        pattern = self.voikko.getHyphenationPattern(u"auton-")
        self.assertEqual("  -   ", pattern)
        pattern = self.voikko.getHyphenationPattern(u"aztoa-")
        self.assertEqual("  - - ", pattern)
        pattern = self.voikko.getHyphenationPattern(u"aztoa-alus")
        self.assertEqual("  - -= -  ", pattern)
        pattern = self.voikko.getHyphenationPattern(u"-auton")
        self.assertEqual("   -  ", pattern)
        pattern = self.voikko.getHyphenationPattern(u"-aztoa")
        self.assertEqual("   - -", pattern)

    def testHyphenate(self):
        self.assertEqual(u"kis-sa", self.voikko.hyphenate(u"kissa"))
        self.assertEqual(u"mää-rä", self.voikko.hyphenate(u"määrä"))
        self.assertEqual(u"kuor-ma-au-to", self.voikko.hyphenate(u"kuorma-auto"))
        self.assertEqual(u"vaa-an", self.voikko.hyphenate(u"vaa'an"))

    def testHyphenateWithCustomSeparator(self):
        self.assertEqual(u"kis&shy;sa", self.voikko.hyphenate(u"kissa", u"&shy;", True))
        self.assertEqual(u"kuor&shy;ma-au&shy;to", self.voikko.hyphenate(u"kuorma-auto", u"&shy;", True))
        self.assertEqual(u"vaa&shy;an", self.voikko.hyphenate(u"vaa'an", u"&shy;", True))
        self.assertEqual(u"vaa'an", self.voikko.hyphenate(u"vaa'an", u"&shy;", False))

    def testSetIgnoreDot(self):
        self.voikko.setIgnoreDot(False)
        self.assertFalse(self.voikko.spell(u"kissa."))
        self.voikko.setIgnoreDot(True)
        self.assertTrue(self.voikko.spell(u"kissa."))

    def testSetBooleanOption(self):
        self.voikko.setBooleanOption(0, False)  # This is "ignore dot"
        self.assertFalse(self.voikko.spell(u"kissa."))
        self.voikko.setBooleanOption(0, True)
        self.assertTrue(self.voikko.spell(u"kissa."))

    def testSetIgnoreNumbers(self):
        self.voikko.setIgnoreNumbers(False)
        self.assertFalse(self.voikko.spell(u"kissa2"))
        self.voikko.setIgnoreNumbers(True)
        self.assertTrue(self.voikko.spell(u"kissa2"))

    def testSetIgnoreUppercase(self):
        self.voikko.setIgnoreUppercase(False)
        self.assertFalse(self.voikko.spell(u"KAAAA"))
        self.voikko.setIgnoreUppercase(True)
        self.assertTrue(self.voikko.spell(u"KAAAA"))

    def testAcceptFirstUppercase(self):
        self.voikko.setAcceptFirstUppercase(False)
        self.assertFalse(self.voikko.spell("Kissa"))
        self.voikko.setAcceptFirstUppercase(True)
        self.assertTrue(self.voikko.spell("Kissa"))

    def testUpperCaseScandinavianLetters(self):
        self.assertTrue(self.voikko.spell(u"Äiti"))
        self.assertFalse(self.voikko.spell(u"Ääiti"))
        self.assertTrue(self.voikko.spell(u"š"))
        self.assertTrue(self.voikko.spell(u"Š"))

    def testAcceptAllUppercase(self):
        self.voikko.setIgnoreUppercase(False)
        self.voikko.setAcceptAllUppercase(False)
        self.assertFalse(self.voikko.spell("KISSA"))
        self.voikko.setAcceptAllUppercase(True)
        self.assertTrue(self.voikko.spell("KISSA"))
        self.assertFalse(self.voikko.spell("KAAAA"))

    def testIgnoreNonwords(self):
        self.voikko.setIgnoreNonwords(False)
        self.assertFalse(self.voikko.spell("hatapitk@iki.fi"))
        self.voikko.setIgnoreNonwords(True)
        self.assertTrue(self.voikko.spell("hatapitk@iki.fi"))
        self.assertFalse(self.voikko.spell("ashdaksd"))

    def testAcceptExtraHyphens(self):
        self.voikko.setAcceptExtraHyphens(False)
        self.assertFalse(self.voikko.spell("kerros-talo"))
        self.voikko.setAcceptExtraHyphens(True)
        self.assertTrue(self.voikko.spell("kerros-talo"))

    def testAcceptMissingHyphens(self):
        self.voikko.setAcceptMissingHyphens(False)
        self.assertFalse(self.voikko.spell("sosiaali"))
        self.voikko.setAcceptMissingHyphens(True)
        self.assertTrue(self.voikko.spell("sosiaali"))

    def testSetAcceptTitlesInGc(self):
        self.voikko.setAcceptTitlesInGc(False)
        self.assertEqual(1, len(self.voikko.grammarErrors(u"Kissa on eläin", "fi")))
        self.voikko.setAcceptTitlesInGc(True)
        self.assertEqual(0, len(self.voikko.grammarErrors(u"Kissa on eläin", "fi")))

    def testSetAcceptUnfinishedParagraphsInGc(self):
        self.voikko.setAcceptUnfinishedParagraphsInGc(False)
        self.assertEqual(1, len(self.voikko.grammarErrors(u"Kissa on ", "fi")))
        self.voikko.setAcceptUnfinishedParagraphsInGc(True)
        self.assertEqual(0, len(self.voikko.grammarErrors(u"Kissa on ", "fi")))

    def testSetAcceptBulletedListsInGc(self):
        self.voikko.setAcceptBulletedListsInGc(False)
        self.assertNotEqual(0, len(self.voikko.grammarErrors(u"kissa", "fi")))
        self.voikko.setAcceptBulletedListsInGc(True)
        self.assertEqual(0, len(self.voikko.grammarErrors(u"kissa", "fi")))

    def testSetNoUglyHyphenation(self):
        self.voikko.setNoUglyHyphenation(False)
        self.assertEqual(u"i-va", self.voikko.hyphenate(u"iva"))
        self.voikko.setNoUglyHyphenation(True)
        self.assertEqual(u"iva", self.voikko.hyphenate(u"iva"))

    def testSetHyphenateUnknownWordsWorks(self):
        self.voikko.setHyphenateUnknownWords(False)
        self.assertEqual(u"kirjutepo", self.voikko.hyphenate(u"kirjutepo"))
        self.voikko.setHyphenateUnknownWords(True)
        self.assertEqual(u"kir-ju-te-po", self.voikko.hyphenate(u"kirjutepo"))

    def testSetMinHyphenatedWordLength(self):
        self.voikko.setMinHyphenatedWordLength(6)
        self.assertEqual(u"koira", self.voikko.hyphenate(u"koira"))
        self.voikko.setMinHyphenatedWordLength(2)
        self.assertEqual(u"koi-ra", self.voikko.hyphenate(u"koira"))

    def testIncreaseSpellerCacheSize(self):
        # TODO: this only tests that nothing breaks, not that cache is actually increased
        self.voikko.setSpellerCacheSize(3)
        self.assertTrue(self.voikko.spell(u"kissa"))

    def testDisableSpellerCache(self):
        # TODO: this only tests that nothing breaks, not that cache is actually disabled
        self.voikko.setSpellerCacheSize(-1)
        self.assertTrue(self.voikko.spell(u"kissa"))

    def testSetSuggestionStrategy(self):
        self.voikko.setSuggestionStrategy(SuggestionStrategy.OCR)
        self.assertFalse(u"koira" in self.voikko.suggest(u"koari"))
        self.assertTrue(u"koira" in self.voikko.suggest(u"koir_"))
        self.voikko.setSuggestionStrategy(SuggestionStrategy.TYPO)
        self.assertTrue(u"koira" in self.voikko.suggest(u"koari"))

    def testMaxAnalysisCountIsNotPassed(self):
        complexWord = u"lumenerolumenerolumenerolumenerolumenero"
        self.assertTrue(len(self.voikko.analyze(complexWord)) <= MAX_ANALYSIS_COUNT)

    def testMorPruningWorks(self):
        # TODO: this test will not fail, it just takes very long time
        # if pruning does not work.
        complexWord = u""
        for i in range(0, 20):
            complexWord = complexWord + u"lumenero"
        self.assertTrue(len(complexWord) < MAX_WORD_CHARS)
        self.voikko.analyze(complexWord)

    def testOverLongWordsAreRejectedInSpellCheck(self):
        # Limit is 255 characters. This behavior is deprecated and may change.
        longWord = u""
        for i in range(0, 25):
            longWord = longWord + u"kuraattori"
        self.assertTrue(len(longWord) < MAX_WORD_CHARS)
        self.assertTrue(self.voikko.spell(longWord))

        longWord = longWord + u"kuraattori"
        self.assertTrue(len(longWord) > MAX_WORD_CHARS)
        self.assertFalse(self.voikko.spell(longWord))

    def testOverLongWordsAreRejectedInAnalysis(self):
        # Limit is 255 characters. This behavior is deprecated and may change.
        longWord = u""
        for i in range(0, 25):
            longWord = longWord + u"kuraattori"
        self.assertTrue(len(longWord) < MAX_WORD_CHARS)
        self.assertEqual(1, len(self.voikko.analyze(longWord)))

        longWord = longWord + u"kuraattori"
        self.assertTrue(len(longWord) > MAX_WORD_CHARS)
        self.assertEqual(0, len(self.voikko.analyze(longWord)))

    def testTokenizationWorksForHugeParagraphs(self):
        hugeParagraph = "Kissa on 29 vuotta vanha... Onhan se silloin vanha. " * 10000
        self.assertEqual(10000 * 20, len(self.voikko.tokens(hugeParagraph)))

    def testTokenizationWorksWithSomeMultibyteCharacters(self):
        text = u"Kissä on 29 vuotta vanha... Onhan se silloin vanha. \n" * 9
        self.assertEqual(180, len(self.voikko.tokens(text)))

    def testEmbeddedNullsAreNotAccepted(self):
        self.assertFalse(self.voikko.spell(u"kissa\0asdasd"))
        self.assertEqual(0, len(self.voikko.suggest(u"kisssa\0koira")))
        self.assertEqual(u"kissa\0koira", self.voikko.hyphenate(u"kissa\0koira"))
        self.assertEqual(0, len(self.voikko.grammarErrors(u"kissa\0koira", "fi")))
        self.assertEqual(0, len(self.voikko.analyze(u"kissa\0koira")))

    def testNullCharMeansSingleSentence(self):
        sentences = self.voikko.sentences(u"kissa\0koira. Koira ja kissa.")
        self.assertEqual(1, len(sentences))
        self.assertEqual(Sentence.NONE, sentences[0].nextStartType)
        self.assertEqual(u"kissa\0koira. Koira ja kissa.", sentences[0].sentenceText)

    def testNullCharIsUnknownToken(self):
        tokens = self.voikko.tokens(u"kissa\0koira")
        self.assertEqual(3, len(tokens))
        self.assertEqual(Token.WORD, tokens[0].tokenType)
        self.assertEqual(u"kissa", tokens[0].tokenText)
        self.assertEqual(Token.UNKNOWN, tokens[1].tokenType)
        self.assertEqual(u"\0", tokens[1].tokenText)
        self.assertEqual(Token.WORD, tokens[2].tokenType)
        self.assertEqual(u"koira", tokens[2].tokenText)

        tokens = self.voikko.tokens(u"kissa\0\0koira")
        self.assertEqual(4, len(tokens))
        self.assertEqual(Token.WORD, tokens[0].tokenType)
        self.assertEqual(u"kissa", tokens[0].tokenText)
        self.assertEqual(Token.UNKNOWN, tokens[1].tokenType)
        self.assertEqual(u"\0", tokens[1].tokenText)
        self.assertEqual(Token.UNKNOWN, tokens[2].tokenType)
        self.assertEqual(u"\0", tokens[2].tokenText)
        self.assertEqual(Token.WORD, tokens[3].tokenType)
        self.assertEqual(u"koira", tokens[3].tokenText)

        tokens = self.voikko.tokens(u"kissa\0")
        self.assertEqual(2, len(tokens))
        self.assertEqual(Token.WORD, tokens[0].tokenType)
        self.assertEqual(u"kissa", tokens[0].tokenText)
        self.assertEqual(Token.UNKNOWN, tokens[1].tokenType)
        self.assertEqual(u"\0", tokens[1].tokenText)

        tokens = self.voikko.tokens(u"\0kissa")
        self.assertEqual(2, len(tokens))
        self.assertEqual(Token.UNKNOWN, tokens[0].tokenType)
        self.assertEqual(u"\0", tokens[0].tokenText)
        self.assertEqual(Token.WORD, tokens[1].tokenType)
        self.assertEqual(u"kissa", tokens[1].tokenText)

        tokens = self.voikko.tokens(u"\0")
        self.assertEqual(1, len(tokens))
        self.assertEqual(Token.UNKNOWN, tokens[0].tokenType)
        self.assertEqual(u"\0", tokens[0].tokenText)

        self.assertEqual(0, len(self.voikko.tokens(u"")))

    def testAllCapsAndDot(self):
        self.voikko.setIgnoreDot(True)
        self.assertFalse(self.voikko.spell(u"ABC-DEF."))

    def testGetVersion(self):
        version = Voikko.getVersion()
        # We can't test for correct version but let's assume it starts with a number
        self.assertTrue(re.compile(u"[0-9].*").match(version) is not None)

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(LibvoikkoTest)
    unittest.TextTestRunner(verbosity=1).run(suite)
