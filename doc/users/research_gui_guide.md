# Research GUI User Guide (retired)

> **Retired on 2026-10-16.** The Flet-based Research GUI (`bmlibrarian_research_gui.py`) has been
> removed from BMLibrarian, together with all other Flet applications and the `flet` dependency.
> flet 1.0 changed its event model in a way that would have required rewriting the whole Flet GUI,
> and every Flet application except the Citation lab already had a PySide6/Qt equivalent
> (remaining gaps: [ROADMAP §1](../../ROADMAP.md)).

## Use instead

```bash
uv run python bmlibrarian_qt.py
```

Then open the **Research** tab. It runs the multi-agent research workflow (query generation,
search, scoring, citation extraction, reporting, counterfactual analysis) with visual progress and a
report preview. Unlike the Flet GUI, query generation is single-model only, and there is no
citation accept/refuse review step (see [ROADMAP §1](../../ROADMAP.md)).

The command-line options of the old Flet launcher (`--auto`, `--quick`, `--max-results`,
`--score-threshold`) have no equivalent in the Qt application. For a fully non-interactive run, use
the CLI instead: `uv run python bmlibrarian_cli.py --auto "your research question"`.

## See also

- [Qt GUI User Guide](qt_gui_user_guide.md) - Research tab and all other tabs
- [Flet to Qt Migration Guide](flet_to_qt_migration_guide.md) - historical notes on the transition
