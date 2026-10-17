# Sentence boundaries in abstracts

Use `bmlibrarian.utils.sentence_bounds` whenever you need to know whether a
span of an abstract is one or more complete sentences, for example to
validate an LLM quote. Do not split on `". "`: biomedical text is full of
"et al.", "e.g.", "vs.", "Fig. 2", "E. coli", "sp. nov.", decimals and
structured-abstract labels.

- `complete_sentence_span(text, start, end) -> (start, end) | None`: trims
  whitespace and appends closing punctuation the quote omitted, but never
  adds words. Returns None for fragments and label-only spans. The citation
  agent rejects a passage with `REJECT_INCOMPLETE_SENTENCE` when this
  returns None.
- `is_sentence_start(text, i)`: true at the start of the text, after a
  sentence end, after a line break, or after a section label that itself
  starts a sentence. Opening brackets, quotes and `*`/`#` in between are
  skipped.
- `is_sentence_end(text, i)` (i exclusive): true for `.`/`!`/`?` plus
  closing brackets or quotes, followed by whitespace or the end of the text.
  Also true at a line break or the end of the text. A `.` does not count if
  the next word is lowercase, if the token is in `NON_TERMINAL_ABBREVIATIONS`,
  or if it is the "al" of "et al.". "Al." on its own (aluminium) does count.
- Section labels are "RESULTS:", "**RESULTS:**", or mixed-case names in
  `KNOWN_SECTION_LABELS` ("Materials and methods:"). An ordinary colon
  ("two arms: Group A…") is not a label.
- Policy: ambiguity means "not a boundary", so a doubtful span is rejected,
  never accepted. Known conservative misses are a sentence that starts
  lowercase after a full stop ("mRNA…"), and "et al." or "Fig." at the real
  end of a sentence.
- All functions are pure. Bad arguments raise `TypeError`/`ValueError`.

Tests: `tests/test_sentence_bounds.py`. It is a candidate for upstreaming to
bmlib (shared text utilities).
