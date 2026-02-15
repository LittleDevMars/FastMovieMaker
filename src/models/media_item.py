"""Media library item data model (pure Python, no Qt dependency)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MediaItem:
    """Represents a media file in the library."""

    item_id: str
    file_path: str
    file_name: str
    media_type: str         # "video" or "image"
    added_at: str           # ISO 8601 timestamp
    thumbnail_path: str = ""
    duration_ms: int = 0    # Video duration (0 for images)
    width: int = 0
    height: int = 0
    file_size: int = 0      # Bytes
    favorite: bool = False

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "media_type": self.media_type,
            "added_at": self.added_at,
            "thumbnail_path": self.thumbnail_path,
            "duration_ms": self.duration_ms,
            "width": self.width,
            "height": self.height,
            "file_size": self.file_size,
            "favorite": self.favorite,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MediaItem:
        return cls(
            item_id=data["item_id"],
            file_path=data["file_path"],
            file_name=data["file_name"],
            media_type=data["media_type"],
            added_at=data["added_at"],
            thumbnail_path=data.get("thumbnail_path", ""),
            duration_ms=data.get("duration_ms", 0),
            width=data.get("width", 0),
            height=data.get("height", 0),
            file_size=data.get("file_size", 0),
            favorite=data.get("favorite", False),
        )
