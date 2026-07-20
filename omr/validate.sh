#!/bin/sh
set -eu

repo_dir="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "${repo_dir}"

compose() {
    docker compose --profile omr "$@"
}

validation_name=".omr-validation-$$"
validation_dir="${repo_dir}/data/${validation_name}"

cleanup() {
    compose rm --stop --force omr >/dev/null 2>&1 || true
    rm -rf "${validation_dir}"
}
trap cleanup EXIT INT TERM

compose config --quiet
compose build omr
compose run --rm omr Audiveris -version

mkdir -p "${validation_dir}/output"
curl --fail --location --retry 3 \
    --output "${validation_dir}/allegretto.png" \
    "https://raw.githubusercontent.com/Audiveris/audiveris/5.11.0/data/examples/allegretto.png"
echo "a9207f26b57415d8c54602881316c003319c5593ed8baf4c3af13715c41b3065  ${validation_dir}/allegretto.png" |
    sha256sum --check --strict

compose run --rm omr \
    Audiveris -batch -export \
    -output "/data/${validation_name}/output" \
    -- "/data/${validation_name}/allegretto.png"

test -s "${validation_dir}/output/allegretto.mxl"
python3 -m zipfile --test "${validation_dir}/output/allegretto.mxl"

compose up --detach --wait omr

container_id="$(compose ps --quiet omr)"
test -n "${container_id}"
status="$(docker inspect --format '{{.State.Health.Status}}' "${container_id}")"
test "${status}" = "healthy"

echo "OMR image build, CLI export and compose health checks passed."
