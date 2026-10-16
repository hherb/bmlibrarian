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
- `exact` is True when only case and whitespace differ. Use it rather than
  `similarity == 1.0`. Exact spans may start or end mid-word; fuzzy spans
  always start and end on word boundaries.
- `similarity` is `SequenceMatcher(autojunk=False).ratio()` on normalised text
  (lowercase, collapsed whitespace), reported even on rejection. It is 0.0
  when no candidate location was found at all or the passage is too long to
  reach the threshold (`fits_text()`), so 0.0 means "not found", not a near
  miss.
- No Unicode normalisation beyond lowercasing: NFD vs NFC accents and curly
  vs straight quotes count as edits, which matters for short passages.
- `normalize_with_offsets()` is the reusable normaliser with an index map back
  to the original.
- With `difflib`'s default `autojunk=True`, characters that make up more than
  1% of a string of 200 or more characters are treated as junk. In prose that
  covers most letters, which skews `ratio()`, so always pass
  `autojunk=False` for character-level comparison of prose.
- Raises `TypeError` for non-strings and `ValueError` for a threshold outside
  (0, 1]. Callers that take LLM output should type-check first and treat a bad
  value as a failed validation.

Developer detail: `doc/developers/citation_system.md` → "Passage Validation".
