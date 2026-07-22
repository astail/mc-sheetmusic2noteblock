"""OMR ジョブの永続化・API レスポンスモデル。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


OmrJobStatus = Literal["queued", "running", "done", "failed"]


class OmrJobError(BaseModel):
    """クライアントへ公開してよい、固定文言のエラー情報。"""

    code: str
    message: str


class OmrJobRecord(BaseModel):
    """data/omr/jobs/{job_id}/job.json に保存する内部レコード。"""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: OmrJobStatus
    source_filename: str
    score_id: str | None = None
    error: OmrJobError | None = None
    # done でも、Audiverisが複数ページとして誤認識し結合した場合など
    # 認識結果の確認を促したい場合に設定する(致命的ではないため score_id と共存する)
    warning: str | None = None


class OmrJobResponse(BaseModel):
    job_id: str
    status: OmrJobStatus
    score_id: str | None = None
    error: OmrJobError | None = None
    warning: str | None = None


class OmrJobCreated(BaseModel):
    job_id: str
    status: Literal["queued"]
