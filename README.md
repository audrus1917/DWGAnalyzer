# DWGAnalyzer

DWGAnalyzer is a Python application for inspecting and analyzing DWG/DXF
drawings. The project is being rebuilt from a legacy prototype with a smaller,
English-first architecture and GNU gettext localization.

The current migration stage provides the project foundation and input layer.
DWGAnalyzer can discover DWG/DXF files in files, directories, and ZIP archives,
and can load drawings through `ezdxf`. Drawing entity parsing and analysis are
intentionally not implemented yet.

## Supported inputs

- DXF files are read directly through `ezdxf`.
- DWG files require ODA File Converter to be installed and available to
  `ezdxf`.
- Directories are scanned recursively in deterministic order.
- ZIP archives may contain DWG and DXF files. Archive members are validated for
  path traversal, encryption, symbolic links, excessive size, and suspicious
  compression ratios before extraction.

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
