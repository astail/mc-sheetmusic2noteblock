"""(midi_pitch + transpose) → { instrument, clicks, octave_shift } の変換(DESIGN.md §6)。

プリセット bass_harp_bell(既定):
  MIDI 30〜53 → bass / 54〜78 → harp / 79〜102 → bell(境界 54・78 は harp 優先)。
  30 未満・102 超はオクターブシフトして音域に収め、octave_shift 警告を生成する。
プリセット harp_only(素材節約):
  全音を harp の2オクターブ(MIDI 54〜78)にオクターブ折込する。
"""

from pydantic import BaseModel

from app.models.blueprint import Warning
from app.services.instruments import INSTRUMENTS

PRESET_MIN = 30
PRESET_MAX = 102
HARP_MIN = 54
HARP_MAX = 78


class MappedNote(BaseModel):
    instrument: str
    clicks: int  # 0〜24
    octave_shift: int  # 音域に収めるためにシフトしたオクターブ数(+は上、-は下)


def _instrument_for(midi: int) -> str:
    # 境界 54・78 は harp 優先
    if midi <= 53:
        return "bass"
    if midi <= 78:
        return "harp"
    return "bell"


def _shift_into_range(midi: int, low: int, high: int) -> tuple[int, int]:
    octave_shift = 0
    while midi < low:
        midi += 12
        octave_shift += 1
    while midi > high:
        midi -= 12
        octave_shift -= 1
    return midi, octave_shift


def map_pitch(
    midi_pitch: int,
    preset: str = "bass_harp_bell",
    transpose_semitones: int = 0,
) -> MappedNote:
    if preset not in ("bass_harp_bell", "harp_only"):
        raise ValueError(f"未対応のプリセットです: {preset}")

    midi = midi_pitch + transpose_semitones
    if preset == "harp_only":
        midi, octave_shift = _shift_into_range(midi, HARP_MIN, HARP_MAX)
        instrument = "harp"
    else:
        midi, octave_shift = _shift_into_range(midi, PRESET_MIN, PRESET_MAX)
        instrument = _instrument_for(midi)
    clicks = midi - INSTRUMENTS[instrument].base_midi
    return MappedNote(instrument=instrument, clicks=clicks, octave_shift=octave_shift)


def build_octave_shift_warning(mapped: list[MappedNote]) -> Warning | None:
    """シフトが発生した音があれば octave_shift 警告を1件にまとめて返す。"""
    shifts = [m.octave_shift for m in mapped if m.octave_shift != 0]
    if not shifts:
        return None
    lo, hi = min(shifts), max(shifts)
    range_text = f"{lo:+d}" if lo == hi else f"{lo:+d}〜{hi:+d}"
    return Warning(
        type="octave_shift",
        message=f"{len(shifts)}音を音域に収めるため {range_text} オクターブシフトしました",
    )
