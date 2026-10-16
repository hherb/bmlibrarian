# Configuration GUI User Guide (retired)

> **Retired.** The Flet-based Configuration GUI launcher (`bmlibrarian_config_gui.py`) was deleted on
> 2025-11-13; the remaining Flet applications and the `flet` dependency were removed on 2026-10-16.
> flet 1.0 changed its event model in a way that would have required rewriting the whole Flet GUI,
> and every Flet application except the Citation lab already had a PySide6/Qt equivalent
> (remaining gaps: [ROADMAP §1](../../ROADMAP.md)).

## Use instead

```bash
uv run python bmlibrarian_qt.py
```

Then open the **Configuration** or **Settings** tab to manage agent models, parameters, Ollama and
database settings. Configuration is still stored in `~/.bmlibrarian/config.json` (or in the database
for authenticated users), so existing configuration files keep working unchanged.

## See also

- [Qt GUI User Guide](qt_gui_user_guide.md) - Configuration tab and all other tabs
- [Configuration Guide](configuration_guide.md) - configuration file format and options
- [Flet to Qt Migration Guide](flet_to_qt_migration_guide.md) - historical notes on the transition
