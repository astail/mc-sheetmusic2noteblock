#!/bin/sh
set -eu

# 起動前にモデルの読み込みを確認する(壊れたインストールなら healthy 判定前に落とす)
homr --init

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec python3 -m uvicorn wrapper.server:app \
    --host 0.0.0.0 \
    --port "${OMR_PORT:-8080}" \
    --timeout-graceful-shutdown "${OMR_GRACEFUL_SHUTDOWN_SECONDS:-3}"
