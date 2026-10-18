# Locating quoted passages in source text

Use `bmlibrarian.utils.passage_match.find_passage(passage, text, min_similarity)`
whenever an LLM "quotes" a source and you need the source's own wording or
span (citation validation, highlighting, evidence checks). Do not hand-roll a
`SequenceMatcher` sliding window. The old one in `CitationFinderAgent` made
O(P·A) `SequenceMatcher` calls, each O(P²) (31 s per 1 kB abstract), and
mis-mapped spans.

- Returns `PassageMatch(similarity, start, end, text, exact)`; `matched` is
  True when `similarity >= min_similarity`. `text == original[start:end]`,
  with the original case and whitespace. `__post_init__` rejects
  inconsistent values (span fields only partly set, similarity outside
  [0, 1]).
- `exact` is True when only case, whitespace, accents, typographic
  variants, compatibility forms (`²` vs `2`) and invisible characters
  differ. An exact span can start or end inside a multi-letter fold (`ﬁ`). Use it rather than
  `similarity == 1.0`. Exact spans may start or end mid-word; fuzzy spans
  always start and end on word boundaries. For citations, the span must also
  be complete sentences; see `doc/llm/sentence_bounds.md`.
- `similarity` is `SequenceMatcher(autojunk=False).ratio()` on normalised text
  (see `fold_char()` below, collapsed whitespace), reported even on rejection. It is 0.0
  when no candidate location was found at all or the passage is too long to
  reach the threshold (`fits_text()`), so 0.0 means "not found", not a near
  miss.
- `fold_char()` folds one character (#291): curly quotes, primes and
  guillemets to `'`/`"`, hyphen/dash/minus variants to `-`, NFKD
  (ligatures `ﬁ` -> `fi`, `²` -> `2`), the quote/dash folds again after
  NFKD (`⁻` -> U+2212 -> `-`), combining marks dropped (accents, so NFC and
  NFD compare equal) except negation overlays U+0338/U+20D2/U+20E5 (`≠`
  must not equal `=`), soft hyphen and zero-width characters dropped, then
  lowercased. Folding is for comparison only; the returned span is
  always the source's own characters.
- `normalize_with_offsets()` is the reusable normaliser with an index map back
  to the original. Characters folded to nothing have no map entry;
  `_accepted()` extends a span's end up to the next kept character, so a
  trailing NFD accent stays in the span and a ligature is never split. That
  also pulls a trailing zero-width character or soft hyphen into the span.
- With `difflib`'s default `autojunk=True`, characters that make up more than
  1% of a string of 200 or more characters are treated as junk. In prose that
  covers most letters, which skews `ratio()`, so always pass
  `autojunk=False` for character-level comparison of prose.
- Raises `TypeError` for non-strings and `ValueError` for a threshold outside
  (0, 1]. Callers that take LLM output should type-check first and treat a bad
  value as a failed validation.

Developer detail: `doc/developers/citation_system.md` → "Passage Validation".
