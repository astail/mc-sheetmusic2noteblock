"""スコア API(DESIGN.md §5)。

- POST /api/scores: multipart アップロード + 即パースしてサマリ返却
- GET /api/scores/{score_id}: 保存済みサマリ返却
"""

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app import storage
from app.services.parser import SUPPORTED_EXTENSIONS, ScoreSummary, parse_score
from app.services.quantizer import recommend_tpq

router = APIRouter(tags=["scores"])

OMR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


class ScoreResponse(BaseModel):
    score_id: str
    summary: ScoreSummary
    recommended_tpq: int | None = None  # 原曲 BPM が取れない場合は None


def _score_response(score_id: str, summary: ScoreSummary) -> ScoreResponse:
    bpm = summary.original_bpm
    return ScoreResponse(
        score_id=score_id,
        summary=summary,
        recommended_tpq=recommend_tpq(bpm) if bpm is not None else None,
    )


@router.post("/scores", response_model=ScoreResponse)
def upload_score(file: UploadFile) -> ScoreResponse:
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
    return _score_response(score_id, parsed.summary)


@router.get("/scores/{score_id}", response_model=ScoreResponse)
def get_score(score_id: str) -> ScoreResponse:
    try:
        summary = storage.load_parsed(score_id)
    except ValueError:
        # 不正な形式の id は存在しない id と同様に扱う
        summary = None
    if summary is None:
        raise HTTPException(status_code=404, detail="score が見つかりません")
    return _score_response(score_id, summary)
