from pathlib import Path

import ezdxf

from dwganalyzer.services import analyze_path


def _write_dxf(path: Path) -> None:
    drawing = ezdxf.new()
    drawing.modelspace().add_line((0, 0), (10, 10))
    drawing.saveas(path)


def test_analyzes_discovered_drawings(tmp_path: Path) -> None:
    _write_dxf(tmp_path / "b.dxf")
    _write_dxf(tmp_path / "a.dxf")

    batch = analyze_path(tmp_path)

    assert batch.discovered_count == 2
    assert [Path(item.source).name for item in batch.analyses] == [
        "a.dxf",
        "b.dxf",
    ]
    assert [item.entity_count for item in batch.analyses] == [1, 1]
    assert batch.failures == ()


def test_continues_after_drawing_error(tmp_path: Path) -> None:
    _write_dxf(tmp_path / "valid.dxf")
    broken = tmp_path / "broken.dxf"
    broken.write_text("not a DXF", encoding="utf-8")

    batch = analyze_path(tmp_path)

    assert batch.discovered_count == 2
    assert len(batch.analyses) == 1
    assert len(batch.failures) == 1
    assert batch.failures[0].source == str(broken)
    assert batch.failures[0].code == "drawing_read_error"
    assert "Unable to read DXF drawing" in batch.failures[0].message
