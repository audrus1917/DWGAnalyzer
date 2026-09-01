# DWGAnalyzer

DWGAnalyzer is a Python application for inspecting and analyzing DWG/DXF
drawings. The project is being rebuilt from a legacy prototype with a smaller,
English-first architecture and GNU gettext localization.

The current migration stage provides the project foundation, input layer,
parser-independent drawing summaries, and structural drawing analysis.
DWGAnalyzer can discover DWG/DXF files in files, directories, and ZIP archives,
load drawings through `ezdxf`, and extract layout, layer, block, text, and block
reference metadata. It can build inventory counts, inspect block reachability,
detect inconsistent references, and produce localized text or stable JSON
reports from the command line.

## Supported inputs

- DXF files are read directly through `ezdxf`.
- DWG files require ODA File Converter to be installed and available to
  `ezdxf`.
- Directories are scanned recursively in deterministic order.
- ZIP archives may contain DWG and DXF files. Archive members are validated for
  path traversal, encryption, symbolic links, excessive size, and suspicious
  compression ratios before extraction.

## Architecture

- `dwganalyzer.io` discovers inputs, extracts archive members, and loads
  drawings.
- `dwganalyzer.parsers` converts loaded drawings into stable domain summaries.
- `dwganalyzer.services` coordinates processing and analyzes summaries without
  depending on `ezdxf` in the analysis layer.
- `dwganalyzer.reporting` renders localized text and non-localized JSON.
- `dwganalyzer.models` contains immutable data shared across those boundaries.
- `dwganalyzer.i18n` is the single gettext initialization point.

Parser output intentionally contains no `ezdxf` entities. Geometry processing,
persistence, and visualization belong to later migration stages. Analysis
findings use stable machine-readable codes; only their text representation is
localized at the reporting boundary.

## Command-line usage

Analyze one drawing, a directory tree, or a ZIP archive:

```bash
dwganalyzer analyze path/to/drawing.dxf
dwganalyzer analyze path/to/drawings/
dwganalyzer analyze path/to/drawings.zip
```

Request JSON for machine processing or select Russian text output:

```bash
dwganalyzer analyze path/to/drawings/ --format json
dwganalyzer analyze path/to/drawing.dxf --language ru
```

Text reports include aggregate status, per-drawing inventory, block usage, and
structural findings. JSON field names, error codes, and finding codes are
stable and are never translated; `schema_version` identifies the JSON contract.
The command exits with status `0` when all discovered drawings are analyzed and
status `1` on an input or per-drawing processing failure. Invalid CLI arguments
use the standard argparse status `2`.

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
./.venv/bin/dwganalyzer analyze --help
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

To update source messages, create a temporary template and merge it into the
catalog:

```bash
find src/dwganalyzer -name '*.py' -print | sort > /tmp/dwganalyzer-i18n-files
xgettext --language=Python --keyword=_ --keyword=ngettext:1,2 \
  --files-from=/tmp/dwganalyzer-i18n-files \
  --output=/tmp/dwganalyzer.pot
msgmerge --update \
  src/dwganalyzer/i18n/locale/ru/LC_MESSAGES/dwganalyzer.po \
  /tmp/dwganalyzer.pot
```

To add another language, initialize its catalog from the same template, place
it below `src/dwganalyzer/i18n/locale/<language>/LC_MESSAGES/`, translate it,
and compile it with `msgfmt`:

```bash
msginit --input=/tmp/dwganalyzer.pot --locale=de \
  --output-file=src/dwganalyzer/i18n/locale/de/LC_MESSAGES/dwganalyzer.po
```
