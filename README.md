# DWGAnalyzer

DWGAnalyzer is a Python application for inspecting and analyzing DWG/DXF
drawings. The project is being rebuilt from a legacy prototype with a smaller,
English-first architecture and GNU gettext localization.

The current migration stage provides only the project foundation: package
metadata, a CLI entry point, core error types, minimal domain models, and the
localization boundary. Drawing discovery and parsing are intentionally not
implemented yet.

## Development setup

DWGAnalyzer requires Python 3.12 or newer.

```bash
python -m venv .venv
./.venv/bin/pip install --editable ".[dev]"
```

Run the focused test suite:

```bash
./.venv/bin/pytest -q
```

Display the current CLI help:

```bash
./.venv/bin/dwganalyzer
```

## Localization

English is the source and fallback language. Russian translations use the
`dwganalyzer` gettext domain and live under
`src/dwganalyzer/i18n/locale/ru/LC_MESSAGES/`.

Compile the Russian catalog after editing it:

```bash
msgfmt \
  src/dwganalyzer/i18n/locale/ru/LC_MESSAGES/dwganalyzer.po \
  --output-file=src/dwganalyzer/i18n/locale/ru/LC_MESSAGES/dwganalyzer.mo
```
