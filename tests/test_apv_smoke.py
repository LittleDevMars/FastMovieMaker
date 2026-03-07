"""Smoke tests for APV pipeline verification script."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_apv_pipeline.py"


def test_apv_smoke_script_skips_without_sample_env(monkeypatch) -> None:
    env = dict(os.environ)
    env.pop("FMM_APV_SAMPLE", None)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert "SKIPPED:" in result.stdout


def test_apv_smoke_script_fails_with_missing_sample_file() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--sample", "/tmp/fmm_apv_missing_sample.mov"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "FAIL:" in result.stdout


@pytest.mark.apv_smoke
def test_apv_smoke_script_runs_with_sample_env() -> None:
    sample_path = os.getenv("FMM_APV_SAMPLE", "").strip()
    if not sample_path:
        pytest.skip("FMM_APV_SAMPLE is not set")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--sample", sample_path],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "PASS:" in result.stdout
