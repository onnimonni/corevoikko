This repository contains the core parts of Voikko:

* libvoikko - The Voikko library
* voikko-fi - Finnish morphology for Voikko
* data - Shared data files used by libvoikko, Joukahainen etc.
* tests - Test data for automated tests covering the combined functionality of libvoikko and voikko-fi
* tools - Developer tools and generally useful Python libraries

The Wiki for this repository is used as the general developer Wiki for Voikko.

## Offline Finnish text audit

Fork: https://github.com/onnimonni/corevoikko

The audit builds this checkout's libvoikko and standard Finnish dictionary, then
checks frozen UTF-8 text. No document content leaves the machine. Python uses the
existing upstream bindings; the checker itself is the native C++ library.

```bash
# Once: provision the pinned tools from devenv.nix/devenv.lock.
devenv shell -- true

# Thereafter: offline build, accuracy workload, labelled findings.
bash autoresearch.sh

# Check a local UTF-8 plain-text document; output JSON diagnostics.
bash autoresearch.sh --text-file document.txt --profile prose
```

Profiles: `prose`, `title`, `list`, `message`. Use fragment allowances only when
the genre warrants them. Diagnostic offsets are zero-based Unicode code-point
indexes with exclusive ends, not UTF-8 bytes or UTF-16 indexes. PDF/DOCX/HTML
extraction and legal review are outside this plain-text checker.

### Corpus and scoring

- `benchmarks/finnish_cases.json`: 111 cases, source provenance, linguistic gold,
  exact spans, and explicit verbatim/corrected/synthetic labels.
- `benchmarks/check_finnish.py`: token spelling plus paragraph grammar checking,
  span scoring, and the local text-checking CLI.
- `benchmarks/baseline_findings.json`: frozen, locally labelled reproductions
  against source commit `ad9d89ef20680cbdb572894bd3e40b84573666f2`.
- `.bench-build/findings.json`: current full report, including source, corpus and
  dictionary identities. Build logs are also under `.bench-build/`.

Primary metric: `quality_loss = 5 * false_positives + false_negatives`, lower is
better. The 5:1 weighting prioritizes avoiding false alarms. Precision, recall,
correction suggestions and unsupported checks are secondary metrics. A match
requires the annotated kind, span and grammar code where specified; merely
flagging another part of an erroneous paragraph does not count as detection.
Unsupported checks do not inflate the scored false-negative count.

Initial baseline: loss **73**, **14** false-positive diagnostics, **3** missed
supported errors, **24** detected errors, **8** unsupported checks. This is an
adversarial curated corpus, **not an estimate of general Finnish accuracy**.
Several cases reproduce the same defect at distinct boundaries.
Expected corrections appear in suggestions in **18/21** scored opportunities,
including missed errors in the denominator.

### Local finding labels

| ID | Classification | Reproduced behavior |
|---|---|---|
| VOIKKO-001 | P1 `bug:coverage` | 501-token sentence discards the paragraph's earlier grammar error; 499/500 controls detect it. |
| VOIKKO-002 | P1 `bug:coverage` | Error in sentence 201 is lost; spurious missing-punctuation warning at truncation. |
| VOIKKO-003 | P2 `bug:tokenization` | Terminal URL absorbs `?`, producing a missing-punctuation false positive. |
| VOIKKO-004 | P2 `bug:false-positive` | Emoji after a complete sentence gets a missing-punctuation warning. |
| VOIKKO-005 | P2 `integration:paragraph-context` | `Hei,` plus a new line loses greeting context; correct lowercase is flagged. |
| VOIKKO-006 | P2 `bug:binding` | Python LF splitting leaves CR from CRLF and flags it as missing punctuation. |
| VOIKKO-007 | P2 `coverage:dictionary` | Correct `pseudonymisointi` and verb forms are rejected by the standard dictionary. |
| VOIKKO-008 | P2 `integration:spelling-adapter` | Dot-stripped `esim` is rejected; documented abbreviation handling is required. |
| VOIKKO-009 | P2 `integration:spelling-adapter` | Valid clock/date tokens are rejected as lexical words. |
| VOIKKO-010 | P3 `limitation:message-format` | ASCII smiley triggers an invalid-sentence-start warning. |

These are local triage labels, not filed GitHub issues. Adapter findings are not
claimed as upstream engine bugs. Diagnostics remain review suggestions, not
automatic edits or proof of incorrect Finnish.

Unsupported in this selected Finnish rule engine: general subject–verb and
adjective agreement, nominal case government, object case, relative-pronoun
selection and document semantics. Correspondence closings are covered only for
the comma after a closing formula (VOIKKO-023).
Embedded NUL is unsupported grammar input and can silently return no findings.
Adjacent verb A/MA-infinitive government **is** implemented and scored. No
spelling/grammar result establishes privacy-law compliance or factual accuracy.

Known gaps, deliberately not "fixed" because a stricter rule would flag
legitimate plain-text policies (`limitation:false-negative`):

- A paragraph ending in `,`, `;` or `:` passes the terminal-punctuation check.
  Colons before lists and commas/semicolons on list lines are legitimate.
- An unclosed opening parenthesis is not reported; only a stray closing one
  (code 12) is. List markers such as `a)` make naive pairing unreliable.
- Missing-verb hint (code 17) fires on verbless formulaic greetings/closings
  ending in a period, e.g. `Hyvää huomenta.`, `Terveisin Elias.`, in both
  profiles (`limitation:message-format`). Disabling it would also lose real
  hits such as `Minä juoksema nopeasti.`
- Valid-looking compounds can hide typos: `Ystävälisin` parses as *ystävä* +
  *lisin* (`limitation:compound-overgeneration`). Individual frequent cases go
  to the autocorrect list (see VOIKKO-016).
- Suggestion ranking (`limitation:suggestion-ranking`): `tietosuja` never
  suggests `tietosuoja`, although it is generated (rank 6 of 15 collected).
  Candidates are ranked `priority × (discovery index + 5)` and only the top 5
  are returned, so late-generator finds (e.g. inserting `o`) lose to earlier
  ones. On 1,375 single-deletion typos from corpus words: top-1 47.6%, top-5
  93.0%; of the 96 misses, 81 are collected but ranked 6–15 and only 15 are
  never generated. Insertion order, doubling the cost budget and doubling the
  candidate cap changed nothing. A fix needs a ranking redesign validated on
  a larger suggestion gold set than upstream's 68 lines.
- Real-document residue (Kela privacy page, 119 blocks, 19 diagnostics after
  VOIKKO-017/018; none is a genuine error in the source): agency/page names seen
  once (`Automaattiset päätökset`, `Tietoluvat`), inconsistently cased words
  (`Kirjaamo` vs `kirjaamoon`), and dictionary gaps — standalone `PDF`/`pdf`,
  programme names `Eepos`, `Kanta`. (`PL` and *toisio-* were fixed in
  VOIKKO-021/025.)
- Organisation names (`coverage:dictionary-config`): 113 vocabulary entries
  flagged `orgname` (Fimea, Valvira, Nordea, Tekes, Siemens, Kone, …) are
  excluded from the default build. Building with
  `make vvfst GENLEX_OPTS=--extra-usage=orgname` was measured on a separate
  dictionary: the benchmark stays at loss 0 and all upstream suites pass;
  inflected forms such as `Fimean` and `Nordean` stop being spelling errors.
  Cost: capitalized homographs lose the code 6 hint (`Ostin uuden Koneen.`
  is no longer flagged, since *Kone* is also a company). Default left
  unchanged; choose per use case. `Verohallinto` and `Tilastokeskus` are
  accepted as compounds but get code 6 when capitalized; `Traficom` is absent.
- `Digi- ja väestötietovirasto` gets code 6 on `Digi-`: a capitalized
  suspended compound part starting a name is indistinguishable from a slip.
- Second real document (Yle Abitreenit privacy notice, 45 blocks): 9
  diagnostics after VOIKKO-020; recall 39/40 injected typos (the one miss is
  inside an email address, which is never spell-checked by design). Residue:
  product name `Abitreenit-`, surname `Hausen`, code 17 on bold run-in
  headings flattened into prose (`Oikeus saada pääsy tietoihisi.`), and one
  genuine source issue: a sentence ending in a URL without a full stop (code 9).
- Correspondence guide (Kielitoimiston ohjepankki, *Sähköposti, kirje ja muut
  viestit*): 40/42 of its correct example messages pass the `message` profile
  after VOIKKO-022. Remaining (`limitation:message-format`): the endorsed
  lowercase signature `t. Tuisku` after `Hyvää joulunodotusta!` gets code 7,
  and `PS Muista kokous.` (undotted PS) gets code 6 on `Muista`.
- Third real document (Otava web-shop privacy policy, 26 blocks): 9
  diagnostics after VOIKKO-024, recall 34/35 (the miss is inside a URL). The
  residue is unknown company names (`Storia`, `Paytrail`), the English gloss
  `Cookie`, and two genuine source issues: a capitalized common noun
  (`Tietosuojaselostetta`, code 6) and a sentence without a full stop (code 9).
  The page also has two real grammar errors that pass silently, illustrating the
  unsupported classes: case government *Evästeistä käytetään* (should be
  *Evästeitä*) and a stray comma before the adverbial *joka kerta*.
- Document structure (`limitation:document-structure`): the CLI applies one
  profile per file. Headings and list items need `title`/`list` profiles,
  which require structure from the source format (HTML/DOCX), not plain text.

### Retained fixes

- VOIKKO-002: grammar analysis now stores every sentence in a paragraph instead
  of truncating at 200. Sentence 201 is checked with correct original offsets,
  without the truncation-induced punctuation warning.
- VOIKKO-001: dynamic token storage removes the 500-token sentence ceiling;
  supported errors before and after a long sentence retain their original spans.
- VOIKKO-006: the Python binding accepts CRLF paragraph endings without feeding
  CR to grammar rules; diagnostic spans still refer to the original input.
- VOIKKO-003: URL tokens leave terminal `.`, `!` and `?` as sentence punctuation,
  while query separators and parameters inside URLs remain intact.
- VOIKKO-007: the standard dictionary now includes the sourced verb
  `pseudonymisoida`, with regular inflection and derived `pseudonymisointi`.
- VOIKKO-008/009: spelling also checks a token with its following original dot
  when necessary. Abbreviations and dot-terminated dates/times no longer produce
  lexical false alarms; absent dots and misspelled words are not silently accepted.
- VOIKKO-004: terminal-punctuation checking skips trailing whitespace and
  non-language symbols, including across sentence boundaries. Symbols do not
  conceal a missing punctuation mark after an actual word.
- VOIKKO-005: the message profile retains comma-ended line continuations and
  maps normalized CRLF grammar spans back to original code-point positions.
  Exclamation-ended greetings still require correct sentence capitalization.
- VOIKKO-010: unfinished/message checking does not treat a wordless symbolic
  fragment as a linguistic sentence start. Duplicate commas and invalid starts
  of actual linguistic sentences remain checked; strict prose is unchanged.
- VOIKKO-011 (P1 `bug:memory-safety`, found after the baseline): the grammar
  cache compared input with `wcscmp`, ignoring the documented length of
  `voikkoNextGrammarErrorUcs4`. A correctly bounded buffer without a
  terminating NUL was read out of bounds; a guarded-page repro crashed with
  SIGBUS. A shorter bound on the same text also returned a stale error lying
  outside the bound. The cache now stores and compares the exact length.
- VOIKKO-012 (P2 `bug:false-negative`): a foreign quotation mark `“` as the
  last token of a sentence was never examined (the check required two more
  tokens), so `”…“` passed. It now gets code 11 with suggestion `”`.
- VOIKKO-013 (P1 `bug:false-positive`): decomposed Unicode (NFD, common in
  macOS and some PDF/mail exports) split every word at combining diacritics:
  `Säilytämme` became `Sa`+`ilyta`+`mme`, each flagged as a misspelling. The
  spell API already normalized NFD; only the tokenizer classified U+0300–U+036F
  as unknown. Combining marks now stay inside words; NFD typos are still caught.
- VOIKKO-014 (P1 `bug:false-positive`): company names got "write in lowercase"
  (code 6) on the company form itself — `Posti Oy`, `Nokia Oyj` — and on
  capitalized name words before it. `Oy`/`Oyj`/`Ab`/`Abp`/`Ky`/`Ay`/`Tmi`,
  including inflected forms such as `Oy:n` and `Oyj:ssä`, and the capitalized
  run ending in one are now accepted. A capitalized common noun outside such a
  run is still reported. Source: Kielitoimiston ohjepankki, "Yhdistys- tai
  yhtiömuotoa ilmaisevat lyhenteet: ry, oy" — *oy*/*oyj* may by established
  practice be capitalized (*Kemira oyj ~ Kemira Oyj*); both remain accepted.
- VOIKKO-015 (`coverage:dictionary` + `integration:spelling-adapter`): added
  `GDPR` in `vvfst/poikkeavat.lexc` (not the `joukahainen.xml` export, which
  `make update-vocabulary` overwrites) with front-vowel endings (`GDPR:ää`, `GDPR:ssä`;
  `GDPR:aa` and `GDRP` stay rejected). The adapter no longer spell-checks
  letterless tokens such as Y-tunnus `1234567-8`, `040-1234567` and ISO dates;
  tokens with letters, e.g. `kissa2`, are still checked.
- VOIKKO-016 (`coverage:autocorrect`): `ystävälisin` → `ystävällisin` added to
  `vocabulary/autocorrect/fi.xml`. Grammar now reports the misspelled email
  sign-off as code 1 with a case-preserving suggestion.
- VOIKKO-017 (`integration:document-names`, adapter policy): a base form the
  document capitalizes mid-sentence at least twice and never writes in
  lowercase is treated as a name, so "write in lowercase" (code 6) is dropped
  for it — `Kela`, `Kelan`, `Kelassa` (*kela* is also "reel"). On the Kela
  privacy page this removed 42 of 65 diagnostics. Single capitalized slips and
  words also written in lowercase in the same document stay reported.
- VOIKKO-018 (`integration:spelling-adapter`): schemeless domains on common
  TLDs (`tietosuoja.fi`, `kela.fi`) are not spell-checked; a hyphen-attached
  ending is (`Suomi.fi-tunnisteella` passes, `…-tunnisteela` is flagged). A
  missing space after a full stop (`kissa.koira`) is still reported.
- VOIKKO-019 (`coverage:dictionary`): `Kela` (Kansaneläkelaitos) added as a
  proper noun in `vvfst/poikkeavat.lexc` with the same `kala` inflection as the
  common noun *kela* ("reel"), which was the only entry. A single `Kelan` or
  `Kelalle` no longer gets code 6; lowercase *kelalla* is still accepted.
- VOIKKO-020 (`coverage:dictionary`): `ETA` (Euroopan talousalue) added with
  back-vowel endings (`ETA:n`, `ETA:ssa`, `ETA-maissa`; `ETA:ssä` rejected).
  It was absent, so every "EU- tai ETA-maissa" in a data-transfer section was
  flagged.
- VOIKKO-021 (`coverage:dictionary`): `PL` (postilokero, per Kielitoimiston
  ohjepankki's lyhenneluettelo) added as an uninflected abbreviation for
  addresses such as `PL 450, 00056 Kela`; `PLL` stays rejected.
- VOIKKO-022 (`coverage:dictionary`): `terv.` (terveisin) and `P.S.` (post
  scriptum), both endorsed by the Kotus correspondence guide, added; `Terv.
  Elias Laine` and `P.S. Muista kokous.` no longer produce spelling errors.
- VOIKKO-023 (`integration:message-format`, adapter check): in the `message`
  profile, a comma after a closing formula on its own line followed by a name
  line is reported as code 4 ("remove extra comma"), per Kotus:
  "Lopputervehdyksen jäljessä ei käytetä pilkkua". Only the guide's formulas
  are matched (`Terveisin`, `Ystävällisin terveisin`, `Kunnioittavasti`, …);
  `Hei,` and formula words inside a sentence are untouched. This moves the
  corpus's `signature-comma` case from unsupported to detected (1/8).
- VOIKKO-024 (`coverage:dictionary`): `IP` (Internet Protocol, per
  Kielitoimiston ohjepankki's lyhenneluettelo) added with front-vowel endings,
  so `IP-osoite`/`IP-osoitteen` pass; `IP:ta` stays rejected.
- VOIKKO-025 (`coverage:dictionary`): the prefix *toisio-* ("secondary") added
  with the same compounding as its counterpart *ensiö-*, via a new
  `Poikkeavat_p` lexicon wired into `Sanasto_p`. `toisiokäyttö`, `toisiolain`
  and `toisioraaka-aine` pass; bare `toisio` and `toisiokäytö` are rejected.

Current frozen-corpus result: **0 false positives**, **0 missed supported
errors**, **27 detections**, **21/21 corrections**; 1 of the 8 unsupported
checks (signature comma) is now detected and the other 7 remain unsupported.
Passing this curated workload does not establish correctness on arbitrary text.

Native regressions, after the benchmark build (adapter behavior plus upstream
`tests/voikkotest/fi-x-vfst` grammar 181, tokenizer 33, sentence 19, spelling
3,700+ and suggestion 68 cases):
`devenv --offline shell -- uv run --offline --no-project python -m unittest -v benchmarks.test_check_finnish benchmarks.test_upstream_suites`

`libvoikko/test` used `failIf`/`failUnless`/`assertEquals`, removed in Python
3.12, so most of the suite errored before reaching Voikko (`bug:test-suite`,
fixed). With this hermetic build, 59/65 `LibvoikkoTest` cases pass; the other 6
need default dictionary discovery or the medicine variant, which
`--disable-external-dicts` and the standard-only build intentionally omit.


### Reviewed public sources

Short attributed excerpts, stored locally; URLs are provenance, never benchmark
dependencies. No private correspondence was collected.

- [Kela: tietosuoja](https://www.kela.fi/tietosuoja)
- [Yle: Abitreenit privacy notice](https://yle.fi/a/20-10006120)
- [Kotus: kieliaineistojen käyttö](https://kotus.fi/kotus/kieliaineistot/kieliaineistojen-kaytto/)
- [Kielitoimiston ohjepankki: sähköposti, kirje ja muut viestit](https://kielitoimistonohjepankki.fi/ohje/sahkoposti-kirje-ja-muut-viestit/)
- [Tietosuojavaltuutettu: pseudonymisointi ja anonymisointi](https://tietosuoja.fi/pseudonymisointi-anonymisointi)

The Kotus excerpt has a real source typo, `osoitteseen` → `osoitteeseen`, which
Voikko detects and suggests correctly. It is **not** a Voikko bug. Page-specific
open licences were not established; do not assume these quotations license
redistributing entire source documents.

