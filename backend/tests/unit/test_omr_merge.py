"""Audiverisが誤って複数ページに分割した認識結果の結合ロジックを検証する。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from music21 import converter

from app.api.omr import _merge_mxl_pages
from app.services.hand_split import split_hands
from app.services.parser import parse_score

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _wrap_as_mxl(musicxml_bytes: bytes) -> bytes:
    output = io.BytesIO()
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="score.musicxml" media-type="application/vnd.recordare.musicxml+xml"/></rootfiles>
</container>"""
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("score.musicxml", musicxml_bytes)
    return output.getvalue()


def _mxl_fixture() -> bytes:
    return _wrap_as_mxl((FIXTURES / "scale_c_major.musicxml").read_bytes())


def test_merge_mxl_pages_offsets_each_page_by_prior_cumulative_duration(tmp_path):
    merged = _merge_mxl_pages([_mxl_fixture(), _mxl_fixture()])

    out_path = tmp_path / "merged.mxl"
    out_path.write_bytes(merged)
    score = converter.parse(out_path)

    parts = list(score.parts)
    # 各ページ1パートずつ(同じ並び順)なので、同じ声部の続きとして1パートに統合される
    assert len(parts) == 1

    notes = list(parts[0].flatten().notes)
    assert len(notes) == 16  # 8音のフィクスチャ x 2ページ分がすべて含まれる

    # scale_c_major.musicxml は4分音符8音(合計8拍)なので、2ページ目は+8拍分オフセットされる
    assert float(notes[0].getOffsetInHierarchy(score)) == 0.0
    assert float(notes[8].getOffsetInHierarchy(score)) == 8.0


def test_merge_mxl_pages_does_not_split_a_single_voice_into_fake_hands(tmp_path):
    # 実際のバグ: 1段譜(単旋律。ボーカル譜等)の楽譜が複数ページに誤認識された場合、
    # 各ページのパートをそのまま独立したパートとして連結すると、hand_split の
    # 「未解決トラックがちょうど2本なら順序で右手/左手を割り当てる」フォールバックが
    # 誤発火し、単に「前半のページ」「後半のページ」というだけで右手/左手に
    # 分かれてしまっていた(実際には手の区別が存在しない同一の声部)。
    # パートをページ間で同じ並び順のものへ統合することで、1パートのままになり
    # この誤ったフォールバックが発火しないことを確認する
    merged = _merge_mxl_pages([_mxl_fixture(), _mxl_fixture()])

    out_path = tmp_path / "merged.mxl"
    out_path.write_bytes(merged)
    parsed = parse_score(out_path)

    assert len(parsed.summary.tracks) == 1
    hands = split_hands(
        parsed.events, track_names={t.index: t.name for t in parsed.summary.tracks}
    )
    # 単一トラックなので hand_split は順序フォールバック(④、誤って前半/後半で
    # 右手/左手に分かれてしまうバグの原因だった)ではなく音域フォールバック(⑤)になる。
    # scale_c_major は C4〜C5 で全音が右手側の境界値以上なので、全音が right になる
    # (前半8音=right・後半8音=leftというページ単位の誤分割にはならない)
    assert hands == ["right"] * 16


def test_merge_mxl_pages_keeps_hand_info_across_the_musicxml_export_roundtrip(tmp_path):
    # 実際のバグ: Audiverisが1枚の両手ピアノ譜を2ページと誤認識した場合、各ページは
    # それぞれ右手(Staff1)/左手(Staff2)のパートを持つ。MusicXML書き出し時に
    # part.idは新しく採番され直され元のstaff情報("...-StaffN")が失われるため、
    # staff番号をpartName("右手"/"左手")に変換して引き継がないと、結合後に
    # hand_split が右手/左手を区別できなくなる
    twinkle_both_hands = _wrap_as_mxl(
        (FIXTURES / "twinkle_both_hands.musicxml").read_bytes()
    )
    merged = _merge_mxl_pages([twinkle_both_hands, twinkle_both_hands])

    out_path = tmp_path / "merged.mxl"
    out_path.write_bytes(merged)
    parsed = parse_score(out_path)

    # 各ページとも(右手, 左手)の2パートで並び順が同じなので、ページをまたいで
    # 右手同士・左手同士がそれぞれ1つのパートに統合され、合計2トラックになる
    assert len(parsed.summary.tracks) == 2
    names = [t.name for t in parsed.summary.tracks]
    assert names == ["右手", "左手"]

    hands = split_hands(
        parsed.events, track_names={t.index: t.name for t in parsed.summary.tracks}
    )
    events_by_track: dict[int, list] = {}
    for event, hand in zip(parsed.events, hands):
        events_by_track.setdefault(event.track_index, []).append(hand)
    for track in parsed.summary.tracks:
        expected = "right" if track.name == "右手" else "left"
        assert all(h == expected for h in events_by_track[track.index])
    # 右手・左手それぞれ、両ページ分(twinkle_both_handsの14+14, 12+12)が含まれる
    assert len(events_by_track[0]) == 28
    assert len(events_by_track[1]) == 24
