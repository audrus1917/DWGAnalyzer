from pathlib import Path
from tempfile import TemporaryDirectory

from ezdxf.filemanagement import new

from parsedwg.dxf_dxf_info import iter_entity_descriptions


def test_iter_entity_descriptions_includes_type_position_and_text():
    with TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / "entities.dxf"

        doc = new()
        modelspace = doc.modelspace()
        modelspace.add_line((0, 0), (10, 10))
        modelspace.add_text("Марка 1", dxfattribs={"insert": (2, 3, 0)})
        modelspace.add_mtext("Примечание").set_location((4, 5, 0))
        doc.layout("Layout1").add_circle((6, 7, 0), radius=2)
        doc.saveas(source_path)

        rows = list(iter_entity_descriptions(source_path))

        assert any(
            "type=LINE" in row
            and "start=(0.00, 0.00, 0.00)" in row
            and "end=(10.00, 10.00, 0.00)" in row
            for row in rows
        )
        assert any(
            "type=TEXT" in row
            and "insert=(2.00, 3.00, 0.00)" in row
            and "text='Марка 1'" in row
            for row in rows
        )
        assert any(
            "type=MTEXT" in row
            and "insert=(4.00, 5.00, 0.00)" in row
            and "text='Примечание'" in row
            for row in rows
        )
        assert any(
            "[Layout1]" in row
            and "type=CIRCLE" in row
            and "center=(6.00, 7.00, 0.00)" in row
            for row in rows
        )


def test_iter_entity_descriptions_modelspace_only_skips_layouts():
    with TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / "entities.dxf"

        doc = new()
        doc.modelspace().add_text("Текст модели", dxfattribs={"insert": (1, 2, 0)})
        doc.layout("Layout1").add_text("Текст листа", dxfattribs={"insert": (8, 9, 0)})
        doc.saveas(source_path)

        rows = list(iter_entity_descriptions(source_path, modelspace_only=True))

        assert len(rows) == 1
        assert "[Model]" in rows[0]
        assert "Текст модели" in rows[0]
        assert "Текст листа" not in rows[0]
