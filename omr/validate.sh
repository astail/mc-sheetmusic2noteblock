#!/bin/sh
set -eu

repo_dir="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "${repo_dir}"

project_name="omr-validation-$$"

compose() {
    docker compose --project-name "${project_name}" --profile omr "$@"
}

monotonic_ns() {
    python3 -c 'import time; print(time.monotonic_ns())'
}

validation_name=".omr-validation-$$"
validation_dir="${repo_dir}/data/${validation_name}"

cleanup() {
    compose down --remove-orphans --rmi local >/dev/null 2>&1 || true
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

stop_started_ns="$(monotonic_ns)"
docker stop --timeout 2 "${container_id}" >/dev/null
stop_finished_ns="$(monotonic_ns)"
stop_elapsed_ms="$(((stop_finished_ns - stop_started_ns) / 1000000))"
exit_code="$(docker inspect --format '{{.State.ExitCode}}' "${container_id}")"

test "${stop_elapsed_ms}" -lt 2000
test "${exit_code}" -eq 0

cleanup

test -z "$(docker ps --all --quiet \
    --filter "label=com.docker.compose.project=${project_name}")"
test -z "$(docker network ls --quiet \
    --filter "label=com.docker.compose.project=${project_name}")"
test -z "$(docker image ls --quiet \
    --filter "reference=${project_name}-*")"

trap - EXIT INT TERM

echo "Graceful stop completed in ${stop_elapsed_ms} ms with exit code ${exit_code}."
echo "OMR build, export, health, graceful stop and container/network/image cleanup checks passed."
