import json

from dwganalyzer.i18n import using_language
from dwganalyzer.models import (
    AnalysisBatch,
    DrawingSummary,
    ProcessingFailure,
)
from dwganalyzer.reporting import render_json, render_text
from dwganalyzer.services import analyze_drawing


def _batch() -> AnalysisBatch:
    analysis = analyze_drawing(DrawingSummary(source="empty.dxf"))
    return AnalysisBatch(
        input_path="drawings",
        analyses=(analysis,),
        failures=(
            ProcessingFailure(
                source="broken.dxf",
                code="drawing_read_error",
                message="Unable to read DXF drawing: broken.dxf",
            ),
        ),
    )


def test_renders_english_text() -> None:
    report = render_text(_batch())

    assert "Drawings discovered: 2" in report
    assert "Drawing: empty.dxf" in report
    assert "Drawing contains no entities." in report
    assert "Failures:" in report


def test_renders_russian_text() -> None:
    with using_language("ru"):
        report = render_text(_batch())

    assert "Найдено чертежей: 2" in report
    assert "Чертёж: empty.dxf" in report
    assert "Чертёж не содержит объектов." in report
    assert "Ошибки:" in report


def test_renders_stable_json() -> None:
    with using_language("ru"):
        payload = json.loads(render_json(_batch()))

    assert payload["schema_version"] == 1
    assert payload["summary"] == {
        "discovered_count": 2,
        "failure_count": 1,
        "successful_count": 1,
    }
    assert payload["drawings"][0]["findings"] == [
        {"code": "empty_drawing"}
    ]
    assert payload["failures"] == [
        {"code": "drawing_read_error", "source": "broken.dxf"}
    ]
    assert "message" not in payload["failures"][0]
