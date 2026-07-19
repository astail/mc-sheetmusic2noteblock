"""score_id 発行と data/scores/{score_id}/ 配下のファイル管理(DESIGN.md §3)。

- original.<ext>: アップロードされた元ファイル
- parsed.json: パースサマリ(ScoreSummary)
- blueprint.json: 最後に生成した設計書(Blueprint)
"""

import re
import uuid
from pathlib import Path

from app import config
from app.models.blueprint import Blueprint
from app.services.parser import ScoreSummary

_SCORE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _validate_score_id(score_id: str) -> str:
    # パストラバーサル防止: UUID hex 以外は拒否
    if not _SCORE_ID_RE.fullmatch(score_id):
        raise ValueError(f"不正な score_id です: {score_id!r}")
    return score_id


def _scores_root() -> Path:
    # テストで config.DATA_DIR を差し替えられるよう呼び出し時に参照する
    return Path(config.DATA_DIR) / "scores"


def score_dir(score_id: str) -> Path:
    return _scores_root() / _validate_score_id(score_id)


def create_score(original_filename: str, content: bytes) -> str:
    """score_id を発行し original.<ext> を保存する。"""
    score_id = uuid.uuid4().hex
    ext = Path(original_filename).suffix.lower()
    directory = _scores_root() / score_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"original{ext}").write_bytes(content)
    return score_id


def score_exists(score_id: str) -> bool:
    return score_dir(score_id).is_dir()


def original_path(score_id: str) -> Path | None:
    directory = score_dir(score_id)
    if not directory.is_dir():
        return None
    matches = sorted(directory.glob("original.*"))
    return matches[0] if matches else None


def save_parsed(score_id: str, summary: ScoreSummary) -> None:
    (score_dir(score_id) / "parsed.json").write_text(
        summary.model_dump_json(), encoding="utf-8"
    )


def load_parsed(score_id: str) -> ScoreSummary | None:
    path = score_dir(score_id) / "parsed.json"
    if not path.is_file():
        return None
    return ScoreSummary.model_validate_json(path.read_text(encoding="utf-8"))


def save_blueprint(score_id: str, blueprint: Blueprint) -> None:
    (score_dir(score_id) / "blueprint.json").write_text(
        blueprint.model_dump_json(), encoding="utf-8"
    )


def load_blueprint(score_id: str) -> Blueprint | None:
    path = score_dir(score_id) / "blueprint.json"
    if not path.is_file():
        return None
    return Blueprint.model_validate_json(path.read_text(encoding="utf-8"))
