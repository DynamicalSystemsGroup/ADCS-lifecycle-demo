#!/usr/bin/env bash
# Pre-push leak check. Run before every push: scripts/leak_check.sh [BASE]
#
# Scans what would leave this machine (tracked changes BASE..HEAD, default
# origin/main) for private context. Exits non-zero on any hit.
#
#   1. nothing under private/ is tracked
#   2. no secret-shaped strings (JWTs, bearer tokens, *_TOKEN=value, private keys)
#   3. no local home paths, Slack archive links, or Google Docs links
#   4. no term from private/denylist.txt (gitignored; one term per line, # comments)
#
# Contains no sensitive strings itself; the denylist lives in private/.
set -euo pipefail

BASE="${1:-origin/main}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
fail=0

report() { echo "LEAK-CHECK FAIL: $1"; fail=1; }

# 1. private/ must not be tracked
if [ -n "$(git ls-files private/)" ]; then
  report "files under private/ are tracked:"; git ls-files private/
fi

# Added lines in the outgoing diff (tracked changes only)
ADDED="$(git diff "$BASE"...HEAD --unified=0 --no-color -- . ':(exclude)uv.lock' \
  | grep -E '^\+' | grep -vE '^\+\+\+ ' || true)"

scan() {  # scan <label> <extended-regex>
  local hits
  hits="$(printf '%s\n' "$ADDED" | grep -nE -- "$2" || true)"
  if [ -n "$hits" ]; then report "$1"; printf '%s\n' "$hits" | head -20; fi
}

# 2. secrets
scan "JWT-shaped token"            'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'
scan "bearer token"                '[Bb]earer [A-Za-z0-9._~+/-]{20,}'
scan "*_TOKEN assignment w/ value" '[A-Z_]*TOKEN[A-Z_]*=["'"'"']?[A-Za-z0-9._-]{12,}'
scan "private key block"           'BEGIN [A-Z ]*PRIVATE KEY'

# 3. local paths and internal links
scan "local home path"             '/Users/[a-z]+/'
scan "Slack archive link"          'slack\.com/archives'
scan "Google Docs link"            'docs\.google\.com'
# email addresses, except obviously public/no-reply ones
EMAILS="$(printf '%s\n' "$ADDED" | grep -noE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' \
  | grep -viE 'noreply|no-reply|example\.(com|org)|@users\.noreply\.github\.com' || true)"
if [ -n "$EMAILS" ]; then report "email address in outgoing diff"; printf '%s\n' "$EMAILS" | head -20; fi

# 4. denylist terms (case-insensitive, fixed strings)
DENY="$ROOT/private/denylist.txt"
if [ -f "$DENY" ]; then
  while IFS= read -r term; do
    case "$term" in ''|\#*) continue ;; esac
    if printf '%s\n' "$ADDED" | grep -qiF -- "$term"; then
      report "denylisted term present (term withheld; see private/denylist.txt line for '${term:0:2}…')"
    fi
  done < "$DENY"
else
  echo "LEAK-CHECK NOTE: private/denylist.txt not found; denylist scan skipped"
fi

if [ "$fail" -ne 0 ]; then
  echo "LEAK-CHECK: BLOCKED"; exit 1
fi
echo "LEAK-CHECK: PASS (base $BASE)"
