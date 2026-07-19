"""NoteEvent に hand("right" | "left" | "other")を付与する(docs/DESIGN.md §6)。

優先順のフォールバック:
  ⓪ ConversionSettings.hand_assignment("track_N" キー)による上書き("ignore" は "other")
  ① MusicXML の staff(1=右手, 2=左手, 3以上=other)
  ② トラック名ヒューリスティック("left" / "right" / "L.H." / "R.H." / 右手 / 左手 等)
  ③ 未解決トラックがちょうど2本なら順序で割当(先=右手, 後=左手)
  ④ それ以外(単一トラック等)は C4(MIDI 60)境界で音域分割
"""

import re
from typing import Literal

from app.models.events import NoteEvent

Hand = Literal["right", "left", "other"]

C4_MIDI = 60


# "Upright Piano" 等の部分一致を避けるため単語境界付きで判定する
_RIGHT_NAME_RE = re.compile(r"\bright\b|\br\.?h\b|右手", re.IGNORECASE)
_LEFT_NAME_RE = re.compile(r"\bleft\b|\bl\.?h\b|左手", re.IGNORECASE)


def _hand_from_name(name: str | None) -> Hand | None:
    if not name:
        return None
    if _RIGHT_NAME_RE.search(name):
        return "right"
    if _LEFT_NAME_RE.search(name):
        return "left"
    return None


def split_hands(
    events: list[NoteEvent],
    track_names: dict[int, str | None] | None = None,
    hand_assignment: dict[str, str] | None = None,
) -> list[Hand]:
    """events と同順の hand リストを返す。"""
    track_names = track_names or {}
    hand_assignment = hand_assignment or {}
    track_indices = sorted({e.track_index for e in events})

    override_hand: dict[int, Hand] = {}
    name_hand: dict[int, Hand] = {}
    for track in track_indices:
        override = hand_assignment.get(f"track_{track}")
        if override in ("right", "left"):
            override_hand[track] = override
        elif override == "ignore":
            override_hand[track] = "other"
        else:
            from_name = _hand_from_name(track_names.get(track))
            if from_name is not None:
                name_hand[track] = from_name

    # ③ の対象: 上書き・トラック名・staff のどれでも解決しないトラック
    has_staff = {e.track_index for e in events if e.staff_number is not None}
    fallback_tracks = [
        t
        for t in track_indices
        if t not in override_hand and t not in name_hand and t not in has_staff
    ]
    order_hand: dict[int, Hand] = {}
    if len(fallback_tracks) == 2:
        order_hand[fallback_tracks[0]] = "right"
        order_hand[fallback_tracks[1]] = "left"

    hands: list[Hand] = []
    for event in events:
        track = event.track_index
        if track in override_hand:
            hands.append(override_hand[track])
        elif event.staff_number == 1:
            hands.append("right")
        elif event.staff_number == 2:
            hands.append("left")
        elif event.staff_number is not None:
            hands.append("other")
        elif track in name_hand:
            hands.append(name_hand[track])
        elif track in order_hand:
            hands.append(order_hand[track])
        else:
            hands.append("right" if event.midi_pitch >= C4_MIDI else "left")
    return hands
