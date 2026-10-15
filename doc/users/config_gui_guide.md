# Configuration GUI User Guide (retired)

> **Retired on 2026-10-16.** The Flet-based Configuration GUI (`bmlibrarian_config_gui.py`) has been
> removed from BMLibrarian, together with all other Flet applications and the `flet` dependency.
> flet 1.0 changed its event model in a way that would have required rewriting the whole Flet GUI,
> and every Flet application already had a PySide6/Qt equivalent.

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
