"""Frame thumbnail cache for instant preview during source switching."""

from __future__ import annotations

import hashlib
import subprocess
import shutil
import threading
import tempfile
from pathlib import Path

from PySide6.QtGui import QImage
from src.services.ffmpeg_logger import log_ffmpeg_command, log_ffmpeg_line
from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner


def _ms_from_path(path: Path) -> int:
    """Extract millisecond value from filename like frame_000001000.jpg."""
    stem = path.stem  # e.g., "frame_000001000"
    return int(stem.split("_")[1])


class FrameCacheService:
    """Manages a directory of pre-extracted JPEG frames for quick lookup.

    LRU eviction으로 디스크 캐시 크기를 제한 (HPP Ch.11 — 메모리 관리).

    Cache structure::

        <cache_dir>/
            <source_hash>/
                frame_000000000.jpg   (frame at 0ms)
                frame_000001000.jpg   (frame at 1000ms)
                ...
    """

    # 최대 소스별 캐시 디렉토리 수
    _MAX_SOURCE_DIRS = 10

    def __init__(self) -> None:
        self._cache_dir: Path | None = None
        # LRU 순서 추적: source_path → hash (최근 접근 순)
        self._access_order: list[str] = []

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
        """Return the cache subdirectory for a given source video.

        LRU eviction: 소스 디렉토리 수가 _MAX_SOURCE_DIRS를 초과하면
        가장 오래된 소스의 캐시를 삭제.
        """
        h = hashlib.md5(source_path.encode()).hexdigest()[:12]
        d = self.initialize() / h
        d.mkdir(exist_ok=True)
        # LRU 순서 갱신
        if source_path in self._access_order:
            self._access_order.remove(source_path)
        self._access_order.append(source_path)
        # Eviction
        while len(self._access_order) > self._MAX_SOURCE_DIRS:
            oldest = self._access_order.pop(0)
            old_h = hashlib.md5(oldest.encode()).hexdigest()[:12]
            old_dir = self._cache_dir / old_h
            if old_dir.exists():
                shutil.rmtree(old_dir, ignore_errors=True)
        return d

    def is_cached(self, source_path: str) -> bool:
        """Check if frames have been extracted for this source."""
        d = self.source_cache_dir(source_path)
        return any(d.glob("frame_*.jpg"))

    def get_nearest_frame(self, source_path: str, source_ms: int, threshold_ms: int = 2000) -> Path | None:
        """Find the cached JPEG closest to *source_ms*.

        Uses binary search on sorted filenames (ms encoded as zero-padded
        integers). Returns ``None`` if:
        1. No frames are cached for this source.
        2. The closest frame is further away than *threshold_ms*.
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

        if best_dist > threshold_ms:
            return None

        return best

    def get_frame(self, source_path: str, frame_index: int, fps: float) -> QImage | None:
        """Retrieve the frame image for a specific frame index."""
        if fps <= 0:
            return None

        # Calculate timestamp to match the naming convention in extract_frames
        # We use the same integer interval logic to ensure filenames match
        interval_ms = int(1000 / fps)
        ms = frame_index * interval_ms

        d = self.source_cache_dir(source_path)
        # Try exact match first
        img_path = d / f"frame_{ms:09d}.jpg"

        if img_path.exists():
            return QImage(str(img_path))
        
        return None

    @staticmethod
    def extract_frame_at(source_path: str, ms: int, output_path: Path, quality: int | None = None) -> bool:
        """Extract a single frame at specific timestamp using fast seek (Double-SS).

        Args:
            source_path: Video file path
            ms: Timestamp in milliseconds
            output_path: Destination path for the image
            quality: JPEG quality (1-31, lower is better)

        Returns:
            True if successful, False otherwise
        """
        if quality is None:
            from src.services.settings_manager import SettingsManager
            quality = SettingsManager().get_frame_cache_quality()

        runner = get_ffmpeg_runner()
        if not runner.is_available():
            return False

        target_sec = ms / 1000.0
        input_seek = max(0.0, target_sec - 10.0)
        output_seek = target_sec - input_seek

        args = [
            "-ss", f"{input_seek:.3f}",
            "-i", source_path,
            "-ss", f"{output_seek:.3f}",
            "-frames:v", "1",
            "-q:v", str(quality),
            "-y",
            str(output_path),
        ]

        log_ffmpeg_command(args)

        try:
            runner.run(
                args,
                capture_output=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception:
            return False

    def extract_video_frames(
        self,
        source_path: str,
        fps: float,
        width: int = 640,
        on_progress: object = None,
        cancel_check: object = None,
        quality: int | None = None,
        duration_ms: int | None = None,
    ) -> int:
        """Extract all frames for video playback at the specified FPS."""
        interval_ms = int(1000 / fps) if fps > 0 else 33
        output_dir = self.source_cache_dir(source_path)
        
        if quality is None:
            from src.services.settings_manager import SettingsManager
            quality = SettingsManager().get_frame_cache_quality()

        # Clean up existing cache for this source to avoid mixing framerates
        # (Optional: sophisticated logic could check if existing cache is compatible)
        # For now, we assume if we call this, we want fresh frames for this FPS.
        # But we rely on extract_frames which appends. Let's just call extract_frames.
        return self.extract_frames(source_path, output_dir, interval_ms, width,
                                   duration_ms=duration_ms,
                                   on_progress=on_progress, cancel_check=cancel_check, quality=quality)

    @staticmethod
    def extract_frames(
        source_path: str,
        output_dir: Path,
        interval_ms: int = 1000,
        width: int = 640,
        duration_ms: int | None = None,
        on_progress: object = None,
        cancel_check: object = None,
        quality: int = 5,
    ) -> int:
        """Extract frames from *source_path* at regular intervals via FFmpeg.

        Uses the ``fps`` video filter for efficient batch extraction.
        Returns the number of frames extracted.
        """
        runner = get_ffmpeg_runner()
        if not runner.is_available():
            raise FileNotFoundError("FFmpeg not found")

        fps_value = 1000.0 / interval_ms

        args = [
            "-i", source_path,
            "-vf", f"fps={fps_value},scale={width}:-1",
            "-q:v", str(quality),
            "-vsync", "vfr",
            "-progress", "pipe:1",
            "-y",
            str(output_dir / "frame_%06d.jpg"),
        ]

        log_ffmpeg_command(args)

        proc = runner.run_async(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # Drain stderr in a background thread to log and prevent buffer overflow
        stderr_buffer = []
        def _drain_stderr():
            try:
                for line in proc.stderr:
                    log_ffmpeg_line(line)
                    stderr_buffer.append(line)
                    if len(stderr_buffer) > 20:
                        stderr_buffer.pop(0)
            except Exception:
                pass

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        total_expected = (duration_ms // interval_ms + 1) if duration_ms else 0

        # Poll with cancel check
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break

            if cancel_check and cancel_check():
                proc.kill()
                proc.wait()
                return 0

            if line and on_progress and total_expected > 0:
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=")[1])
                        current_ms = us // 1000
                        current_frame = current_ms // interval_ms
                        # Extraction is phase 1 (0-90% of total work)
                        on_progress(int(current_frame * 0.9), total_expected)
                    except (ValueError, IndexError):
                        pass

        if proc.returncode != 0:
            stderr = "".join(stderr_buffer).strip()
            # 에러 원인은 보통 로그 마지막에 있으므로 마지막 500자를 가져옵니다.
            log_snippet = stderr[-500:] if len(stderr) > 500 else stderr
            raise RuntimeError(log_snippet or f"FFmpeg exit code {proc.returncode}")

        # Rename from FFmpeg 1-indexed sequential to ms-based naming
        seq_frames = sorted(output_dir.glob("frame_*.jpg"))
        num_frames = len(seq_frames)
        extracted = 0
        for i, frame_path in enumerate(seq_frames):
            ms = i * interval_ms
            new_name = output_dir / f"frame_{ms:09d}.jpg"
            frame_path.rename(new_name)
            extracted += 1
            if on_progress and total_expected > 0 and num_frames > 0:
                # Renaming is phase 2 (90-100% of total work)
                progress_val = int(total_expected * 0.9 + (extracted / num_frames) * total_expected * 0.1)
                on_progress(min(progress_val, total_expected), total_expected)

        return extracted
