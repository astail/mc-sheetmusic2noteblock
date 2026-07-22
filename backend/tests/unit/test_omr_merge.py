"""Audiverisが誤って複数ページに分割した認識結果の結合ロジックを検証する。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from music21 import converter

from app.api.omr import _merge_mxl_pages

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _mxl_fixture() -> bytes:
    output = io.BytesIO()
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="score.musicxml" media-type="application/vnd.recordare.musicxml+xml"/></rootfiles>
</container>"""
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.writestr(
            "score.musicxml", (FIXTURES / "scale_c_major.musicxml").read_bytes()
        )
    return output.getvalue()


def test_merge_mxl_pages_offsets_each_page_by_prior_cumulative_duration(tmp_path):
    merged = _merge_mxl_pages([_mxl_fixture(), _mxl_fixture()])

    out_path = tmp_path / "merged.mxl"
    out_path.write_bytes(merged)
    score = converter.parse(out_path)

    parts = list(score.parts)
    assert len(parts) == 2  # ページごとに独立したパートとして連結される

    first_page_notes = list(parts[0].flatten().notes)
    second_page_notes = list(parts[1].flatten().notes)
    assert len(first_page_notes) == 8
    assert len(second_page_notes) == 8

    # scale_c_major.musicxml は4分音符8音(合計8拍)なので、2ページ目は+8拍分オフセットされる
    assert float(first_page_notes[0].getOffsetInHierarchy(score)) == 0.0
    assert float(second_page_notes[0].getOffsetInHierarchy(score)) == 8.0
