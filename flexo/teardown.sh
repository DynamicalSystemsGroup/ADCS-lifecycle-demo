#!/usr/bin/env bash
# flexo/teardown.sh — remove the adcs-demo org from a running Flexo.
# Deletes everything we created: branches, repo, org.

set -euo pipefail

FLEXO_URL="${FLEXO_URL:-http://localhost:8080}"
FLEXO_AUTH_URL="${FLEXO_AUTH_URL:-http://localhost:8082}"
FLEXO_USER="${FLEXO_USER:-user01}"
FLEXO_PASS="${FLEXO_PASS:-password1}"
FLEXO_ORG="${FLEXO_ORG:-adcs-demo}"
TIMEOUT=60

if [[ -n "${FLEXO_TOKEN:-}" ]]; then
    TOKEN="$FLEXO_TOKEN"
else
    TOKEN=$(curl -s -m "$TIMEOUT" -u "$FLEXO_USER:$FLEXO_PASS" \
        "$FLEXO_AUTH_URL/login" \
        | python3 -c "import sys, json; print(json.load(sys.stdin).get('token', ''))" 2>/dev/null || true)
    if [[ -z "$TOKEN" ]]; then
        echo "ERROR: failed to obtain token" >&2
        exit 1
    fi
fi

code=$(curl -s -m "$TIMEOUT" -o /dev/null -w "%{http_code}" \
    -X DELETE "$FLEXO_URL/orgs/$FLEXO_ORG" \
    -H "Authorization: Bearer $TOKEN")
case "$code" in
    200|204) echo "Deleted org $FLEXO_ORG ($code)";;
    404)     echo "Org $FLEXO_ORG not found (already gone)";;
    *)       echo "DELETE returned $code" >&2; exit 1;;
esac
