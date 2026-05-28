#!/usr/bin/env bash
# start-services.sh — bring up the local fourth-service stack for the
# canonical multi-remote pipeline run.
#
# WP4 §"The transaction-log store as a fourth service". The store is
# a CouchDB container with the demo's expected name + port + default
# credentials. Idempotent: re-running is safe; if the container is
# already up it prints reachability + exits.
#
# To stop / clean up: tools/stop-services.sh

set -euo pipefail

CONTAINER_NAME="${ADCS_TXNLOG_CONTAINER:-couchdb-adcs}"
PORT="${ADCS_TXNLOG_PORT:-5984}"
USER="${ADCS_TXNLOG_USER:-adcs}"
PASSWORD="${ADCS_TXNLOG_PASSWORD:-adcs}"
DB="${ADCS_TXNLOG_DB:-adcs-txnlogs}"
IMAGE="${ADCS_TXNLOG_IMAGE:-couchdb:3}"

echo "[start-services] Bringing up txnlog store..."
echo "  Container: ${CONTAINER_NAME}"
echo "  Port:      ${PORT}"
echo "  Database:  ${DB}"

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker not on PATH. Install Docker Desktop / Colima first." >&2
    exit 1
fi

# Is the container already running?
if docker ps --filter "name=${CONTAINER_NAME}" --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "  Container already running — skipping start."
else
    # Check if a stopped container exists and remove it first
    if docker ps -a --filter "name=${CONTAINER_NAME}" --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        echo "  Removing previous stopped container..."
        docker rm -f "${CONTAINER_NAME}" >/dev/null
    fi
    echo "  Starting ${IMAGE}..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        -p "${PORT}:5984" \
        -e "COUCHDB_USER=${USER}" \
        -e "COUCHDB_PASSWORD=${PASSWORD}" \
        "${IMAGE}" >/dev/null
fi

# Wait for CouchDB to be ready (it has a startup delay)
echo -n "  Waiting for CouchDB to respond..."
for i in $(seq 1 30); do
    if curl -fsS "http://${USER}:${PASSWORD}@localhost:${PORT}/" >/dev/null 2>&1; then
        echo " ready."
        break
    fi
    echo -n "."
    sleep 1
done

# Create the database if it doesn't exist (idempotent)
echo -n "  Ensuring database '${DB}' exists..."
status=$(curl -s -o /dev/null -w "%{http_code}" \
    -X PUT "http://${USER}:${PASSWORD}@localhost:${PORT}/${DB}")
case "${status}" in
    201|202|412) echo " ok (${status})." ;;
    *) echo " status=${status}"; exit 1 ;;
esac

echo "[start-services] Txnlog store reachable at http://localhost:${PORT}/${DB}"
echo "  Fauxton UI: http://localhost:${PORT}/_utils/"
echo
echo "To use this store from a pipeline run:"
echo "  export ADCS_TXNLOG_ENABLED=1"
echo "  export ADCS_TXNLOG_URL=http://localhost:${PORT}"
echo "  export ADCS_TXNLOG_USER=${USER}"
echo "  export ADCS_TXNLOG_PASSWORD=${PASSWORD}"
echo "  uv run python -m pipeline.runner --auto --backend=flexo --compute=docker"
