"""Frame thumbnail cache for instant preview during source switching."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import shutil
import tempfile
from pathlib import Path

from src.utils.ffmpeg_utils import find_ffmpeg


def _ms_from_path(path: Path) -> int:
    """Extract millisecond value from filename like frame_000001000.jpg."""
    stem = path.stem  # e.g., "frame_000001000"
    return int(stem.split("_")[1])


class FrameCacheService:
    """Manages a directory of pre-extracted JPEG frames for quick lookup.

    Cache structure::

        <cache_dir>/
            <source_hash>/
                frame_000000000.jpg   (frame at 0ms)
                frame_000001000.jpg   (frame at 1000ms)
                ...
    """

    def __init__(self) -> None:
        self._cache_dir: Path | None = None

    @property
    def cache_dir(self) -> Path | None:
        return self._cache_dir

    def initialize(self) -> Path:
        """Create a temp directory for this session's frame cache."""
        if self._cache_dir is None:
            self._cache_dir = Path(tempfile.mkdtemp(prefix="fmm_framecache_"))
        return self._cache_dir

    def cleanup(self) -> None:
        """Remove the entire cache directory."""
        if self._cache_dir and self._cache_dir.exists():
            shutil.rmtree(self._cache_dir, ignore_errors=True)
        self._cache_dir = None

    def source_cache_dir(self, source_path: str) -> Path:
        """Return the cache subdirectory for a given source video."""
        h = hashlib.md5(source_path.encode()).hexdigest()[:12]
        d = self.initialize() / h
        d.mkdir(exist_ok=True)
        return d

    def is_cached(self, source_path: str) -> bool:
        """Check if frames have been extracted for this source."""
        d = self.source_cache_dir(source_path)
        return any(d.glob("frame_*.jpg"))

    def get_nearest_frame(self, source_path: str, source_ms: int) -> Path | None:
        """Find the cached JPEG closest to *source_ms*.

        Uses binary search on sorted filenames (ms encoded as zero-padded
        integers).  Returns ``None`` if no frames are cached for this source.
        """
        d = self.source_cache_dir(source_path)
        frames = sorted(d.glob("frame_*.jpg"))
        if not frames:
            return None

        target = source_ms
        best = frames[0]
        best_dist = abs(_ms_from_path(best) - target)

        lo, hi = 0, len(frames) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            ms = _ms_from_path(frames[mid])
            dist = abs(ms - target)
            if dist < best_dist:
                best = frames[mid]
                best_dist = dist
            if ms < target:
                lo = mid + 1
            elif ms > target:
                hi = mid - 1
            else:
                return frames[mid]
        return best

    @staticmethod
    def extract_frames(
        source_path: str,
        output_dir: Path,
        interval_ms: int = 1000,
        width: int = 640,
        duration_ms: int | None = None,
        on_progress: object = None,
        cancel_check: object = None,
    ) -> int:
        """Extract frames from *source_path* at regular intervals via FFmpeg.

        Uses the ``fps`` video filter for efficient batch extraction.
        Returns the number of frames extracted.
        """
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise FileNotFoundError("FFmpeg not found")

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW

        fps_value = 1000.0 / interval_ms  # e.g., 1.0 for 1000ms interval

        cmd = [
            ffmpeg,
            "-i", source_path,
            "-vf", f"fps={fps_value},scale={width}:-1",
            "-q:v", "5",
            "-vsync", "vfr",
            "-y",
            str(output_dir / "frame_%06d.jpg"),
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
        )

        # Poll with cancel check
        while proc.poll() is None:
            if cancel_check and cancel_check():
                proc.kill()
                proc.wait()
                return 0
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass

        if proc.returncode != 0:
            stderr = proc.stderr.read().decode(errors="replace")
            raise RuntimeError(f"FFmpeg frame extraction failed: {stderr[:300]}")

        # Rename from FFmpeg 1-indexed sequential to ms-based naming
        total_expected = (duration_ms // interval_ms + 1) if duration_ms else 0
        seq_frames = sorted(output_dir.glob("frame_*.jpg"))
        extracted = 0
        for i, frame_path in enumerate(seq_frames):
            ms = i * interval_ms
            new_name = output_dir / f"frame_{ms:09d}.jpg"
            frame_path.rename(new_name)
            extracted += 1
            if on_progress and total_expected > 0:
                on_progress(extracted, total_expected)

        return extracted
