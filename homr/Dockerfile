# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="mc-sheetmusic2noteblock OMR (homr)" \
      org.opencontainers.image.description="homr (deep-learning OMR) runtime" \
      org.opencontainers.image.source="https://github.com/liebharc/homr" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

# opencv-python-headless(homrの依存)がDebian slim上で動くために必要な共有ライブラリ
RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libxcb1 \
        libsm6 \
        libxext6; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/omr-requirements.txt
RUN set -eux; \
    pip install --no-cache-dir --requirement /tmp/omr-requirements.txt; \
    rm /tmp/omr-requirements.txt

# モデル重み(~180MB)をビルド時に取得し、コンテナ起動のたびダウンロードしないようにする
RUN homr --init

COPY --chmod=755 bin/entrypoint.sh /usr/local/bin/omr-entrypoint
COPY --chmod=755 bin/healthcheck.sh /usr/local/bin/omr-healthcheck
COPY wrapper /opt/omr-api/wrapper

FROM base AS test

COPY requirements-dev.txt /tmp/omr-requirements-dev.txt
COPY tests /tests
RUN set -eux; \
    pip install --no-cache-dir --requirement /tmp/omr-requirements-dev.txt; \
    rm /tmp/omr-requirements-dev.txt

WORKDIR /opt/omr-api
ENTRYPOINT ["python3", "-m", "pytest"]
CMD ["-q", "/tests"]

FROM base AS runtime

WORKDIR /opt/omr-api
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD ["/usr/local/bin/omr-healthcheck"]

ENTRYPOINT ["/usr/local/bin/omr-entrypoint"]
