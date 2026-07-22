"""設計書 API(DESIGN.md §5)。変換パイプラインをここで結線する。

- POST /api/scores/{score_id}/blueprint: body=ConversionSettings → 変換実行 + 永続化
- GET  /api/scores/{score_id}/blueprint: 最後に生成した設計書
"""

from fastapi import APIRouter, HTTPException

from app import storage
from app.models.blueprint import Blueprint
from app.models.settings import ConversionSettings
from app.services.blueprint_builder import build_blueprint_parts
from app.services.hand_split import split_hands
from app.services.layout import build_layout
from app.services.materials import count_materials
from app.services.parser import parse_score
from app.services.quantizer import quantize_beats, quantize_seconds

router = APIRouter(tags=["blueprints"])


@router.post("/scores/{score_id}/blueprint", response_model=Blueprint)
def create_blueprint(score_id: str, settings: ConversionSettings) -> Blueprint:
    try:
        original = storage.original_path(score_id)
        summary = storage.load_parsed(score_id)
    except ValueError:
        original = summary = None
    if original is None or summary is None:
        raise HTTPException(status_code=404, detail="score が見つかりません")

    try:
        parsed = parse_score(original, measure_range=settings.measure_range)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if settings.mode == "seconds":
        result = quantize_seconds(parsed.events, tempo_scale=settings.tempo_scale)
        ticks_per_quarter = None
    else:
        result = quantize_beats(
            parsed.events,
            settings.ticks_per_quarter,
            has_tempo_changes=summary.has_tempo_changes,
        )
        ticks_per_quarter = settings.ticks_per_quarter

    hands = split_hands(
        [q.event for q in result.events],
        track_names={t.index: t.name for t in summary.tracks},
        hand_assignment=settings.hand_assignment,
    )
    source_file = storage.load_source_filename(score_id) or original.name
    try:
        meta, steps, build_warnings = build_blueprint_parts(
            result.events,
            hands,
            title=summary.title or source_file,
            source_file=source_file,
            original_bpm=summary.original_bpm,
            ticks_per_quarter=ticks_per_quarter,
            effective_bpm=result.effective_bpm,
            quantization_stats=result.stats,
            preset=settings.instrument_preset,
            transpose_semitones=settings.transpose_semitones,
            custom_ranges=settings.custom_ranges,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    blueprint = Blueprint(
        meta=meta,
        steps=steps,
        materials=count_materials(steps),
        warnings=result.warnings + build_warnings,
        layout=build_layout(steps),
    )
    storage.save_blueprint(score_id, blueprint)
    return blueprint


@router.get("/scores/{score_id}/blueprint", response_model=Blueprint)
def get_blueprint(score_id: str) -> Blueprint:
    try:
        blueprint = storage.load_blueprint(score_id)
    except ValueError:
        blueprint = None
    if blueprint is None:
        raise HTTPException(status_code=404, detail="設計書がまだ生成されていません")
    return blueprint
