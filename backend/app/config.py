"""環境変数から読む設定値。"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
OMR_SERVICE_URL = os.environ.get("OMR_SERVICE_URL", "http://omr:8080")
REPEATER_WARNING_THRESHOLD = int(os.environ.get("REPEATER_WARNING_THRESHOLD", "300"))


def _default_frontend_dir() -> Path:
    # cwd 相対(コンテナの WORKDIR /app・リポジトリルート起動)→ リポジトリ配置
    # (backend/ からの直接起動。pip install 済みコンテナでは site-packages 配下なので不成立)の順に解決
    candidates = [Path("frontend"), Path(__file__).resolve().parents[2] / "frontend"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


_frontend_env = os.environ.get("FRONTEND_DIR")
FRONTEND_DIR = Path(_frontend_env) if _frontend_env else _default_frontend_dir()
