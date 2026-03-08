"""
Hardware acceleration utilities for FFmpeg.
Detects and validates platform-specific hardware encoders.
"""
from __future__ import annotations

import sys
from typing import Any

from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner


def _software_encoder(codec: str) -> str:
    if codec == "hevc":
        return "libx265"
    if codec == "prores":
        return "prores_ks"
    return "libx264"


def _default_flags(codec: str, encoder: str) -> list[str]:
    # Keep existing defaults to preserve output behavior.
    if "videotoolbox" in encoder:
        if codec in ("h264", "hevc"):
            return ["-q:v", "65", "-realtime", "0"]
        if codec == "prores":
            return ["-profile:v", "2"]
    if "nvenc" in encoder:
        return ["-preset", "p4", "-cq", "23"]
    if "qsv" in encoder:
        return ["-global_quality", "23", "-look_ahead", "1"]
    if "amf" in encoder:
        return ["-rc", "cqp", "-qp_i", "23", "-qp_p", "23", "-qp_b", "23"]
    if "vaapi" in encoder:
        return ["-qp", "23"]
    if encoder == "libx265":
        return ["-preset", "medium", "-crf", "23"]
    if encoder == "prores_ks":
        return ["-profile:v", "2"]
    return ["-preset", "medium", "-crf", "23"]


def _encoder_for_backend(codec: str, backend: str) -> str:
    if backend == "videotoolbox":
        if codec == "hevc":
            return "hevc_videotoolbox"
        if codec == "prores":
            return "prores_videotoolbox"
        return "h264_videotoolbox"
    if backend == "nvenc":
        return "hevc_nvenc" if codec == "hevc" else "h264_nvenc"
    if backend == "qsv":
        return "hevc_qsv" if codec == "hevc" else "h264_qsv"
    if backend == "amf":
        return "hevc_amf" if codec == "hevc" else "h264_amf"
    if backend == "vaapi":
        return "hevc_vaapi" if codec == "hevc" else "h264_vaapi"
    if backend == "software":
        return _software_encoder(codec)
    return _software_encoder(codec)


def _platform_backend_priority() -> list[str]:
    platform = sys.platform
    if platform == "darwin":
        return ["videotoolbox", "software"]
    if platform == "win32":
        return ["nvenc", "qsv", "amf", "software"]
    if platform.startswith("linux"):
        return ["vaapi", "nvenc", "software"]
    return ["software"]


def _probe_encoder_help(encoder: str) -> tuple[bool, str | None]:
    """Validate encoder by running ffmpeg '-h encoder=<name>' best-effort."""
    runner = get_ffmpeg_runner()
    if not runner.is_available():
        return False, "ffmpeg unavailable"

    try:
        result = runner.run(["-hide_banner", "-h", f"encoder={encoder}"], timeout=5)
    except Exception as exc:
        return False, str(exc)

    output = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    if result.returncode != 0:
        return False, f"ffmpeg returned {result.returncode}"
    if "unknown encoder" in output or "is not recognized" in output:
        return False, "encoder help not available"
    return True, None


def _available_encoder_names() -> set[str]:
    runner = get_ffmpeg_runner()
    if not runner.is_available():
        return set()

    try:
        result = runner.run(["-hide_banner", "-encoders"], timeout=5)
    except Exception:
        return set()

    names: set[str] = set()
    for line in (result.stdout or "").splitlines():
        # Typical format: " V....D h264_nvenc ..."
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith(("V", "A", "S", ".")):
            names.add(parts[1])
    return names


def get_encoder_candidates(codec: str = "h264") -> list[dict[str, Any]]:
    """Return ordered encoder candidates for the current platform.

    Includes validated hardware encoders first, then software fallback.
    """
    available = _available_encoder_names()
    candidates: list[dict[str, Any]] = []

    for backend in _platform_backend_priority():
        encoder = _encoder_for_backend(codec, backend)

        # Always include software fallback.
        if backend == "software":
            candidates.append(
                {
                    "backend": backend,
                    "encoder": encoder,
                    "flags": _default_flags(codec, encoder),
                    "is_hardware": False,
                    "reason": None,
                }
            )
            continue

        if available and encoder not in available:
            continue

        ok, reason = _probe_encoder_help(encoder)
        if ok:
            candidates.append(
                {
                    "backend": backend,
                    "encoder": encoder,
                    "flags": _default_flags(codec, encoder),
                    "is_hardware": True,
                    "reason": None,
                }
            )
        elif available and encoder in available:
            # Listed but unusable; not candidate but useful as reason via get_hw_info.
            continue

    # Safety net: never return empty.
    if not candidates:
        sw = _software_encoder(codec)
        candidates.append(
            {
                "backend": "software",
                "encoder": sw,
                "flags": _default_flags(codec, sw),
                "is_hardware": False,
                "reason": None,
            }
        )
    return candidates


def get_hw_encoder(codec: str = "h264") -> tuple[str, list[str]]:
    """Get best encoder (hardware preferred) for current platform.

    Compatibility wrapper kept for existing callers.
    """
    candidates = get_encoder_candidates(codec)
    first = candidates[0]
    return first["encoder"], list(first["flags"])


def _backend_codec_map() -> dict[str, list[str]]:
    return {
        "videotoolbox": ["h264", "hevc", "prores"],
        "nvenc": ["h264", "hevc"],
        "qsv": ["h264", "hevc"],
        "amf": ["h264", "hevc"],
        "vaapi": ["h264", "hevc"],
        "software": ["h264", "hevc", "prores"],
    }


def get_hw_info() -> dict:
    """Get hardware acceleration details for UI.

    Returns:
        {
            "platform": str,
            "encoders": dict[str, list[str]],
            "recommended": str | None,
            "candidates": list[str],
            "unavailable_reasons": dict[str, str],
        }
    """
    platform = sys.platform
    info: dict[str, Any] = {
        "platform": platform,
        "encoders": {},
        "recommended": None,
        "candidates": [],
        "unavailable_reasons": {},
    }

    available = _available_encoder_names()
    backend_codecs = _backend_codec_map()

    if not available:
        info["unavailable_reasons"]["ffmpeg"] = "FFmpeg unavailable or encoders list failed"

    for backend, codecs in backend_codecs.items():
        encoder = _encoder_for_backend("h264", backend)
        if backend == "software":
            info["encoders"][backend] = codecs
            continue

        if available and encoder not in available:
            info["unavailable_reasons"][backend] = f"{encoder} not listed in ffmpeg -encoders"
            continue

        ok, reason = _probe_encoder_help(encoder)
        if ok:
            info["encoders"][backend] = codecs
        else:
            info["unavailable_reasons"][backend] = reason or "encoder help probe failed"

    candidates = get_encoder_candidates("h264")
    info["candidates"] = [c["encoder"] for c in candidates]
    if candidates:
        info["recommended"] = candidates[0]["encoder"]

    return info


if __name__ == "__main__":
    print("Hardware acceleration detection")
    hw_info = get_hw_info()
    print(f"Platform: {hw_info['platform']}")
    print(f"Recommended: {hw_info.get('recommended', 'N/A')}")
    print(f"Candidates: {hw_info.get('candidates', [])}")
    if hw_info.get("unavailable_reasons"):
        print("Unavailable reasons:")
        for key, reason in hw_info["unavailable_reasons"].items():
            print(f"  {key}: {reason}")
