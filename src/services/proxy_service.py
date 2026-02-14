"""Service for generating and managing proxy media for better editing performance."""

from __future__ import annotations

import logging
import subprocess
import sys
import hashlib
from pathlib import Path

from src.utils.config import find_ffmpeg

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

def generate_proxy(video_path: Path, proxy_path: Path, force: bool = False) -> bool:
    """Generate a low-res (720p) proxy of the video.
    
    Args:
        video_path: Source high-res video.
        proxy_path: Destination proxy path.
        force: If True, overwrite existing proxy.
        
    Returns:
        True if proxy was generated successfully or already exists.
    """
    if proxy_path.exists() and not force:
        logger.info(f"Proxy already exists: {proxy_path}")
        return True

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        logger.error("FFmpeg not found for proxy generation.")
        return False

    logger.info(f"Generating proxy for {video_path} -> {proxy_path}")
    
    # Proxy settings: 720p, H.264, low bitrate, fast preset
    cmd = [
        ffmpeg,
        "-y",
        "-i", str(video_path),
        "-vf", "scale=-2:720", # Height 720, width auto (even)
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "30",          # Lower quality
        "-c:a", "aac",
        "-b:a", "128k",
        str(proxy_path)
    ]

    kwargs = dict(capture_output=True, text=True)
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(cmd, **kwargs)
        if result.returncode != 0:
            logger.error(f"Proxy generation failed:\n{result.stderr[:500]}")
            return False
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
