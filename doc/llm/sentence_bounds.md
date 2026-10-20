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
  Aspirin."`). When this returns None the citation agent tries
  `enclosing_sentence_span`, and rejects the passage with
  `REJECT_INCOMPLETE_SENTENCE` only if that fails too.
- `enclosing_sentence_span(text, start, end, max_added_chars=MAX_WIDENING_CHARS)`:
  widens a fragment to the complete sentence(s) containing it: back to the
  nearest sentence start (only at a letter, digit or opening mark), forward
  to the nearest sentence end, then `complete_sentence_span`. None if no
  boundary lies within `max_added_chars` (400) added characters on both
  sides together, if a new sentence starts before the fragment's sentence
  ends (the source broke it off: never run it into the next sentence), or if
  the result is not citable. Already-complete spans come back as
  `complete_sentence_span` returns them. The caller decides whether
  widening is safe; the citation agent also refuses when the fragment occurs
  more than once in the abstract, and records `Citation.widened_from`.
- `is_sentence_end(text, i)` (i exclusive): true only for `.`/`!`/`?` plus
  closing brackets/quotes, followed by whitespace, the end of the text, or a
  glued capitalised word (`"DAPT.The"`, `"stenosis.Conclusion:"`: source
  text, from PubMed and Europe PMC alike, that lost its spaces). A glued word
  does not count after a one-letter token (`"p.Arg506Gln"`, `"J.Smith"`,
  `"N.Engl"`) or when it runs on into a digit or a full stop
  (`"www.ClinicalTrials.gov"`). A line break
  or the end of the text **without** punctuation is not an end (hard-wrapped
  text, truncated sentences, keyword lists). A `.` does not count if the
  token before it is in `NON_TERMINAL_ABBREVIATIONS` (unless it is all caps
  and a capitalised word follows: "clinical CA. The", "levels of NO. In" end
  sentences, "FIG. 2", "VS. PLACEBO", "CO. Inc." do not), is the "al" of
  "et al." (any case) not followed by a capitalised word or followed by a
  bracket ("et al. (2019)", "et al. (Lancet, 2019)" continue, "…by Knaus et
  al. Curves were…" ends), is an initial (`INITIAL_PATTERN`: "U.S", "e.g"),
  or is a single capital letter next to another one (both stops of
  "J. M. Smith"), or if the next word is an ordinary lowercase word. Any
  other single capital is a designator that can end a sentence ("type B.",
  "Group A.", "hepatitis B."). Time units ("3 min.", "2 hrs.") are not in
  the abbreviation list.
  Lowercase words that contain a digit or a capital ("p53", "mRNA", "eGFR")
  or start with a Greek letter ("β-blockers") can start a sentence. At the
  very end of the text the abbreviation rules do not apply ("…Smith et al."
  ends the text and its sentence). "Al." on its own (aluminium) counts.
  In every boundary and token check, invisible format characters (Unicode `Cf`: zero-width
  space, soft hyphen, word joiner, BOM) count as whitespace (`_is_blank`,
  #302), so `"…cohort.​ Next"` still ends a sentence.
- `is_sentence_start(text, i)`: true at the start of the text, after a
  sentence end, after a blank line, after a single line break that follows
  a sentence end or a heading/label line ("BACKGROUND", "## Results",
  "Methods:"), or after a section label that itself starts a sentence,
  with or without a space after its colon (`"Conclusion:Pre-operative"`),
  after a capitalised one-word `KNOWN_SECTION_LABELS` label fused onto the
  word (`"unclear.ObjectiveThis study"`, `"ResultsWe"`, `"ConclusionsCSF"`;
  the label must itself start a sentence; #304), and after a lost-text gap:
  `LOST_TEXT_GAP_SPACES` (2) spaces, or a space after `(`/`[`/`{`, on one
  line, before a capitalised word or "A" (`"(all  Women with"`, `"E4 ( A
  minority"`: PubMed dropped a formula or symbol there). The broken sentence
  before such a gap still has no end, so it cannot be cited on its own; a
  longer quote that contains it and starts and ends at boundaries is
  accepted (owner decision, #307). A stray colon
  after a bold label (`"**CONCLUSIONS:** : Text"`) is part of the label.
  Opening brackets, quotes and `*`/`#` in between are skipped.
- Section labels are all caps ("RESULTS:", "**RESULTS:**", "**Results**:",
  "AUTHORS' CONCLUSIONS:") or mixed-case
  names in `KNOWN_SECTION_LABELS` ("Materials and methods:", "Conclusions
  and Relevance:"). An ordinary colon ("two arms: Group A…") is not a label.
- Policy: ambiguity means "not a boundary", so a doubtful span is rejected,
  never accepted, with five owner-approved exceptions (2026-10-19, #303)
  because they rejected real evidence: all-caps tokens before a capitalised
  word, single-capital designators, "et al." before a capital, time units,
  and glued sentences/labels. The price: "…reported by J. Smith" and
  "…with S. Typhimurium" can be cut after the lone initial, and "min. 3"
  after "min." (pinned in `test_known_trade_offs_split_single_initials`).
  Measured on 500 random PubMed abstracts: no fragment newly accepted (0 of
  2,319 comma cuts and 0 of 29 abbreviation-ended pieces either way; the
  same 15 label-artifact "first word dropped" spans of 4,317 were accepted
  before and after), naive sentences accepted 94.3% → 94.9%. The PR #305
  review then narrowed the all-caps and glued-text rules (above); not
  re-measured. Known conservative misses: a sentence ending in a
  listed abbreviation or initial with more text after it ("…given i.v. Next"), a
  multi-word label fused to the next word (`"Materials and methodsWe"`), a
  sentence after lost text with a single space (`"8.8%) MAE rates"`), a
  sentence starting with an ordinary lowercase word
  after a full stop, a sentence ending in a reference marker after the full
  stop (`significant.[12] Next`), and a final sentence with no closing
  punctuation.
- All functions are pure. Bad arguments raise `TypeError`/`ValueError`.

Tests: `tests/test_sentence_bounds.py`. It is a candidate for upstreaming to
bmlib (shared text utilities).
