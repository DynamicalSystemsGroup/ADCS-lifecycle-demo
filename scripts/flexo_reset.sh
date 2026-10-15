#!/usr/bin/env bash
# Reset the local Flexo SysML v2 stack to an empty store: restart the in-memory quad server,
# wait for it, and re-create the org the SysML v2 service writes into (FLEXO_LOCAL.md, step 3).
# The store never frees deleted projects, so this is the only way to reclaim it.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
dir="${FLEXO_COMPOSE_DIR:-$here/../flexo-mms-sysmlv2/docker-compose}"
env_file="$dir/env/flexo-sysmlv2.env"
[ -f "$env_file" ] || { echo "no $env_file; set FLEXO_COMPOSE_DIR" >&2; exit 1; }

docker restart quad-server >/dev/null
for _ in $(seq 60); do curl -s -o /dev/null http://localhost:3030/\$/ping && break; sleep 1; done
sleep 3
token=$(grep '^FLEXO_AUTH=' "$env_file" | cut -d= -f2- | tr -d '"')
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT http://localhost:8080/orgs/sysmlv2 \
  -H "Authorization: $token" -H 'Content-Type: text/turtle' \
  --data '<> <http://purl.org/dc/terms/title> "sysml2"@en .')
[ "$code" = 201 ] || { echo "org bootstrap returned $code (expected 201)" >&2; exit 1; }
echo "flexo reset: projects = $(curl -s http://localhost:8083/projects)"
