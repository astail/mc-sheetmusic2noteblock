#!/bin/sh
set -eu

repo_dir="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "${repo_dir}"

project_name="omr-validation-$(date +%s)-$$"
active_container="${project_name}-active"
active_client="${project_name}-client"

compose() {
    docker compose --project-name "${project_name}" --profile omr "$@"
}

monotonic_ns() {
    python3 -c 'import time; print(time.monotonic_ns())'
}

validation_name=".omr-validation-$$"
validation_dir="${repo_dir}/data/${validation_name}"

cleanup() {
    docker rm --force "${active_client}" "${active_container}" >/dev/null 2>&1 || true
    compose down --remove-orphans --rmi local >/dev/null 2>&1 || true
    docker image rm "${project_name}-unit" >/dev/null 2>&1 || true
    rm -rf "${validation_dir}"
}
trap cleanup EXIT INT TERM

mkdir -p "${validation_dir}"
compose config --quiet
docker build \
    --file omr/Dockerfile \
    --target test \
    --tag "${project_name}-unit" \
    omr >/dev/null
docker run --rm "${project_name}-unit"
docker image rm "${project_name}-unit" >/dev/null

compose build omr
compose run --rm omr Audiveris -version
curl --fail --location --retry 3 \
    --output "${validation_dir}/allegretto.png" \
    "https://raw.githubusercontent.com/Audiveris/audiveris/5.11.0/data/examples/allegretto.png"
echo "a9207f26b57415d8c54602881316c003319c5593ed8baf4c3af13715c41b3065  ${validation_dir}/allegretto.png" |
    sha256sum --check --strict

compose up --detach --wait omr

container_id="$(compose ps --quiet omr)"
test -n "${container_id}"
status="$(docker inspect --format '{{.State.Health.Status}}' "${container_id}")"
test "${status}" = "healthy"
# entrypoint の ${OMR_PORT:-8080} と同様に、空文字も既定値へ戻る。
compose exec --no-TTY --env OMR_PORT= omr /usr/local/bin/omr-healthcheck

compose exec --no-TTY omr python3 - \
    "/data/${validation_name}/allegretto.png" \
    "/data/${validation_name}/allegretto.mxl" <<'PY'
import secrets
import sys
from urllib.request import Request, urlopen

input_path, output_path = sys.argv[1:]
boundary = f"----omr-validation-{secrets.token_hex(12)}"
image = open(input_path, "rb").read()
body = (
    f"--{boundary}\r\n"
    'Content-Disposition: form-data; name="file"; filename="allegretto.png"\r\n'
    "Content-Type: image/png\r\n\r\n"
).encode() + image + f"\r\n--{boundary}--\r\n".encode()
request = Request(
    "http://127.0.0.1:8080/transcribe",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)
with urlopen(request, timeout=300) as response:
    assert response.status == 200
    assert response.headers.get_content_type() == "application/vnd.recordare.musicxml+xml"
    with open(output_path, "wb") as output:
        output.write(response.read())
PY

test -s "${validation_dir}/allegretto.mxl"
python3 -m zipfile --test "${validation_dir}/allegretto.mxl"

stop_started_ns="$(monotonic_ns)"
docker stop --timeout 2 "${container_id}" >/dev/null
stop_finished_ns="$(monotonic_ns)"
stop_elapsed_ms="$(((stop_finished_ns - stop_started_ns) / 1000000))"
exit_code="$(docker inspect --format '{{.State.ExitCode}}' "${container_id}")"

test "${stop_elapsed_ms}" -lt 2000
test "${exit_code}" -eq 0

active_workspace_dir="${validation_dir}/active-workspaces"
mkdir -p "${active_workspace_dir}"
active_port=18080
active_id="$(docker run --detach \
    --name "${active_container}" \
    --env AUDIVERIS_COMMAND=/test/fake_audiveris.py \
    --env FAKE_AUDIVERIS_MODE=hang \
    --env FAKE_AUDIVERIS_PID=/validation/fake.pid \
    --env FAKE_AUDIVERIS_STARTED=/validation/fake-started \
    --env FAKE_AUDIVERIS_TERM_MARKER=/validation/fake-term \
    --env OMR_PORT="${active_port}" \
    --env TMPDIR=/validation/active-workspaces \
    --volume "${repo_dir}/omr/tests/fake_audiveris.py:/test/fake_audiveris.py:ro" \
    --volume "${validation_dir}:/validation" \
    "${project_name}-omr")"
test -n "${active_id}"

attempt=0
until docker exec "${active_container}" /usr/local/bin/omr-healthcheck >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    test "${attempt}" -lt 120
    sleep 0.25
done

active_client_id="$(docker run --detach \
    --name "${active_client}" \
    --network "container:${active_id}" \
    --entrypoint python3 \
    --volume "${repo_dir}/omr/tests/http_client.py:/test/http_client.py:ro" \
    --volume "${validation_dir}/allegretto.png:/test/allegretto.png:ro" \
    "${project_name}-omr" \
    /test/http_client.py \
    /test/allegretto.png \
    "http://127.0.0.1:${active_port}/transcribe")"
test -n "${active_client_id}"

attempt=0
until test -s "${validation_dir}/fake.pid"; do
    attempt=$((attempt + 1))
    test "${attempt}" -lt 120
    sleep 0.25
done
fake_pid="$(cat "${validation_dir}/fake.pid")"
docker exec "${active_container}" kill -0 "${fake_pid}"

active_stop_started_ns="$(monotonic_ns)"
docker stop --timeout 10 "${active_container}" >/dev/null
active_stop_finished_ns="$(monotonic_ns)"
active_stop_elapsed_ms="$(((active_stop_finished_ns - active_stop_started_ns) / 1000000))"
active_exit_code="$(docker inspect --format '{{.State.ExitCode}}' "${active_container}")"

test "${active_stop_elapsed_ms}" -lt 10000
test "${active_exit_code}" -eq 0
test -e "${validation_dir}/fake-term"
timeout 10 docker wait "${active_client}" >/dev/null
test "$(docker inspect --format '{{.State.Running}}' "${active_client}")" = "false"
test -z "$(find "${active_workspace_dir}" -mindepth 1 -maxdepth 1 -print -quit)"

docker rm "${active_client}" "${active_container}" >/dev/null

cleanup

test -z "$(docker ps --all --quiet \
    --filter "label=com.docker.compose.project=${project_name}")"
test -z "$(docker network ls --quiet \
    --filter "label=com.docker.compose.project=${project_name}")"
test -z "$(docker image ls --quiet \
    --filter "reference=${project_name}-*")"
test -z "$(docker ps --all --quiet --filter "name=^/${active_container}$")"
test -z "$(docker ps --all --quiet --filter "name=^/${active_client}$")"

trap - EXIT INT TERM

echo "Graceful stop completed in ${stop_elapsed_ms} ms with exit code ${exit_code}."
echo "Active-request stop completed in ${active_stop_elapsed_ms} ms with exit code ${active_exit_code}."
echo "OMR unit tests, HTTP export, health, graceful stop and container/network/image cleanup checks passed."
