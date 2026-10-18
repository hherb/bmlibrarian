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
  closing brackets/quotes, followed by whitespace, the end of the text, or a
  glued capitalised word (`"DAPT.The"`, `"stenosis.Conclusion:"`: source
  text, from PubMed and Europe PMC alike, that lost its spaces). A line break
  or the end of the text **without** punctuation is not an end (hard-wrapped
  text, truncated sentences, keyword lists). A `.` does not count if the
  token before it is in `NON_TERMINAL_ABBREVIATIONS` (unless it is all caps:
  "clinical CA.", "levels of NO." end sentences), is the "al" of "et al."
  (any case) not followed by a capitalised word ("et al. (2019)" continues,
  "…by Knaus et al. Curves were…" ends), is an initial (`INITIAL_PATTERN`:
  "U.S", "e.g"), or is a single capital letter after another initial
  ("J. M. Smith"), or if the next word is an ordinary lowercase word. Any
  other single capital is a designator that can end a sentence ("type B.",
  "Group A.", "hepatitis B."). Time units ("3 min.", "2 hrs.") are not in
  the abbreviation list.
  Lowercase words that contain a digit or a capital ("p53", "mRNA", "eGFR")
  or start with a Greek letter ("β-blockers") can start a sentence. At the
  very end of the text the abbreviation rules do not apply ("…Smith et al."
  ends the text and its sentence). "Al." on its own (aluminium) counts.
  Throughout the module, invisible format characters (Unicode `Cf`: zero-width
  space, soft hyphen, word joiner, BOM) count as whitespace (`_is_blank`,
  #302), so `"…cohort.​ Next"` still ends a sentence.
- `is_sentence_start(text, i)`: true at the start of the text, after a
  sentence end, after a blank line, after a single line break that follows
  a sentence end or a heading/label line ("BACKGROUND", "## Results",
  "Methods:"), or after a section label that itself starts a sentence,
  with or without a space after its colon (`"Conclusion:Pre-operative"`).
  Opening brackets, quotes and `*`/`#` in between are skipped.
- Section labels are all caps ("RESULTS:", "**RESULTS:**", "AUTHORS'
  CONCLUSIONS:") or mixed-case
  names in `KNOWN_SECTION_LABELS` ("Materials and methods:", "Conclusions
  and Relevance:"). An ordinary colon ("two arms: Group A…") is not a label.
- Policy: ambiguity means "not a boundary", so a doubtful span is rejected,
  never accepted, with four owner-approved exceptions (2026-10-19, #303)
  because they rejected real evidence: all-caps tokens, single-capital
  designators, "et al." before a capital, and glued sentences/labels. The
  price: "…reported by J. Smith" can be cut after "J.". Measured on 500
  random PubMed abstracts: no mid-sentence fragment accepted before or after
  (0 of 2,319 comma cuts, 0 of 29 abbreviation-ended pieces, the same 15
  label-artifact "first word dropped" spans of 4,317), naive sentences
  accepted 94.3% → 94.9%. Known conservative misses: a sentence ending in a
  listed abbreviation or initial with more text after it ("…given i.v. Next"), a label
  fused to the next word (`"unclear.ObjectiveThis study"`), a sentence starting with an ordinary lowercase word
  after a full stop, a sentence ending in a reference marker after the full
  stop (`significant.[12] Next`), and a final sentence with no closing
  punctuation.
- All functions are pure. Bad arguments raise `TypeError`/`ValueError`.

Tests: `tests/test_sentence_bounds.py`. It is a candidate for upstreaming to
bmlib (shared text utilities).
