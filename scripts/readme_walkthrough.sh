#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
OUT_DIR="${1:-/tmp/leaguespy-walkthrough}"

mkdir -p "$OUT_DIR"

echo "==> LeagueSpy README walkthrough"
echo "Using Python: $PYTHON_BIN"
echo "Artifacts dir: $OUT_DIR"

echo
echo "==> 1) Offline doctor against the example config"
"$PYTHON_BIN" -m src.cli doctor --config config.example.yaml --offline

echo
echo "==> 2) Generate offline showcase artifacts"
"$PYTHON_BIN" -m src.cli showcase --output-dir "$OUT_DIR/showcase"

echo
echo "==> 3) Run the automated test suite"
"$PYTHON_BIN" -m pytest -q tests -q

echo
echo "Walkthrough complete."
echo "Showcase artifacts: $OUT_DIR/showcase"
