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
selection, document semantics, and correspondence closing conventions.
Embedded NUL is unsupported grammar input and can silently return no findings.
Adjacent verb A/MA-infinitive government **is** implemented and scored. No
spelling/grammar result establishes privacy-law compliance or factual accuracy.

### Retained fixes

- VOIKKO-002: grammar analysis now stores every sentence in a paragraph instead
  of truncating at 200. Sentence 201 is checked with correct original offsets,
  without the truncation-induced punctuation warning.
- VOIKKO-001: dynamic token storage removes the 500-token sentence ceiling;
  supported errors before and after a long sentence retain their original spans.
- VOIKKO-006: the Python binding accepts CRLF paragraph endings without feeding
  CR to grammar rules; diagnostic spans still refer to the original input.


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

