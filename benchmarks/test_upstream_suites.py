"""Upstream fi-x-vfst grammar/tokenizer/sentence/spell/suggest expectations via native APIs.

Run after bash autoresearch.sh; mirrors tools/bin/voikkotest parsing without
its external build/shell steps.
"""
import unittest

from benchmarks.check_finnish import ROOT, Voikko
from libvoikko import SuggestionStrategy

SUITE = ROOT / "tests/voikkotest/fi-x-vfst"


def fixture_lines(name):
    lines = []
    for raw in (SUITE / name).read_text(encoding="utf-8").splitlines():
        if raw.startswith("#"):
            continue
        comment = raw.find(" #")
        line = (raw[:comment] if comment != -1 else raw).strip()
        if line:
            lines.append(line)
    return lines


class UpstreamSuiteTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(Voikko.setLibrarySearchPath, Voikko._sharedLibrarySearchPath)
        Voikko.setLibrarySearchPath(str(ROOT / ".bench-build/library/src/.libs"))
        self.voikko = Voikko("fi", path=str(ROOT / ".bench-build/dictionaries"))
        self.addCleanup(self.voikko.terminate)

    def setDefaults(self):
        self.voikko.setIgnoreDot(False)
        self.voikko.setIgnoreNumbers(False)
        self.voikko.setSuggestionStrategy(SuggestionStrategy.TYPO)
        self.voikko.setAcceptTitlesInGc(False)
        self.voikko.setAcceptUnfinishedParagraphsInGc(False)
        self.voikko.setAcceptBulletedListsInGc(False)

    def testGrammar(self):
        cases, section = [], ""
        for line in fixture_lines("grammar.txt"):
            if line.startswith("{") and line.endswith("}"):
                section = line[1:-1]
            elif line.startswith("["):
                cases[-1][2].append(line)
            else:
                cases.append((section, line, []))
        self.assertGreater(len(cases), 100, "grammar fixture parsing yielded too few cases")
        for section, text, expected in cases:
            with self.subTest(section=section, text=text):
                self.setDefaults()
                voikko = self.voikko  # name referenced by fixture option expressions
                for option in section.split(" "):
                    if option:
                        eval(option)  # trusted fixture syntax: voikko.setAcceptTitlesInGc(True)
                actual = ["[code=%i, level=0, stpos=%i, len=%i, suggs={%s}]" % (
                    e.errorCode, e.startPos, e.errorLen,
                    ",".join('"%s"' % s for s in e.suggestions))
                    for e in voikko.grammarErrors(text, "fi")]
                self.assertEqual(expected, actual)

    def testTokenizerAndSentences(self):
        for name, split in (("tokenizer.txt", self.voikko.tokens),
                            ("sentence.txt", self.voikko.sentences)):
            self.setDefaults()
            lines = fixture_lines(name)
            for text, expected in zip(lines[0::2], lines[1::2]):
                with self.subTest(fixture=name, text=text):
                    self.assertEqual(expected, repr(split(text)))

    def applySection(self, section):
        voikko = self.voikko  # name referenced by fixture option expressions
        for option in section.split(" "):
            if option:
                eval(option)  # trusted fixture syntax: voikko.setIgnoreDot(True)

    def testSpelling(self):
        section, count = "", 0
        self.setDefaults()
        for line in fixture_lines("spell.txt"):
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                self.setDefaults()
                self.applySection(section)
                continue
            negative = line.startswith("!")
            word = line[1:] if negative else line
            count += 1
            with self.subTest(section=section, word=line):
                self.assertEqual(not negative, self.voikko.spell(word))
        self.assertGreater(count, 1000, "spelling fixture parsing yielded too few cases")

    def testSuggestions(self):
        section, count = "", 0
        self.setDefaults()
        for line in fixture_lines("suggest.txt"):
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            count += 1
            self.applySection(section)
            remaining = self.voikko.suggest(parts[0])
            self.setDefaults()
            # Required suggestions must appear in order; "!x" must not follow.
            for expected in parts[1:]:
                with self.subTest(section=section, word=parts[0], expected=expected):
                    if expected.startswith("!"):
                        self.assertNotIn(expected[1:], remaining)
                    else:
                        self.assertIn(expected, remaining)
                        remaining = remaining[remaining.index(expected) + 1:]
        self.assertGreater(count, 60, "suggestion fixture parsing yielded too few cases")


if __name__ == "__main__":
    unittest.main()
