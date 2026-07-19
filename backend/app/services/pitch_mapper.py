"""(midi_pitch + transpose) → { instrument, clicks, octave_shift } の変換(DESIGN.md §6)。

プリセット bass_harp_bell(既定):
  MIDI 30〜53 → bass / 54〜78 → harp / 79〜102 → bell(境界 54・78 は harp 優先)。
  30 未満・102 超はオクターブシフトして音域に収め、octave_shift 警告を生成する。
"""

from pydantic import BaseModel

from app.models.blueprint import Warning
from app.services.instruments import INSTRUMENTS

PRESET_MIN = 30
PRESET_MAX = 102


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


def map_pitch(
    midi_pitch: int,
    preset: str = "bass_harp_bell",
    transpose_semitones: int = 0,
) -> MappedNote:
    if preset != "bass_harp_bell":
        raise ValueError(f"未対応のプリセットです: {preset}")

    midi = midi_pitch + transpose_semitones
    octave_shift = 0
    while midi < PRESET_MIN:
        midi += 12
        octave_shift += 1
    while midi > PRESET_MAX:
        midi -= 12
        octave_shift -= 1

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
