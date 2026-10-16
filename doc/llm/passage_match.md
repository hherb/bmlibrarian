# Locating quoted passages in source text

Use `bmlibrarian.utils.passage_match.find_passage(passage, text, min_similarity)`
whenever an LLM "quotes" a source and you need the source's own wording or
span (citation validation, highlighting, evidence checks). Do not hand-roll a
`SequenceMatcher` sliding window. The old one in `CitationFinderAgent` cost
O(P²·A) `SequenceMatcher` calls (31 s per 1 kB abstract) and mis-mapped spans.

- Returns `PassageMatch(similarity, start, end, text)`; `matched` is True when
  `similarity >= min_similarity`. `text == original[start:end]`, with the
  original case and whitespace.
- `similarity` is `SequenceMatcher(autojunk=False).ratio()` on normalised text
  (lowercase, collapsed whitespace), reported even on rejection.
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
