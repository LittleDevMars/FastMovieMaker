"""Service for generating and managing proxy media for better editing performance."""

from __future__ import annotations

import logging
import hashlib
import subprocess
import threading
from pathlib import Path
from typing import Callable

from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner
from src.services.video_probe import probe_video

logger = logging.getLogger(__name__)

def get_proxy_dir(project_path: Path | None = None) -> Path:
    """Return the directory to store proxy files.
    
    Defaults to ~/.FastMovieMaker/proxies if no project path is given.
    """
    if project_path:
        proxy_dir = project_path.parent / ".proxies"
    else:
        proxy_dir = Path.home() / ".FastMovieMaker" / "proxies"
    
    proxy_dir.mkdir(parents=True, exist_ok=True)
    return proxy_dir

def get_proxy_path(video_path: Path, project_path: Path | None = None) -> Path:
    """Generate a unique proxy path for a given source video."""
    # Use MD5 of absolute path to avoid collisions and keep filenames manageable
    path_hash = hashlib.md5(str(video_path.absolute()).encode()).hexdigest()
    proxy_dir = get_proxy_dir(project_path)
    return proxy_dir / f"proxy_{path_hash}.mp4"

def generate_proxy(
    video_path: Path,
    proxy_path: Path,
    force: bool = False,
    on_progress: Callable[[int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> bool:
    """Generate a low-res (720p) proxy of the video.
    
    Args:
        video_path: Source high-res video.
        proxy_path: Destination proxy path.
        force: If True, overwrite existing proxy.
        on_progress: Optional callback(percentage) for progress updates.
        cancel_check: Optional callback returning True to abort generation.
        
    Returns:
        True if proxy was generated successfully or already exists.
    """
    if proxy_path.exists() and not force:
        logger.info(f"Proxy already exists: {proxy_path}")
        if on_progress:
            on_progress(100)
        return True

    runner = get_ffmpeg_runner()
    if not runner.is_available():
        logger.error("FFmpeg not found for proxy generation.")
        return False

    logger.info(f"Generating proxy for {video_path} -> {proxy_path}")

    # Get duration for progress calculation
    total_duration_sec = 0.0
    if on_progress:
        try:
            info = probe_video(video_path)
            total_duration_sec = info.duration_ms / 1000.0
        except Exception:
            pass

    args = [
        "-y",
        "-i", str(video_path),
        "-vf", "scale=-2:720",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "30",
        "-c:a", "aac",
        "-b:a", "128k",
        "-progress", "pipe:1",
        str(proxy_path),
    ]

    try:
        process = runner.run_async(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # Drain stderr in background to prevent deadlock
        def _drain_stderr():
            try:
                for _ in process.stderr:
                    pass
            except Exception:
                pass

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # Parse stdout for progress
        if process.stdout:
            for line in process.stdout:
                if cancel_check and cancel_check():
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    if proxy_path.exists():
                        proxy_path.unlink(missing_ok=True)
                    return False

                line = line.strip()
                if on_progress and total_duration_sec > 0 and line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=")[1])
                        current_sec = us / 1_000_000
                        pct = int(current_sec / total_duration_sec * 100)
                        on_progress(min(100, max(0, pct)))
                    except (ValueError, IndexError):
                        pass

        if cancel_check and cancel_check():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
            if proxy_path.exists():
                proxy_path.unlink(missing_ok=True)
            return False

        process.wait()
        stderr_thread.join(timeout=5)

        if process.returncode != 0:
            logger.error(f"Proxy generation failed with code {process.returncode}")
            if proxy_path.exists():
                proxy_path.unlink(missing_ok=True)
            return False
            
        if on_progress:
            on_progress(100)
            
        return True
    except Exception as e:
        logger.exception(f"Error during proxy generation: {e}")
        return False

def is_proxy_valid(video_path: Path, proxy_path: Path) -> bool:
    """Check if proxy is still valid (e.g. source hasn't changed)."""
    if not proxy_path.exists():
        return False
    
    # Basic check: source modification time vs proxy modification time
    # This is a bit simplified, but works for most cases.
    return video_path.stat().st_mtime <= proxy_path.stat().st_mtime


class ProxyService:
    """Service class for managing proxies (compatibility wrapper)."""

    def has_proxy(self, source_path: str) -> bool:
        path = Path(source_path)
        proxy = get_proxy_path(path)
        return is_proxy_valid(path, proxy)

    def get_proxy_path(self, source_path: str) -> str:
        return str(get_proxy_path(Path(source_path)))

    def create_worker(self, source_path: str):
        """Create a worker to generate proxy."""
        # Import here to avoid circular imports if any
        from src.workers.proxy_worker import ProxyWorker
        return ProxyWorker(source_path)
