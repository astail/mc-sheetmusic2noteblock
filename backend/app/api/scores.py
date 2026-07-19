"""POST /api/scores: multipart アップロード + 即パースしてサマリ返却(DESIGN.md §5)。"""

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app import storage
from app.services.parser import SUPPORTED_EXTENSIONS, ScoreSummary, parse_score
from app.services.quantizer import recommend_tpq

router = APIRouter(tags=["scores"])

OMR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


class UploadScoreResponse(BaseModel):
    score_id: str
    summary: ScoreSummary
    recommended_tpq: int | None = None  # 原曲 BPM が取れない場合は None


@router.post("/scores", response_model=UploadScoreResponse)
def upload_score(file: UploadFile) -> UploadScoreResponse:
    # 同期 def にすることで FastAPI が threadpool で実行し、
    # 数秒かかる music21 パース中も event loop(/healthz 等)をブロックしない
    ext = Path(file.filename or "").suffix.lower()
    if ext in OMR_EXTENSIONS:
        raise HTTPException(
            status_code=501,
            detail="PDF/画像のアップロード(OMR)は未対応です(Phase 4 で対応予定)",
        )
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"未対応の拡張子です: {ext or '(なし)'}(対応: .mid / .musicxml / .mxl)",
        )

    content = file.file.read()
    score_id = storage.create_score(file.filename, content)
    try:
        parsed = parse_score(storage.original_path(score_id))
    except Exception as exc:
        # パースできないファイルは保存物ごと破棄する
        shutil.rmtree(storage.score_dir(score_id), ignore_errors=True)
        raise HTTPException(
            status_code=422, detail=f"楽譜ファイルを解析できませんでした: {exc}"
        ) from exc

    storage.save_parsed(score_id, parsed.summary)
    bpm = parsed.summary.original_bpm
    return UploadScoreResponse(
        score_id=score_id,
        summary=parsed.summary,
        recommended_tpq=recommend_tpq(bpm) if bpm is not None else None,
    )
