from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from .service import generate_report_bytes

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="parsedwg",
    description="MVP-сервис для извлечения позиций из DWG/DXF и формирования СО, ВОР и сметы.",
    version="0.1.0",
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/process")
async def process(drawing: UploadFile = File(...), note: UploadFile | None = File(None)) -> Response:
    if not drawing.filename:
        raise HTTPException(status_code=400, detail="Нужно приложить файл DWG или DXF.")

    with TemporaryDirectory() as temp_dir:
        workdir = Path(temp_dir)
        drawing_path = workdir / drawing.filename
        drawing_path.write_bytes(await drawing.read())

        note_path: Path | None = None
        if note is not None and note.filename:
            note_path = workdir / note.filename
            note_path.write_bytes(await note.read())

        try:
            payload, items = generate_report_bytes(drawing_path, note_path)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not items:
        raise HTTPException(
            status_code=422,
            detail="Не удалось распознать позиции. Проверьте подписи на чертеже и формат файла.",
        )

    filename = f"{Path(drawing.filename).stem}-report.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(content=payload, headers=headers, media_type=media_type)
