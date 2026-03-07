#!/usr/bin/env python3
"""Check APV operational readiness from GitHub metadata.

Result contract:
  - PASS: secret exists and a recent apv-smoke job succeeded
  - FAIL: secret missing or recent apv-smoke job failed/not found
  - SKIPPED: local environment cannot query GitHub metadata (no gh auth/permission)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass


SECRET_NAME = "APV_SAMPLE_B64"
WORKFLOW_FILE = "tests.yml"
APV_JOB_NAME = "apv-smoke"
DEFAULT_LOOKBACK = 10


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    status: str  # PASS | SKIPPED | FAIL
    reason: str
    run_url: str | None = None


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )


def _detect_repo_slug() -> str | None:
    repo_from_env = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if "/" in repo_from_env:
        return repo_from_env

    proc = _run_command(["git", "config", "--get", "remote.origin.url"])
    if proc.returncode != 0:
        return None
    remote = (proc.stdout or "").strip()
    if not remote:
        return None

    ssh_match = re.match(r"^git@github\.com:(?P<slug>[^/]+/[^/]+?)(?:\.git)?$", remote)
    if ssh_match:
        return ssh_match.group("slug")
    https_match = re.match(r"^https://github\.com/(?P<slug>[^/]+/[^/]+?)(?:\.git)?$", remote)
    if https_match:
        return https_match.group("slug")
    return None


def _check_gh_auth() -> tuple[bool, str]:
    proc = _run_command(["gh", "auth", "status"])
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or "gh auth unavailable"
        return False, detail
    return True, ""


def _gh_api_json(endpoint: str) -> tuple[dict, str | None]:
    proc = _run_command(["gh", "api", endpoint])
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"gh api failed: {endpoint}"
        return {}, detail
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON from gh api ({endpoint}): {exc}"
    return payload, None


def _secret_exists(repo_slug: str, secret_name: str) -> tuple[bool, str | None]:
    endpoint = f"/repos/{repo_slug}/actions/secrets/{secret_name}"
    payload, err = _gh_api_json(endpoint)
    if err:
        text = err.lower()
        if "404" in text or "not found" in text:
            return False, None
        return False, err
    return bool(payload.get("name") == secret_name), None


def _find_recent_apv_smoke(repo_slug: str, lookback: int = DEFAULT_LOOKBACK) -> tuple[str, str, str | None]:
    runs_endpoint = f"/repos/{repo_slug}/actions/workflows/{WORKFLOW_FILE}/runs?per_page={lookback}"
    runs_payload, err = _gh_api_json(runs_endpoint)
    if err:
        return "SKIPPED", f"cannot query workflow runs: {err}", None

    runs = runs_payload.get("workflow_runs", []) or []
    if not runs:
        return "FAIL", "no recent workflow runs found for tests.yml", None

    for run in runs:
        run_id = run.get("id")
        run_url = run.get("html_url")
        if not run_id:
            continue
        jobs_endpoint = f"/repos/{repo_slug}/actions/runs/{run_id}/jobs?per_page=100"
        jobs_payload, jobs_err = _gh_api_json(jobs_endpoint)
        if jobs_err:
            return "SKIPPED", f"cannot query workflow jobs: {jobs_err}", None
        jobs = jobs_payload.get("jobs", []) or []
        for job in jobs:
            if job.get("name") != APV_JOB_NAME:
                continue
            conclusion = str(job.get("conclusion") or "").lower()
            status = str(job.get("status") or "").lower()
            if conclusion == "success":
                return "PASS", "recent apv-smoke job succeeded", run_url
            if conclusion in {"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"}:
                return "FAIL", f"recent apv-smoke job ended with {conclusion}", run_url
            if status in {"queued", "in_progress", "waiting", "requested", "pending"}:
                return "FAIL", f"recent apv-smoke job is not complete (status={status})", run_url
            return "FAIL", "recent apv-smoke job has unknown state", run_url

    return "FAIL", "no apv-smoke job found in recent workflow runs", None


def evaluate_readiness() -> ReadinessResult:
    repo_slug = _detect_repo_slug()
    if not repo_slug:
        return ReadinessResult("SKIPPED", "unable to detect GitHub repository slug")

    try:
        authed, reason = _check_gh_auth()
    except FileNotFoundError:
        return ReadinessResult("SKIPPED", "gh CLI is not installed")
    if not authed:
        return ReadinessResult("SKIPPED", f"gh auth unavailable: {reason}")

    exists, secret_err = _secret_exists(repo_slug, SECRET_NAME)
    if secret_err:
        return ReadinessResult("SKIPPED", f"cannot verify secret metadata: {secret_err}")
    if not exists:
        return ReadinessResult("FAIL", f"required secret is missing: {SECRET_NAME}")

    run_status, run_reason, run_url = _find_recent_apv_smoke(repo_slug)
    if run_status == "PASS":
        return ReadinessResult("PASS", run_reason, run_url)
    if run_status == "SKIPPED":
        return ReadinessResult("SKIPPED", run_reason, run_url)
    return ReadinessResult("FAIL", run_reason, run_url)


def _result_exit_code(result: ReadinessResult, require_pass: bool = False) -> int:
    if require_pass:
        return 0 if result.status == "PASS" else 1
    return 1 if result.status == "FAIL" else 0


def _format_output_lines(result: ReadinessResult) -> list[str]:
    lines = [f"result: {result.status}", f"reason: {result.reason}"]
    if result.run_url:
        lines.append(f"run_url: {result.run_url}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify APV operational readiness.")
    parser.add_argument(
        "--require-pass",
        action="store_true",
        help="Return non-zero unless readiness status is PASS.",
    )
    args = parser.parse_args()

    result = evaluate_readiness()
    for line in _format_output_lines(result):
        print(line)
    return _result_exit_code(result, require_pass=args.require_pass)


if __name__ == "__main__":
    raise SystemExit(main())
