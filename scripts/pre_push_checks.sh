#!/usr/bin/env bash
set -euo pipefail

echo "[pre-push] Running pytest..."
QT_QPA_PLATFORM=offscreen pytest tests/ -q

echo "[pre-push] Running APV smoke verifier..."
python3 scripts/verify_apv_pipeline.py

echo "[pre-push] Checking APV operational readiness..."
set +e
if [ "${FMM_ENFORCE_APV_READY:-0}" = "1" ]; then
  apv_ready_output="$(python3 scripts/verify_apv_secret_ready.py --require-pass 2>&1)"
else
  apv_ready_output="$(python3 scripts/verify_apv_secret_ready.py 2>&1)"
fi
apv_ready_rc=$?
set -e
echo "${apv_ready_output}"
if [ ${apv_ready_rc} -ne 0 ]; then
  if [ "${FMM_ENFORCE_APV_READY:-0}" = "1" ]; then
    echo "[pre-push] APV readiness check failed (enforced mode)."
    exit ${apv_ready_rc}
  fi
  echo "[pre-push] APV readiness check failed but enforcement is disabled; continuing."
fi

echo "[pre-push] Verifying test-count docs sync..."
python3 scripts/sync_test_counts.py --check

echo "[pre-push] OK"
