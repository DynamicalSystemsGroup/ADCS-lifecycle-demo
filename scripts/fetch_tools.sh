#!/usr/bin/env bash
# Fetch the OpenSysML toolchain used by the talk assets into .tools/ (gitignored).
# Idempotent: a tool already present is left alone. Every download is checked against
# a published SHA-256 before it is unpacked.
#
#   .tools/sysmlv2       sysml-toolkit  (verify --solve, viz)       Open-MBEE/sysml-toolkit
#   .tools/sysml         OpenSysML CLI  (-render, -render-document) Open-MBEE/OpenSysML
#   .tools/plantuml.jar  PlantUML       (renders `sysmlv2 viz` output)
#
# The SysML v2 standard library is NOT fetched: both CLIs embed it, and `sysmlv2 verify`
# gives the same output with and without --lib (probed 2026-10-14).
set -euo pipefail

TOOLKIT_VERSION=0.10.2
OPENSYSML_VERSION=0.10.0
PLANTUML_VERSION=1.2026.8
# PlantUML publishes no SHA256SUMS file; this is the digest GitHub shows for the release asset.
PLANTUML_SHA256=5e1ecfa8ecd32c90b03bbf3b1eb6f020943f98ab0fcf4032be31a0002ee2c462

cd "$(dirname "$0")/.."
TOOLS=.tools
mkdir -p "$TOOLS"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

os=$(uname -s); arch=$(uname -m)
case "$os-$arch" in
  Darwin-x86_64)  toolkit_triple=x86_64-apple-darwin;        osysml=darwin-amd64 ;;
  Darwin-arm64)   toolkit_triple=aarch64-apple-darwin;       osysml=darwin-arm64 ;;
  Linux-x86_64)   toolkit_triple=x86_64-unknown-linux-gnu;   osysml=linux-amd64 ;;
  Linux-aarch64)  toolkit_triple=aarch64-unknown-linux-gnu;  osysml=linux-arm64 ;;
  *) echo "fetch_tools: unsupported platform $os-$arch" >&2; exit 1 ;;
esac

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

# fetch_checked URL DEST EXPECTED_SHA256
fetch_checked() {
  curl -fsSL --retry 3 -o "$2" "$1"
  [ "$(sha256 "$2")" = "$3" ] || { echo "fetch_tools: SHA-256 mismatch for $1" >&2; exit 1; }
}

# sums_entry SUMSFILE NAME -> digest for NAME
sums_entry() { awk -v n="$2" '$2 == n || $2 == "*" n { print $1 }' "$1"; }

# --- sysmlv2 (sysml-toolkit) ---
if [ ! -x "$TOOLS/sysmlv2" ]; then
  base=https://github.com/Open-MBEE/sysml-toolkit/releases/download/v$TOOLKIT_VERSION
  name=sysmlv2-$TOOLKIT_VERSION-$toolkit_triple.tar.gz
  curl -fsSL --retry 3 -o "$TMP/SHA256SUMS" "$base/SHA256SUMS"
  want=$(sums_entry "$TMP/SHA256SUMS" "$name"); [ -n "$want" ] || { echo "fetch_tools: $name not in SHA256SUMS" >&2; exit 1; }
  fetch_checked "$base/$name" "$TMP/$name" "$want"
  tar -xzf "$TMP/$name" -C "$TMP"
  install -m 755 "$TMP/sysmlv2-$TOOLKIT_VERSION-$toolkit_triple/sysmlv2" "$TOOLS/sysmlv2"
fi

# --- sysml (OpenSysML CLI) ---
if [ ! -x "$TOOLS/sysml" ]; then
  base=https://github.com/Open-MBEE/OpenSysML/releases/download/v$OPENSYSML_VERSION
  name=sysml-$osysml.tar.gz
  curl -fsSL --retry 3 -o "$TMP/SHA256SUMS.txt" "$base/SHA256SUMS.txt"
  want=$(sums_entry "$TMP/SHA256SUMS.txt" "$name"); [ -n "$want" ] || { echo "fetch_tools: $name not in SHA256SUMS.txt" >&2; exit 1; }
  fetch_checked "$base/$name" "$TMP/$name" "$want"
  mkdir "$TMP/sysml-x" && tar -xzf "$TMP/$name" -C "$TMP/sysml-x"
  install -m 755 "$TMP/sysml-x/sysml-$osysml" "$TOOLS/sysml"
fi

# --- PlantUML ---
if [ ! -f "$TOOLS/plantuml.jar" ]; then
  fetch_checked "https://github.com/plantuml/plantuml/releases/download/v$PLANTUML_VERSION/plantuml-$PLANTUML_VERSION.jar" \
    "$TMP/plantuml.jar" "$PLANTUML_SHA256"
  install -m 644 "$TMP/plantuml.jar" "$TOOLS/plantuml.jar"
fi

echo "fetch_tools: ok"
ls -l "$TOOLS"
