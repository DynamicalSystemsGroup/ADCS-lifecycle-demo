#!/usr/bin/env bash
# flexo/init.sh — provision the adcs-demo org / repo / master branch
# in a running Flexo MMS instance.
#
# Prereqs:
#   - A Flexo Layer1 service reachable at $FLEXO_URL (default
#     http://localhost:8080) AND an auth service at $FLEXO_AUTH_URL
#     (default http://localhost:8082).
#   - Bring up either via the flexo-mms-deployment repo
#     (docker-compose/docker-compose.yml) or use a pre-existing instance.
#
# What it does:
#   1. Logs in as $FLEXO_USER (default user01 / password1) to get a token.
#   2. Idempotently PUTs the adcs-demo org and lifecycle repo.
#   3. Idempotently PUTs the master branch.
#
# Subsequent `uv run python -m pipeline.runner --backend=flexo` calls
# will create per-named-graph branches on demand.

set -euo pipefail

FLEXO_URL="${FLEXO_URL:-http://localhost:8080}"
FLEXO_AUTH_URL="${FLEXO_AUTH_URL:-http://localhost:8082}"
FLEXO_USER="${FLEXO_USER:-user01}"
FLEXO_PASS="${FLEXO_PASS:-password1}"
FLEXO_ORG="${FLEXO_ORG:-adcs-demo}"
FLEXO_REPO="${FLEXO_REPO:-lifecycle}"
TIMEOUT=60

echo "Flexo init: $FLEXO_URL (org=$FLEXO_ORG, repo=$FLEXO_REPO)"

# --- Auth ---------------------------------------------------------------

if [[ -n "${FLEXO_TOKEN:-}" ]]; then
    echo "  Using pre-issued FLEXO_TOKEN"
    TOKEN="$FLEXO_TOKEN"
else
    echo "  Logging in as $FLEXO_USER via $FLEXO_AUTH_URL/login ..."
    TOKEN_JSON=$(curl -s -m "$TIMEOUT" -u "$FLEXO_USER:$FLEXO_PASS" "$FLEXO_AUTH_URL/login")
    TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin).get('token', ''))" 2>/dev/null || true)
    if [[ -z "$TOKEN" ]]; then
        echo "ERROR: failed to obtain token from $FLEXO_AUTH_URL/login" >&2
        echo "Response: $TOKEN_JSON" >&2
        exit 1
    fi
    echo "  Got token (${#TOKEN} chars)"
fi

# --- Helpers ------------------------------------------------------------

put_resource() {
    local url="$1" title="$2" extra="${3:-}"
    local body="<> <http://purl.org/dc/terms/title> \"$title\"@en .${extra}"
    local code
    code=$(curl -s -m "$TIMEOUT" -o /dev/null -w "%{http_code}" \
        -X PUT "$url" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: text/turtle" \
        -d "$body")
    case "$code" in
        200|201) echo "  OK   $url ($code)";;
        409)     echo "  EXIST $url ($code)";;
        *)       echo "  FAIL $url ($code)" >&2; exit 1;;
    esac
}

# --- Provision ----------------------------------------------------------

put_resource "$FLEXO_URL/orgs/$FLEXO_ORG" "$FLEXO_ORG"
put_resource "$FLEXO_URL/orgs/$FLEXO_ORG/repos/$FLEXO_REPO" "$FLEXO_REPO"
put_resource "$FLEXO_URL/orgs/$FLEXO_ORG/repos/$FLEXO_REPO/branches/master" "master"

echo
echo "Flexo init complete. Run:"
echo "  uv run python -m pipeline.runner --backend=flexo --auto"
