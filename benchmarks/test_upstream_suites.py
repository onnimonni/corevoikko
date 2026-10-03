"""Upstream fi-x-vfst grammar/tokenizer/sentence expectations via native APIs.

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


if __name__ == "__main__":
    unittest.main()
