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
    description="MVP service for extracting items from DWG/DXF and generating specification, work list, and estimate outputs.",
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
    """Process uploaded files and return an Excel report.

    Raises:
        HTTPException: If the drawing file is missing, the input is invalid,
            or no items could be recognized.
    """
    if not drawing.filename:
        raise HTTPException(status_code=400, detail="Attach a DWG or DXF file.")

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
            detail="Could not recognize any items. Check drawing labels and the input file format.",
        )

    filename = f"{Path(drawing.filename).stem}-report.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(content=payload, headers=headers, media_type=media_type)
