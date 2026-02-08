"""Overlay template data model (pure Python, no Qt dependency)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OverlayTemplate:
    """Represents a video overlay template (transparent PNG)."""

    template_id: str
    name: str
    image_path: str
    thumbnail_path: str
    category: str       # "frame", "watermark", "lower_third"
    aspect_ratio: str   # "16:9", "9:16", "any"
    opacity: float = 1.0
    is_builtin: bool = True

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "image_path": self.image_path,
            "thumbnail_path": self.thumbnail_path,
            "category": self.category,
            "aspect_ratio": self.aspect_ratio,
            "opacity": self.opacity,
            "is_builtin": self.is_builtin,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OverlayTemplate:
        return cls(
            template_id=data["template_id"],
            name=data["name"],
            image_path=data["image_path"],
            thumbnail_path=data.get("thumbnail_path", ""),
            category=data.get("category", "frame"),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
            opacity=data.get("opacity", 1.0),
            is_builtin=data.get("is_builtin", True),
        )
