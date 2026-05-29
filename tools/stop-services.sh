#!/usr/bin/env bash
# stop-services.sh — tear down the local fourth-service stack.
#
# Removes the CouchDB container started by start-services.sh.
# Does NOT delete the volume by default; pass --purge to wipe data.

set -euo pipefail

CONTAINER_NAME="${ADCS_TXNLOG_CONTAINER:-couchdb-adcs}"
PURGE=0
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        -h|--help)
            echo "Usage: $0 [--purge]"
            echo "  --purge    also remove the container's anonymous volume"
            exit 0 ;;
        *) echo "Unknown arg: $arg" >&2; exit 1 ;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker not on PATH." >&2
    exit 1
fi

if docker ps -a --filter "name=${CONTAINER_NAME}" --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "[stop-services] Stopping + removing ${CONTAINER_NAME}..."
    if [ "${PURGE}" -eq 1 ]; then
        docker rm -fv "${CONTAINER_NAME}" >/dev/null
        echo "  Container + anonymous volume removed."
    else
        docker rm -f "${CONTAINER_NAME}" >/dev/null
        echo "  Container removed (volume retained; pass --purge to wipe)."
    fi
else
    echo "[stop-services] No container '${CONTAINER_NAME}' found — nothing to do."
fi
