"""score_id 発行と data/scores/{score_id}/ 配下のファイル管理(DESIGN.md §3)。

- original.<ext>: アップロードされた元ファイル
- parsed.json: パースサマリ(ScoreSummary)
- blueprint.json: 最後に生成した設計書(Blueprint)
"""

import json
import os
import re
import shutil
import uuid
from pathlib import Path

from app import config
from app.models.blueprint import Blueprint
from app.models.omr import OmrJobError, OmrJobRecord, OmrJobStatus
from app.services.parser import ScoreSummary, parse_score

_SCORE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class OmrJobDataError(Exception):
    """永続化されたジョブ状態を安全に解釈できない。"""


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
    """score_id を発行し original.<ext> と表示用ファイル名を保存する。"""
    score_id = uuid.uuid4().hex
    ext = Path(original_filename).suffix.lower()
    directory = _scores_root() / score_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"original{ext}").write_bytes(content)
    # Blueprint.meta.source_file 用に元のファイル名を保持する
    (directory / "source_filename.txt").write_text(
        Path(original_filename).name, encoding="utf-8"
    )
    return score_id


def load_source_filename(score_id: str) -> str | None:
    path = score_dir(score_id) / "source_filename.txt"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


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
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = ScoreSummary.model_validate(payload)
    if "measure_count" in payload:
        return summary

    # #38 より前の parsed.json は measure_count を持たない。元ファイルから
    # 再パースして全フィールドを最新の形に揃え、次回以降の読み込み用に保存する。
    original = original_path(score_id)
    if original is None:
        return None
    try:
        migrated = parse_score(original).summary
    except Exception:
        # 壊れた永続データは、従来どおり API 層で「score が見つからない」と扱う。
        return None
    try:
        save_parsed(score_id, migrated)
    except OSError:
        # 読み取り可能な既存 score は、移行結果を書き戻せない場合も返す。
        # 次回アクセスで再度移行を試みる。
        pass
    return migrated


def save_blueprint(score_id: str, blueprint: Blueprint) -> None:
    (score_dir(score_id) / "blueprint.json").write_text(
        blueprint.model_dump_json(), encoding="utf-8"
    )


def load_blueprint(score_id: str) -> Blueprint | None:
    path = score_dir(score_id) / "blueprint.json"
    if not path.is_file():
        return None
    return Blueprint.model_validate_json(path.read_text(encoding="utf-8"))


def _validate_job_id(job_id: str) -> str:
    if not _JOB_ID_RE.fullmatch(job_id):
        raise ValueError(f"不正な job_id です: {job_id!r}")
    return job_id


def _omr_jobs_root() -> Path:
    return Path(config.DATA_DIR) / "omr" / "jobs"


def omr_job_dir(job_id: str) -> Path:
    return _omr_jobs_root() / _validate_job_id(job_id)


def omr_job_input_path(job_id: str, source_filename: str) -> Path:
    extension = Path(source_filename).suffix.lower()
    return omr_job_dir(job_id) / f"input{extension}"


def _atomic_write_json(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_omr_job(record: OmrJobRecord) -> None:
    _validate_job_id(record.job_id)
    directory = omr_job_dir(record.job_id)
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(directory / "job.json", record.model_dump_json())


def create_omr_job(source_filename: str, content: bytes) -> OmrJobRecord:
    """入力を task 起動前に永続化し、queued レコードを発行する。"""
    safe_filename = Path(source_filename).name
    if not safe_filename:
        raise ValueError("ファイル名がありません")

    root = _omr_jobs_root()
    root.mkdir(parents=True, exist_ok=True)
    while True:
        job_id = uuid.uuid4().hex
        directory = root / job_id
        try:
            directory.mkdir()
            break
        except FileExistsError:
            continue

    record = OmrJobRecord(
        job_id=job_id,
        status="queued",
        source_filename=safe_filename,
    )
    try:
        omr_job_input_path(job_id, safe_filename).write_bytes(content)
        save_omr_job(record)
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return record


def load_omr_job(job_id: str) -> OmrJobRecord | None:
    path = omr_job_dir(job_id) / "job.json"
    if not path.is_file():
        return None
    try:
        record = OmrJobRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OmrJobDataError("OMR job state is corrupt") from exc
    if record.job_id != job_id:
        raise OmrJobDataError("OMR job id does not match its directory")
    return record


def update_omr_job(
    job_id: str,
    status: OmrJobStatus,
    *,
    score_id: str | None = None,
    error: OmrJobError | None = None,
) -> OmrJobRecord:
    record = load_omr_job(job_id)
    if record is None:
        raise OmrJobDataError("OMR job disappeared")
    updated = record.model_copy(
        update={"status": status, "score_id": score_id, "error": error}
    )
    save_omr_job(updated)
    return updated


def iter_omr_jobs() -> list[OmrJobRecord]:
    root = _omr_jobs_root()
    if not root.is_dir():
        return []
    records: list[OmrJobRecord] = []
    for directory in root.iterdir():
        if not directory.is_dir() or not _JOB_ID_RE.fullmatch(directory.name):
            continue
        try:
            record = load_omr_job(directory.name)
        except OmrJobDataError:
            continue
        if record is not None:
            records.append(record)
    return records


def cleanup_omr_job_input(job_id: str) -> None:
    directory = omr_job_dir(job_id)
    if not directory.is_dir():
        return
    for path in directory.glob("input.*"):
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
