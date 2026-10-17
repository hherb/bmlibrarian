# Sentence boundaries in abstracts

Use `bmlibrarian.utils.sentence_bounds` whenever you need to know whether a
span of an abstract is one or more complete sentences, for example to
validate an LLM quote. Do not split on `". "`: biomedical text is full of
"et al.", "e.g.", "vs.", "Fig. 2", "E. coli", "J. Smith", "U.S." and
structured-abstract labels.

- `complete_sentence_span(text, start, end) -> (start, end) | None`: trims
  whitespace, appends closing punctuation the quote omitted (brackets,
  quotes, `.`/`!`/`?`, Markdown `*`), then drops trailing closing marks that
  have no opening mark inside the span, so `(Data not shown.)` quoted as
  "Data not shown" is stored as `Data not shown.`. It never adds words.
  Returns None for fragments, spans without letters, label-only spans
  (`"BACKGROUND"`, `"MATERIALS AND METHODS."`) and spans with fewer than
  `MIN_SENTENCE_WORDS` (2) words besides a leading label (`"RESULTS:
  Aspirin."`). The citation agent rejects a passage with
  `REJECT_INCOMPLETE_SENTENCE` when this returns None.
- `is_sentence_end(text, i)` (i exclusive): true only for `.`/`!`/`?` plus
  closing brackets/quotes, followed by whitespace or the end of the text. A
  line break or the end of the text **without** punctuation is not an end
  (hard-wrapped text, truncated sentences, keyword lists). A `.` does not
  count if the token before it is in `NON_TERMINAL_ABBREVIATIONS`, is the
  "al" of "et al." (any case), or is an initial (`INITIAL_PATTERN`: "J",
  "S", "U.S", "e.g"), or if the next word is an ordinary lowercase word.
  Lowercase words that contain a digit or a capital ("p53", "mRNA", "eGFR")
  or start with a Greek letter ("β-blockers") can start a sentence. At the
  very end of the text the abbreviation rules do not apply ("…Smith et al."
  ends the text and its sentence). "Al." on its own (aluminium) counts.
- `is_sentence_start(text, i)`: true at the start of the text, after a
  sentence end, after a blank line, after a single line break that follows
  a sentence end or a heading/label line ("BACKGROUND", "## Results",
  "Methods:"), or after a section label that itself starts a sentence.
  Opening brackets, quotes and `*`/`#` in between are skipped.
- Section labels are all caps ("RESULTS:", "**RESULTS:**") or mixed-case
  names in `KNOWN_SECTION_LABELS` ("Materials and methods:", "Conclusions
  and Relevance:"). An ordinary colon ("two arms: Group A…") is not a label.
- Policy: ambiguity means "not a boundary", so a doubtful span is rejected,
  never accepted. Known conservative misses: a sentence ending in an initial
  or a listed abbreviation with more text after it ("…vitamin D. Next",
  "…for 30 min. Next"), a sentence starting with an ordinary lowercase word
  after a full stop, a sentence ending in a reference marker after the full
  stop (`significant.[12] Next`), and a final sentence with no closing
  punctuation.
- All functions are pure. Bad arguments raise `TypeError`/`ValueError`.

Tests: `tests/test_sentence_bounds.py`. It is a candidate for upstreaming to
bmlib (shared text utilities).
