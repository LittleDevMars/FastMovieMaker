"""
Bundled FFmpeg using imageio-ffmpeg.
Automatically downloads FFmpeg binaries if not found.
"""
from __future__ import annotations

import os
from pathlib import Path


def get_bundled_ffmpeg() -> str:
    """
    Get FFmpeg executable path.
    Uses imageio-ffmpeg to auto-download if not found.

    Returns:
        Path to ffmpeg executable

    Raises:
        ImportError: If imageio-ffmpeg is not installed
        RuntimeError: If FFmpeg cannot be obtained
    """
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        return ffmpeg_path
    except ImportError:
        raise ImportError(
            "imageio-ffmpeg is not installed.\n"
            "Install with: pip install imageio-ffmpeg"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to get bundled FFmpeg: {e}")


def get_bundled_ffprobe() -> str | None:
    """
    Get FFprobe executable path.
    Tries to find it alongside bundled FFmpeg.

    Returns:
        Path to ffprobe or None if not found
    """
    try:
        ffmpeg_path = get_bundled_ffmpeg()
        ffmpeg_dir = Path(ffmpeg_path).parent

        # Look for ffprobe in the same directory
        import sys
        if sys.platform == "win32":
            ffprobe_path = ffmpeg_dir / "ffprobe.exe"
        else:
            ffprobe_path = ffmpeg_dir / "ffprobe"

        if ffprobe_path.exists():
            return str(ffprobe_path)

        # Fall back to system ffprobe
        import shutil
        return shutil.which("ffprobe")

    except Exception:
        return None


# Example usage:
if __name__ == "__main__":
    try:
        ffmpeg = get_bundled_ffmpeg()
        print(f"✅ FFmpeg: {ffmpeg}")

        ffprobe = get_bundled_ffprobe()
        if ffprobe:
            print(f"✅ FFprobe: {ffprobe}")
        else:
            print("⚠️  FFprobe not found (will use system version)")

    except Exception as e:
        print(f"❌ Error: {e}")
