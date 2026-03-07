#!/usr/bin/env bash
set -euo pipefail

echo "[pre-push] Running pytest..."
QT_QPA_PLATFORM=offscreen pytest tests/ -q

echo "[pre-push] Running APV smoke verifier..."
python3 scripts/verify_apv_pipeline.py

echo "[pre-push] Verifying test-count docs sync..."
python3 scripts/sync_test_counts.py --check

echo "[pre-push] OK"
