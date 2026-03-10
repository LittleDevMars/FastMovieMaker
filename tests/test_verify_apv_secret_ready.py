"""Tests for APV operational readiness verification script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_apv_secret_ready.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_apv_secret_ready", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_readiness_fails_when_secret_missing(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "_detect_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(module, "_check_gh_auth", lambda: (True, ""))
    monkeypatch.setattr(module, "_secret_exists", lambda _repo, _name: (False, None))

    result = module.evaluate_readiness()

    assert result.status == "FAIL"
    assert "required secret is missing" in result.reason


def test_readiness_passes_when_secret_exists_and_apv_passes(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "_detect_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(module, "_check_gh_auth", lambda: (True, ""))
    monkeypatch.setattr(module, "_secret_exists", lambda _repo, _name: (True, None))
    monkeypatch.setattr(
        module,
        "_find_recent_apv_smoke",
        lambda _repo: ("PASS", "recent apv-smoke job succeeded", "https://example.com/run/1"),
    )

    result = module.evaluate_readiness()

    assert result.status == "PASS"
    assert "succeeded" in result.reason
    assert result.run_url == "https://example.com/run/1"


def test_readiness_skips_when_auth_unavailable(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "_detect_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(module, "_check_gh_auth", lambda: (False, "not logged in"))

    result = module.evaluate_readiness()

    assert result.status == "SKIPPED"
    assert "gh auth unavailable" in result.reason


def test_result_exit_code_default_mode(monkeypatch) -> None:
    module = _load_module()
    assert module._result_exit_code(module.ReadinessResult("PASS", "ok")) == 0
    assert module._result_exit_code(module.ReadinessResult("SKIPPED", "skip")) == 0
    assert module._result_exit_code(module.ReadinessResult("FAIL", "no")) == 1


def test_result_exit_code_require_pass_mode(monkeypatch) -> None:
    module = _load_module()
    assert module._result_exit_code(module.ReadinessResult("PASS", "ok"), require_pass=True) == 0
    assert module._result_exit_code(module.ReadinessResult("SKIPPED", "skip"), require_pass=True) == 1
    assert module._result_exit_code(module.ReadinessResult("FAIL", "no"), require_pass=True) == 1


def test_output_lines_are_ci_friendly() -> None:
    module = _load_module()
    lines = module._format_output_lines(
        module.ReadinessResult("PASS", "recent apv-smoke job succeeded", "https://example.com/run/1")
    )
    assert lines[0] == "result: PASS"
    assert lines[1] == "reason: recent apv-smoke job succeeded"
    assert lines[2] == "run_url: https://example.com/run/1"
