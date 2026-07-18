"""環境変数から読む設定値。"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
OMR_SERVICE_URL = os.environ.get("OMR_SERVICE_URL", "http://omr:8080")
# コンテナ(WORKDIR /app)でもリポジトリルートからの起動でも "frontend" が既定で解決できる
FRONTEND_DIR = Path(os.environ.get("FRONTEND_DIR", "frontend"))
