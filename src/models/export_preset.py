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
    crf: int = 23
    speed_preset: str = "medium"
    suffix: str = ""    # Filename suffix, e.g. "_720p"

    @property
    def resolution_label(self) -> str:
        if self.width == 0 and self.height == 0:
            return "Original"
        return f"{self.width}x{self.height}"

    @property
    def file_extension(self) -> str:
        return f".{self.container}"

    def to_dict(self) -> dict:
        """QSettings 직렬화 및 프리셋 저장용 딕셔너리 변환."""
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "codec": self.codec,
            "container": self.container,
            "audio_bitrate": self.audio_bitrate,
            "crf": self.crf,
            "speed_preset": self.speed_preset,
            "suffix": self.suffix,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExportPreset:
        """딕셔너리에서 ExportPreset을 복원한다. 누락 필드는 기본값 사용."""
        return cls(
            name=data["name"],
            width=data.get("width", 0),
            height=data.get("height", 0),
            codec=data.get("codec", "h264"),
            container=data.get("container", "mp4"),
            audio_bitrate=data.get("audio_bitrate", "192k"),
            crf=data.get("crf", 23),
            speed_preset=data.get("speed_preset", "medium"),
            suffix=data.get("suffix", ""),
        )


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
