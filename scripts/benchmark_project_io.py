#!/usr/bin/env python3
"""Benchmark gzip-based project save/load throughput and compression ratio."""

from __future__ import annotations

import argparse
import gzip
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.models.project import ProjectState
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.project_io import load_project, save_project


def build_synthetic_project(segment_count: int, text_length: int) -> ProjectState:
    project = ProjectState()
    project.video_path = Path("/benchmark/source.mp4")
    project.duration_ms = max(1, segment_count) * 200

    track = SubtitleTrack(name="Benchmark", language="ko")
    payload = ("ab" * max(1, text_length // 2))[:text_length]
    for i in range(segment_count):
        start_ms = i * 200
        end_ms = start_ms + 180
        track.add_segment(SubtitleSegment(start_ms, end_ms, f"{i}:{payload}"))
    project.subtitle_track = track
    return project


def run_benchmark(segment_count: int, iterations: int, text_length: int) -> dict[str, float]:
    save_ms_samples: list[float] = []
    load_ms_samples: list[float] = []
    ratio_samples: list[float] = []
    compressed_sizes: list[int] = []
    plain_sizes: list[int] = []

    project = build_synthetic_project(segment_count=segment_count, text_length=text_length)

    with tempfile.TemporaryDirectory(prefix="fmm_projectio_bench_") as tmpdir:
        tmp = Path(tmpdir)
        for i in range(iterations):
            path = tmp / f"bench_{i}.fmm.json"

            t0 = time.perf_counter()
            save_project(project, path)
            t1 = time.perf_counter()

            raw = path.read_bytes()
            compressed_size = len(raw)
            if raw[:2] == b"\x1f\x8b":
                plain_bytes = gzip.decompress(raw)
            else:
                plain_bytes = raw
            plain_size = len(plain_bytes)

            t2 = time.perf_counter()
            loaded = load_project(path)
            t3 = time.perf_counter()
            if len(loaded.subtitle_track) != segment_count:
                raise RuntimeError(
                    f"round-trip mismatch: expected {segment_count}, got {len(loaded.subtitle_track)}"
                )

            save_ms_samples.append((t1 - t0) * 1000.0)
            load_ms_samples.append((t3 - t2) * 1000.0)
            compressed_sizes.append(compressed_size)
            plain_sizes.append(plain_size)
            ratio_samples.append((compressed_size / plain_size) if plain_size else 1.0)

    return {
        "segment_count": float(segment_count),
        "iterations": float(iterations),
        "text_length": float(text_length),
        "save_ms_avg": statistics.fmean(save_ms_samples),
        "load_ms_avg": statistics.fmean(load_ms_samples),
        "save_ms_p95": sorted(save_ms_samples)[int((len(save_ms_samples) - 1) * 0.95)],
        "load_ms_p95": sorted(load_ms_samples)[int((len(load_ms_samples) - 1) * 0.95)],
        "compressed_bytes_avg": statistics.fmean(compressed_sizes),
        "plain_bytes_avg": statistics.fmean(plain_sizes),
        "compression_ratio_avg": statistics.fmean(ratio_samples),
    }


def format_report(metrics: dict[str, float]) -> list[str]:
    return [
        "PROJECT_IO_BENCHMARK",
        f"segments: {int(metrics['segment_count'])}",
        f"iterations: {int(metrics['iterations'])}",
        f"text_length: {int(metrics['text_length'])}",
        f"save_ms_avg: {metrics['save_ms_avg']:.3f}",
        f"load_ms_avg: {metrics['load_ms_avg']:.3f}",
        f"save_ms_p95: {metrics['save_ms_p95']:.3f}",
        f"load_ms_p95: {metrics['load_ms_p95']:.3f}",
        f"compressed_bytes_avg: {metrics['compressed_bytes_avg']:.1f}",
        f"plain_bytes_avg: {metrics['plain_bytes_avg']:.1f}",
        f"compression_ratio_avg: {metrics['compression_ratio_avg']:.4f}",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark project save/load compression path.")
    parser.add_argument("--segments", type=int, default=2000, help="Number of subtitle segments.")
    parser.add_argument("--iterations", type=int, default=3, help="Benchmark iteration count.")
    parser.add_argument("--text-length", type=int, default=80, help="Payload text length.")
    args = parser.parse_args()

    if args.segments <= 0:
        raise SystemExit("--segments must be > 0")
    if args.iterations <= 0:
        raise SystemExit("--iterations must be > 0")
    if args.text_length <= 0:
        raise SystemExit("--text-length must be > 0")

    metrics = run_benchmark(
        segment_count=args.segments,
        iterations=args.iterations,
        text_length=args.text_length,
    )
    for line in format_report(metrics):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
