"""(midi_pitch + transpose) → { instrument, clicks, octave_shift } の変換(DESIGN.md §6)。

プリセット bass_harp_bell(既定):
  MIDI 30〜53 → bass / 54〜78 → harp / 79〜102 → bell(境界 54・78 は harp 優先)。
  30 未満・102 超はオクターブシフトして音域に収め、octave_shift 警告を生成する。
プリセット harp_only(素材節約):
  全音を harp の2オクターブ(MIDI 54〜78)にオクターブ折込する。
プリセット custom(ConversionSettings.custom_ranges):
  ユーザーが選んだ音色ごとに range_start_midi(その音色を使い始める元曲側のMIDI番号)
  で境界を決める。各音色自体の物理的な基準音(clicks=0の実際の音高)は変えられない
  ため、境界で音色を選んだ後、その音色自身の物理レンジへオクターブシフトする。
プリセット single_block(ConversionSettings.single_instrument):
  打楽器も含め全ノートを1つの音色(=下に置くブロック1種類)に固定する。選んだ音色が
  旋律用ならその物理レンジへオクターブ折込し、打楽器用(basedrum/snare/hat)なら
  基準音(clicks=0)に固定する(打楽器はどのプリセットでも音程の概念を持たない)。

打楽器(GM percussion map の実キー番号 → basedrum/snare/hat の3音色):
  クリック数は音程ではなく打楽器の音色そのものを鳴らすためのものなので、
  基準音(clicks=0)に固定する。オクターブシフトの概念もないため常に0。
"""

from pydantic import BaseModel

from app.models.blueprint import Warning
from app.models.settings import CustomRange
from app.services.instruments import INSTRUMENTS

PRESET_MIN = 30
PRESET_MAX = 102
HARP_MIN = 54
HARP_MAX = 78

# GM percussion map(標準キー35〜81)→ basedrum(低音・胴鳴り)/ snare(乾いた鋭い打撃・擦過音)/
# hat(金属的な高音)の3音色。未定義キーは snare にフォールバックする
PERCUSSION_INSTRUMENT_MAP: dict[int, str] = {
    35: "basedrum",  # Acoustic Bass Drum
    36: "basedrum",  # Bass Drum 1
    41: "basedrum",  # Low Floor Tom
    43: "basedrum",  # High Floor Tom
    45: "basedrum",  # Low Tom
    47: "basedrum",  # Low-Mid Tom
    48: "basedrum",  # Hi-Mid Tom
    50: "basedrum",  # High Tom
    60: "basedrum",  # Hi Bongo
    61: "basedrum",  # Low Bongo
    62: "basedrum",  # Mute Hi Conga
    63: "basedrum",  # Open Hi Conga
    64: "basedrum",  # Low Conga
    65: "basedrum",  # High Timbale
    66: "basedrum",  # Low Timbale
    37: "snare",  # Side Stick
    38: "snare",  # Acoustic Snare
    39: "snare",  # Hand Clap
    40: "snare",  # Electric Snare
    54: "snare",  # Tambourine
    58: "snare",  # Vibraslap
    69: "snare",  # Cabasa
    70: "snare",  # Maracas
    73: "snare",  # Short Guiro
    74: "snare",  # Long Guiro
    75: "snare",  # Claves
    76: "snare",  # Hi Wood Block
    77: "snare",  # Low Wood Block
    78: "snare",  # Mute Cuica
    79: "snare",  # Open Cuica
    42: "hat",  # Closed Hi-Hat
    44: "hat",  # Pedal Hi-Hat
    46: "hat",  # Open Hi-Hat
    49: "hat",  # Crash Cymbal 1
    51: "hat",  # Ride Cymbal 1
    52: "hat",  # Chinese Cymbal
    53: "hat",  # Ride Bell
    55: "hat",  # Splash Cymbal
    56: "hat",  # Cowbell
    57: "hat",  # Crash Cymbal 2
    59: "hat",  # Ride Cymbal 2
    67: "hat",  # High Agogo
    68: "hat",  # Low Agogo
    71: "hat",  # Short Whistle
    72: "hat",  # Long Whistle
    80: "hat",  # Mute Triangle
    81: "hat",  # Open Triangle
}
PERCUSSION_FALLBACK_INSTRUMENT = "snare"


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


def validate_custom_ranges(custom_ranges: list[CustomRange] | None) -> None:
    if not custom_ranges:
        raise ValueError("custom プリセットには custom_ranges の指定が必要です")
    names = [r.instrument for r in custom_ranges]
    if len(names) != len(set(names)):
        raise ValueError("custom_ranges に同じ音色を複数回指定することはできません")
    starts = [r.range_start_midi for r in custom_ranges]
    if len(starts) != len(set(starts)):
        # 同じ境界を複数の音色が持つと、境界以上の音が常に後勝ちで1音色に固定され、
        # もう一方が事実上選べなくなってしまうため拒否する
        raise ValueError("custom_ranges に同じ切り替え開始音(range_start_midi)を複数指定することはできません")
    for name in names:
        inst = INSTRUMENTS.get(name)
        if inst is None or inst.is_percussion:
            raise ValueError(f"custom_ranges に無効な音色が含まれています: {name}")


def map_custom(
    midi_pitch: int,
    custom_ranges: list[CustomRange],
    transpose_semitones: int = 0,
) -> MappedNote:
    """range_start_midi はどの音色を使うかを決める境界(元曲側のMIDI番号)であり、
    音色自体の物理的な基準音(clicks=0の実際の音高)はinstruments.pyのbase_midiで
    固定されている(音符ブロックの物理仕様上、ソフトウェアでは変更できない)。
    このため境界で音色を選んだ後、その音色自身の物理レンジへ改めてオクターブシフトする。
    """
    midi = midi_pitch + transpose_semitones
    ranges = sorted(custom_ranges, key=lambda r: r.range_start_midi)
    chosen = ranges[0]
    for r in ranges:
        if r.range_start_midi <= midi:
            chosen = r
        else:
            break
    inst = INSTRUMENTS[chosen.instrument]
    shifted, octave_shift = _shift_into_range(midi, inst.base_midi, inst.base_midi + 24)
    return MappedNote(
        instrument=chosen.instrument,
        clicks=shifted - inst.base_midi,
        octave_shift=octave_shift,
    )


def map_percussion(midi_pitch: int) -> MappedNote:
    instrument = PERCUSSION_INSTRUMENT_MAP.get(midi_pitch, PERCUSSION_FALLBACK_INSTRUMENT)
    return MappedNote(instrument=instrument, clicks=0, octave_shift=0)


def validate_single_instrument(instrument: str | None) -> None:
    if not instrument:
        raise ValueError("single_block プリセットには single_instrument の指定が必要です")
    if instrument not in INSTRUMENTS:
        raise ValueError(f"single_block に無効な音色が指定されています: {instrument}")


def map_single_instrument(
    midi_pitch: int, instrument: str, transpose_semitones: int = 0
) -> MappedNote:
    inst = INSTRUMENTS[instrument]
    if inst.is_percussion:
        return MappedNote(instrument=instrument, clicks=0, octave_shift=0)
    midi, octave_shift = _shift_into_range(
        midi_pitch + transpose_semitones, inst.base_midi, inst.max_midi
    )
    return MappedNote(instrument=instrument, clicks=midi - inst.base_midi, octave_shift=octave_shift)


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
