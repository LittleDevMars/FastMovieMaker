"""
Hardware acceleration utilities for FFmpeg.
Detects and uses platform-specific hardware encoders.
"""
from __future__ import annotations

import sys
import subprocess
from pathlib import Path
from typing import List


def get_hw_encoder(codec: str = "h264") -> tuple[str, List[str]]:
    """
    Get the best hardware encoder for the current platform.

    Args:
        codec: Video codec ("h264", "hevc", "prores")

    Returns:
        tuple[encoder_name, extra_flags]
        - encoder_name: e.g., "h264_videotoolbox", "h264_nvenc"
        - extra_flags: Additional FFmpeg flags for optimization

    Examples:
        >>> encoder, flags = get_hw_encoder("h264")
        >>> # macOS: ("h264_videotoolbox", ["-q:v", "65"])
        >>> # Windows NVIDIA: ("h264_nvenc", ["-preset", "p4"])
        >>> # Linux: ("h264_vaapi", [...])
    """
    platform = sys.platform

    # macOS - VideoToolbox (Apple Silicon & Intel)
    if platform == "darwin":
        if codec == "h264":
            return "h264_videotoolbox", [
                "-q:v", "65",  # Quality (0-100, higher = better)
                "-realtime", "0",  # Not real-time (better quality)
            ]
        elif codec == "hevc":
            return "hevc_videotoolbox", [
                "-q:v", "65",
                "-realtime", "0",
            ]
        elif codec == "prores":
            return "prores_videotoolbox", [
                "-profile:v", "2",  # ProRes 422 Standard
            ]

    # Windows - NVIDIA NVENC (if available)
    elif platform == "win32":
        if _check_nvenc_available():
            if codec == "h264":
                return "h264_nvenc", [
                    "-preset", "p4",  # Medium quality
                    "-cq", "23",  # Constant quality
                ]
            elif codec == "hevc":
                return "hevc_nvenc", [
                    "-preset", "p4",
                    "-cq", "23",
                ]

    # Linux - VAAPI (Intel) or NVENC (NVIDIA)
    elif platform.startswith("linux"):
        if _check_nvenc_available():
            if codec == "h264":
                return "h264_nvenc", ["-preset", "medium", "-cq", "23"]
            elif codec == "hevc":
                return "hevc_nvenc", ["-preset", "medium", "-cq", "23"]
        elif _check_vaapi_available():
            if codec == "h264":
                return "h264_vaapi", ["-qp", "23"]
            elif codec == "hevc":
                return "hevc_vaapi", ["-qp", "23"]

    # Fallback to software encoder
    if codec == "h264":
        return "libx264", [
            "-preset", "medium",
            "-crf", "23",
        ]
    elif codec == "hevc":
        return "libx265", [
            "-preset", "medium",
            "-crf", "23",
        ]
    elif codec == "prores":
        return "prores_ks", [
            "-profile:v", "2",
        ]

    # Default fallback
    return "libx264", ["-preset", "medium", "-crf", "23"]


def _check_nvenc_available() -> bool:
    """Check if NVIDIA NVENC encoder is available."""
    try:
        from ..utils.ffmpeg_utils import find_ffmpeg
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return False

        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False


def _check_vaapi_available() -> bool:
    """Check if VAAPI encoder is available (Linux Intel)."""
    try:
        from ..utils.ffmpeg_utils import find_ffmpeg
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return False

        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "h264_vaapi" in result.stdout
    except Exception:
        return False


def get_hw_info() -> dict:
    """
    Get hardware acceleration information.

    Returns:
        dict with platform, available encoders, and recommended settings
    """
    platform = sys.platform
    info = {
        "platform": platform,
        "encoders": {},
        "recommended": None
    }

    # Check available encoders
    try:
        from ..utils.ffmpeg_utils import find_ffmpeg
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                timeout=5
            )
            encoders_output = result.stdout

            # macOS VideoToolbox
            if "h264_videotoolbox" in encoders_output:
                info["encoders"]["videotoolbox"] = ["h264", "hevc", "prores"]
                info["recommended"] = "videotoolbox"

            # NVIDIA NVENC
            if "h264_nvenc" in encoders_output:
                info["encoders"]["nvenc"] = ["h264", "hevc"]
                if not info["recommended"]:
                    info["recommended"] = "nvenc"

            # Intel VAAPI
            if "h264_vaapi" in encoders_output:
                info["encoders"]["vaapi"] = ["h264", "hevc"]
                if not info["recommended"]:
                    info["recommended"] = "vaapi"

            # Software fallback
            if "libx264" in encoders_output:
                info["encoders"]["software"] = ["h264", "hevc", "prores"]
                if not info["recommended"]:
                    info["recommended"] = "software"

    except Exception as e:
        info["error"] = str(e)

    return info


# Test if running as main
if __name__ == "__main__":
    print("🔍 Hardware Acceleration Detection\n")

    # Get hardware info
    hw_info = get_hw_info()
    print(f"Platform: {hw_info['platform']}")
    print(f"Recommended: {hw_info.get('recommended', 'N/A')}")
    print(f"\nAvailable Encoders:")
    for hw_type, codecs in hw_info.get('encoders', {}).items():
        print(f"  {hw_type}: {', '.join(codecs)}")

    print(f"\n🎯 Recommended Settings:")

    # Test H.264
    encoder, flags = get_hw_encoder("h264")
    print(f"\nH.264: {encoder}")
    print(f"  Flags: {' '.join(flags)}")

    # Test HEVC
    encoder, flags = get_hw_encoder("hevc")
    print(f"\nHEVC/H.265: {encoder}")
    print(f"  Flags: {' '.join(flags)}")

    # Test ProRes (macOS only)
    if sys.platform == "darwin":
        encoder, flags = get_hw_encoder("prores")
        print(f"\nProRes: {encoder}")
        print(f"  Flags: {' '.join(flags)}")
