"""Image overlay (PIP) data models (pure Python, no Qt dependency)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageOverlay:
    """A single image overlay with time range and position on the video."""

    start_ms: int
    end_ms: int
    image_path: str  # Absolute path to image file
    x_percent: float = 70.0  # Left position as % of video width (0-100)
    y_percent: float = 10.0  # Top position as % of video height (0-100)
    scale_percent: float = 25.0  # Image width as % of video width (1-100)
    opacity: float = 1.0  # 0.0-1.0

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def file_name(self) -> str:
        return Path(self.image_path).name

    def to_dict(self) -> dict:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "image_path": self.image_path,
            "x_percent": self.x_percent,
            "y_percent": self.y_percent,
            "scale_percent": self.scale_percent,
            "opacity": self.opacity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ImageOverlay:
        return cls(
            start_ms=data["start_ms"],
            end_ms=data["end_ms"],
            image_path=data["image_path"],
            x_percent=data.get("x_percent", 70.0),
            y_percent=data.get("y_percent", 10.0),
            scale_percent=data.get("scale_percent", 25.0),
            opacity=data.get("opacity", 1.0),
        )


@dataclass
class ImageOverlayTrack:
    """An ordered collection of image overlays."""

    overlays: list[ImageOverlay] = field(default_factory=list)
    locked: bool = False
    hidden: bool = False

    def overlays_at(self, position_ms: int) -> list[ImageOverlay]:
        """Return all overlays active at the given position."""
        return [
            ov for ov in self.overlays
            if ov.start_ms <= position_ms < ov.end_ms
        ]

    def add_overlay(self, overlay: ImageOverlay) -> None:
        """Add an overlay and keep the list sorted by start time."""
        self.overlays.append(overlay)
        self.overlays.sort(key=lambda o: o.start_ms)

    def remove_overlay(self, index: int) -> None:
        """Remove the overlay at *index*."""
        if 0 <= index < len(self.overlays):
            self.overlays.pop(index)

    def __len__(self) -> int:
        return len(self.overlays)

    def __iter__(self):
        return iter(self.overlays)

    def __getitem__(self, index: int) -> ImageOverlay:
        return self.overlays[index]
