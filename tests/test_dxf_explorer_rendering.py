from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from ezdxf.filemanagement import new

from parsedwg.cli import DXFExplorer


def test_export_block_png_writes_png_file() -> None:
    pytest.importorskip("matplotlib")

    with TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / "block.dxf"

        doc = new()
        block = doc.blocks.new("PNG_BLOCK")
        block.add_line((0, 0), (10, 0))
        block.add_circle((5, 5), radius=2)
        doc.saveas(source_path)

        explorer = DXFExplorer(source_path)
        output_path = explorer.export_block_png("PNG_BLOCK")

        assert output_path.exists()
        assert output_path.suffix.lower() == ".png"
        assert output_path.stat().st_size > 0


def test_export_block_svg_writes_svg_file() -> None:
    pytest.importorskip("matplotlib")

    with TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / "block.dxf"

        doc = new()
        block = doc.blocks.new("SVG_BLOCK")
        block.add_line((0, 0), (10, 0))
        block.add_circle((5, 5), radius=2)
        doc.saveas(source_path)

        explorer = DXFExplorer(source_path)
        output_path = explorer.export_block_svg("SVG_BLOCK")

        assert output_path.exists()
        assert output_path.suffix.lower() == ".svg"
        assert output_path.stat().st_size > 0


def test_describe_entity_includes_point_coordinates_and_insert_block_name() -> None:
    doc = new()
    block = doc.blocks.new("MARKER")
    block.add_circle((0, 0, 0), radius=1)

    point = doc.modelspace().add_point((1, 2, 3))
    insert = doc.modelspace().add_blockref("MARKER", (10, 20, 0))

    point_params = DXFExplorer._get_entity_params(point)
    insert_params = DXFExplorer._get_entity_params(insert)

    assert point_params["location"] == "(1.00, 2.00, 3.00)"
    assert insert_params["block"] == "MARKER"
    assert "location=(1.00, 2.00, 3.00)" in DXFExplorer._describe_entity(point_params)
    assert "block='MARKER'" in DXFExplorer._describe_entity(insert_params)