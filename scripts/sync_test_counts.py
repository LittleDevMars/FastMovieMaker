#!/usr/bin/env python3
"""Sync and validate test count numbers in docs.

Usage:
  python scripts/sync_test_counts.py          # update docs in-place
  python scripts/sync_test_counts.py --check  # fail if docs are out of sync

Operational mode:
- Does NOT auto-increment Day counters.
- Only updates test-count related text blocks.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PROGRESS = ROOT / "PROGRESS.md"
TODO = ROOT / "TODO.md"


def run_pytest(args: list[str]) -> str:
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    cmd = ["pytest", "tests/", "-q", *args]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{output.strip()}"
        )
    return output


def parse_collected(output: str) -> int:
    m = re.search(r"(\d+)\s+tests\s+collected", output)
    if not m:
        raise RuntimeError("Could not parse collected test count from pytest output.")
    return int(m.group(1))


def parse_passed(output: str) -> int:
    m = re.search(r"(\d+)\s+passed(?:\s+in|\s*,)", output)
    if not m:
        raise RuntimeError("Could not parse passed test count from pytest output.")
    return int(m.group(1))


def _replace(text: str, pattern: str, repl: str, *, expected_min: int = 1) -> str:
    new_text, count = re.subn(pattern, repl, text, flags=re.MULTILINE)
    if count < expected_min:
        raise RuntimeError(f"Pattern not found (or too few matches): {pattern}")
    return new_text


def build_updated_text(path: Path, text: str, passed: int, collected: int) -> str:
    if path == README:
        badge = (
            f"[![Tests](https://img.shields.io/badge/tests-{passed}%20passed%20%2F%20"
            f"{collected}%20collected-brightgreen.svg)](tests/)"
        )
        text = _replace(
            text,
            r"\[!\[Tests\]\(https://img\.shields\.io/badge/tests-[^)]+-brightgreen\.svg\)\]\(tests/\)",
            badge,
        )
        text = _replace(
            text,
            r"- \*\*.+?\*\*로 검증된 견고한 재생 시스템",
            f"- **{passed} passed / {collected} collected**로 검증된 견고한 재생 시스템",
        )
        text = _replace(
            text,
            r"# 전체 테스트 실행 \(현재 기준 .+\)",
            f"# 전체 테스트 실행 (현재 기준 {passed} passed / {collected} collected)",
        )
        return text

    if path == PROGRESS:
        text = _replace(
            text,
            r"전체 테스트 \*\*\d+/\d+ passed\*\*",
            f"전체 테스트 **{passed}/{collected} passed**",
        )
        text = _replace(
            text,
            r"(\| \*\*테스트 수치 검증 \+ 문서 재동기화\*\* — ).+?(\| \*\*완료 \(Day \d+\)\*\*)",
            (
                r"\1"
                "`QT_QPA_PLATFORM=offscreen pytest tests/ -q --collect-only` 실행으로 "
                f"**{collected} tests collected** 확인, "
                "`QT_QPA_PLATFORM=offscreen pytest tests/ -q` 실행으로 "
                f"**{passed}/{collected} passed** 확인, "
                "`README.md` 현재 수치/배지 문구 동기화 "
                r"\2"
            ),
        )
        return text

    if path == TODO:
        text = _replace(
            text,
            r"\(수정 완료, \d+/\d+ 통과\)",
            f"(수정 완료, {passed}/{collected} 통과)",
        )
        text = _replace(
            text,
            r"(- ✅ 테스트 수치 검증 \+ 문서 재동기화 — ).+( - \d{4}-\d{2}-\d{2})",
            (
                r"\1"
                "`pytest --collect-only` 기준 "
                f"{collected} tests collected, "
                f"`pytest -q` 기준 {passed}/{collected} passed 확인, "
                "README 수치/배지 갱신"
                r"\2"
            ),
        )
        return text

    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Check mode (no write).")
    args = parser.parse_args()

    collected = parse_collected(run_pytest(["--collect-only"]))
    passed = parse_passed(run_pytest([]))

    targets = [README, PROGRESS, TODO]
    out_of_sync: list[Path] = []

    for path in targets:
        current = path.read_text(encoding="utf-8")
        updated = build_updated_text(path, current, passed, collected)
        if current != updated:
            if args.check:
                out_of_sync.append(path)
            else:
                path.write_text(updated, encoding="utf-8")

    if args.check:
        if out_of_sync:
            print("Test counts are out of sync in:")
            for path in out_of_sync:
                print(f"- {path.relative_to(ROOT)}")
            print("Run: python scripts/sync_test_counts.py")
            return 1
        print(f"OK: docs synced ({passed}/{collected} passed, {collected} collected)")
        return 0

    print(f"Updated docs with {passed}/{collected} passed and {collected} collected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
