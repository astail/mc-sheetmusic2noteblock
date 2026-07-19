"""パース結果の中間表現 NoteEvent。"""

from typing import Literal

from pydantic import BaseModel


class NoteEvent(BaseModel):
    offset_ql: float  # 曲頭からのオフセット(quarterLength)
    offset_seconds: float | None = None  # テンポマップ適用後の実秒(seconds モード用)
    duration_ql: float
    midi_pitch: int
    part_id: str
    staff_number: int | None = None
    track_index: int
    channel: int | None = None
    measure: int | None = None
    beat: float | None = None
    tie: Literal["start", "stop", "continue"] | None = None
