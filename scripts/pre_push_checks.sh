#!/usr/bin/env bash
set -euo pipefail

echo "[pre-push] Running pytest..."
QT_QPA_PLATFORM=offscreen pytest tests/ -q

echo "[pre-push] Verifying test-count docs sync..."
python3 scripts/sync_test_counts.py --check

echo "[pre-push] OK"
