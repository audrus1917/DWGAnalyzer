from pathlib import Path

from parsedwg.docs_ingest import _compute_md5_hex, _discover_documents


def test_discover_documents_recursively_collects_supported_files(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    nested = root / "nested"
    nested.mkdir(parents=True)

    (root / "a.docx").write_bytes(b"stub")
    (nested / "b.xlsx").write_bytes(b"stub")
    (nested / "c.csv").write_text("name;qty\nКабель;120\n", encoding="utf-8")
    (nested / "ignore.txt").write_text("x", encoding="utf-8")

    files = _discover_documents(root)

    assert [path.name for path in files] == ["a.docx", "b.xlsx", "c.csv"]


def test_compute_md5_hex_returns_32_char_hash(tmp_path: Path) -> None:
    source = tmp_path / "sample.docx"
    source.write_bytes(b"abc")

    digest = _compute_md5_hex(source)

    assert digest == "900150983cd24fb0d6963f7d28e17f72"