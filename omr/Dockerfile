# syntax=docker/dockerfile:1

# Audiveris 5.11 requires a 64-bit Java 25 runtime. The official Linux
# release is currently available for x86_64 only.
FROM eclipse-temurin:25.0.3_9-jre-noble@sha256:2f1da100788559b397bcf48c736169ea5b070bde84e55f203bbee8e83d87a175

ARG TARGETARCH
ARG AUDIVERIS_VERSION=5.11.0
ARG AUDIVERIS_PACKAGE_URL=https://github.com/Audiveris/audiveris/releases/download/5.11.0/Audiveris-5.11.0-ubuntu24.04-x86_64.deb
ARG AUDIVERIS_PACKAGE_SHA256=f20113aaa33b3149ec8d6a09b2a7963360e65fafd92d69389987a85bbc3ec7a3

LABEL org.opencontainers.image.title="mc-sheetmusic2noteblock OMR" \
      org.opencontainers.image.description="Audiveris batch OMR runtime" \
      org.opencontainers.image.version="${AUDIVERIS_VERSION}" \
      org.opencontainers.image.source="https://github.com/Audiveris/audiveris/tree/5.11.0" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

ENV AUDIVERIS_HOME=/opt/audiveris \
    AUDIVERIS_MIN_HEAP=512m \
    AUDIVERIS_MAX_HEAP=8G \
    JAVA_TOOL_OPTIONS=-Djava.awt.headless=true \
    PATH=/opt/audiveris/bin:/usr/local/bin:${PATH}

RUN set -eux; \
    test "${TARGETARCH:-$(dpkg --print-architecture)}" = "amd64"; \
    test "$(dpkg --print-architecture)" = "amd64"; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libgtk-3-0t64; \
    curl --fail --location --retry 3 \
        --output /tmp/audiveris.deb \
        "${AUDIVERIS_PACKAGE_URL}"; \
    echo "${AUDIVERIS_PACKAGE_SHA256}  /tmp/audiveris.deb" | sha256sum --check --strict; \
    dpkg-deb --extract /tmp/audiveris.deb /; \
    test "$(dpkg-deb --field /tmp/audiveris.deb Version)" = "${AUDIVERIS_VERSION}"; \
    rm -rf \
        /opt/audiveris/lib/runtime \
        /opt/audiveris/bin/Audiveris \
        /tmp/audiveris.deb \
        /var/lib/apt/lists/*; \
    apt-get purge -y --auto-remove curl; \
    ln -s /usr/local/bin/Audiveris /opt/audiveris/bin/Audiveris

COPY --chmod=755 bin/Audiveris /usr/local/bin/Audiveris
COPY --chmod=755 bin/entrypoint.sh /usr/local/bin/omr-entrypoint
COPY --chmod=755 bin/healthcheck.sh /usr/local/bin/omr-healthcheck

RUN Audiveris -version

WORKDIR /data
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD ["/usr/local/bin/omr-healthcheck"]

ENTRYPOINT ["/usr/local/bin/omr-entrypoint"]
