#!/usr/bin/env python3
"""APV conversion smoke verification script.

Usage:
  FMM_APV_SAMPLE=/path/to/sample.mov python3 scripts/verify_apv_pipeline.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner
from src.workers.video_load_worker import VideoLoadWorker


def _probe_video_codec(path: Path) -> str:
    runner = get_ffmpeg_runner()
    result = runner.run_ffprobe(
        [
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=10,
    )
    return (result.stdout or "").strip().lower()


def _probe_stream_types(path: Path) -> set[str]:
    runner = get_ffmpeg_runner()
    result = runner.run_ffprobe(
        [
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        timeout=10,
    )
    return {line.strip().lower() for line in (result.stdout or "").splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify APV conversion pipeline.")
    parser.add_argument(
        "--sample",
        type=str,
        default=os.getenv("FMM_APV_SAMPLE", "").strip(),
        help="Path to APV sample file (defaults to FMM_APV_SAMPLE)",
    )
    args = parser.parse_args()

    if not args.sample:
        print("SKIPPED: FMM_APV_SAMPLE is not set.")
        return 0

    sample_path = Path(args.sample).expanduser()
    if not sample_path.is_file():
        print(f"FAIL: sample file does not exist: {sample_path}")
        return 1

    runner = get_ffmpeg_runner()
    if not runner.is_available():
        print("FAIL: FFmpeg/FFprobe is not available.")
        return 1

    try:
        codec_name = _probe_video_codec(sample_path)
    except Exception as exc:  # pragma: no cover - defensive guard
        print(f"FAIL: ffprobe codec probe failed: {exc}")
        return 1

    if codec_name != "apv":
        print(f"FAIL: expected APV codec, got '{codec_name or 'unknown'}'.")
        return 1

    worker = VideoLoadWorker(sample_path)
    try:
        converted = worker._convert_to_mp4(sample_path)
    except Exception as exc:  # pragma: no cover - defensive guard
        print(f"FAIL: conversion raised an exception: {exc}")
        return 1

    if converted is None or not converted.is_file():
        print("FAIL: conversion to MP4 failed.")
        return 1

    try:
        try:
            stream_types = _probe_stream_types(converted)
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"FAIL: ffprobe stream probe failed: {exc}")
            return 1
        if "video" not in stream_types:
            print(f"FAIL: converted output has no video stream: {converted}")
            return 1
        if "audio" not in stream_types:
            print(f"FAIL: converted output has no audio stream: {converted}")
            return 1

        print("PASS: APV conversion pipeline verified (codec=apv, video+audio streams found).")
        print(f"  sample: {sample_path}")
        print(f"  output: {converted}")
        return 0
    finally:
        converted.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
