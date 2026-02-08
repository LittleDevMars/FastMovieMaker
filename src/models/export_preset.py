"""Export preset data models (pure Python, no Qt dependency)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExportPreset:
    """Defines a single export output configuration."""

    name: str
    width: int          # Target width (0 = keep original)
    height: int         # Target height (0 = keep original)
    codec: str          # "h264", "hevc"
    container: str      # "mp4", "mkv", "webm"
    audio_bitrate: str = "192k"
    suffix: str = ""    # Filename suffix, e.g. "_720p"

    @property
    def resolution_label(self) -> str:
        if self.width == 0 and self.height == 0:
            return "Original"
        return f"{self.width}x{self.height}"

    @property
    def file_extension(self) -> str:
        return f".{self.container}"


DEFAULT_PRESETS: list[ExportPreset] = [
    ExportPreset("4K MP4 (H.264)", 3840, 2160, "h264", "mp4", suffix="_4k"),
    ExportPreset("1080p MP4 (H.264)", 1920, 1080, "h264", "mp4", suffix="_1080p"),
    ExportPreset("720p MP4 (H.264)", 1280, 720, "h264", "mp4", suffix="_720p"),
    ExportPreset("480p MP4 (H.264)", 854, 480, "h264", "mp4", suffix="_480p"),
    ExportPreset("1080p MP4 (HEVC)", 1920, 1080, "hevc", "mp4", suffix="_1080p_hevc"),
    ExportPreset("1080p MKV (HEVC)", 1920, 1080, "hevc", "mkv", suffix="_1080p_hevc_mkv"),
    ExportPreset("Original MP4 (H.264)", 0, 0, "h264", "mp4", suffix="_original"),
]


@dataclass
class BatchExportJob:
    """Tracks state of a single export job within a batch."""

    preset: ExportPreset
    output_path: str
    status: str = "pending"     # pending / running / completed / failed / skipped
    error_message: str = ""
    progress_pct: int = 0
