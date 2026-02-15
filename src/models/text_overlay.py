"""Text overlay data models (pure Python, no Qt dependency)."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.style import SubtitleStyle


@dataclass(slots=True)
class TextOverlay:
    """A single independent text overlay with time range, position, and style."""

    start_ms: int
    end_ms: int
    text: str
    x_percent: float = 50.0  # Anchor point X position as % of video width (0-100)
    y_percent: float = 50.0  # Anchor point Y position as % of video height (0-100)
    alignment: str = "center"  # left, center, right
    v_alignment: str = "middle" # top, middle, bottom
    opacity: float = 1.0     # 0.0-1.0
    style: SubtitleStyle | None = None  # None = use project default style

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict:
        d = {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "x_percent": self.x_percent,
            "y_percent": self.y_percent,
            "alignment": self.alignment,
            "v_alignment": self.v_alignment,
            "opacity": self.opacity,
        }
        if self.style:
            # Note: Assuming SubtitleStyle has a to_dict method or similar
            # If not, we might need a manual dict conversion
            from dataclasses import asdict
            d["style"] = asdict(self.style)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> TextOverlay:
        from src.models.style import SubtitleStyle
        style_data = data.get("style")
        style = SubtitleStyle(**style_data) if style_data else None
        
        return cls(
            start_ms=data["start_ms"],
            end_ms=data["end_ms"],
            text=data["text"],
            x_percent=data.get("x_percent", 50.0),
            y_percent=data.get("y_percent", 50.0),
            alignment=data.get("alignment", "center"),
            v_alignment=data.get("v_alignment", "middle"),
            opacity=data.get("opacity", 1.0),
            style=style,
        )


@dataclass(slots=True)
class TextOverlayTrack:
    """An ordered collection of text overlays."""

    overlays: list[TextOverlay] = field(default_factory=list)
    locked: bool = False
    hidden: bool = False

    def overlays_at(self, position_ms: int) -> list[TextOverlay]:
        """Return all text overlays active at the given position.

        이진 탐색으로 시작점 한정 후 선형 탐색.
        """
        if not self.overlays:
            return []
        idx = bisect.bisect_right(self.overlays, position_ms, key=lambda o: o.start_ms)
        return [ov for ov in self.overlays[:idx] if ov.end_ms > position_ms]

    def add_overlay(self, overlay: TextOverlay) -> None:
        """Add a text overlay and keep the list sorted by start time. bisect.insort O(n)."""
        bisect.insort(self.overlays, overlay, key=lambda o: o.start_ms)

    def remove_overlay(self, index: int) -> None:
        """Remove the text overlay at *index*."""
        if 0 <= index < len(self.overlays):
            self.overlays.pop(index)

    def __len__(self) -> int:
        return len(self.overlays)

    def __iter__(self):
        return iter(self.overlays)

    def __getitem__(self, index: int) -> TextOverlay:
        return self.overlays[index]
