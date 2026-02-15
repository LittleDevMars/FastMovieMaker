"""Media library service - CRUD, thumbnails, JSON persistence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner
from src.models.media_item import MediaItem
from src.utils.config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS


def _get_library_dir() -> Path:
    """Return the library storage directory, creating it if needed."""
    lib_dir = Path.home() / ".fastmoviemaker"
    lib_dir.mkdir(parents=True, exist_ok=True)
    return lib_dir


def _get_thumbnail_dir() -> Path:
    """Return the thumbnail directory, creating it if needed."""
    thumb_dir = _get_library_dir() / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir


def _get_converted_dir() -> Path:
    """Return the directory for converted files (e.g. GIF to MP4)."""
    conv_dir = _get_library_dir() / "converted"
    conv_dir.mkdir(parents=True, exist_ok=True)
    return conv_dir


class MediaLibraryService:
    """Manages a persistent media library with thumbnails."""

    def __init__(self, library_path: Path | None = None):
        self._library_path = library_path or (_get_library_dir() / "media_library.json")
        self._items: list[MediaItem] = []
        self.load()

    # ------------------------------------------------------------------ Persistence

    def load(self) -> None:
        if not self._library_path.exists():
            self._items = []
            return
        try:
            data = json.loads(self._library_path.read_text(encoding="utf-8"))
            self._items = [MediaItem.from_dict(d) for d in data.get("items", [])]
        except (json.JSONDecodeError, KeyError):
            self._items = []

    def save(self) -> None:
        self._library_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"items": [item.to_dict() for item in self._items]}
        self._library_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ CRUD

    def add_item(self, file_path: str | Path) -> MediaItem | None:
        """Add a media file to the library. Returns the new item or None on error.

        GIF files are automatically converted to MP4 video.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return None

        # Detect media type
        ext = file_path.suffix.lower()
        original_name = file_path.name

        # GIF → MP4 conversion
        if ext == ".gif":
            converted = self._convert_gif_to_mp4(file_path)
            if converted:
                file_path = converted
                ext = ".mp4"
                media_type = "video"
            else:
                # Conversion failed, treat as static image
                media_type = "image"
        elif ext in VIDEO_EXTENSIONS:
            media_type = "video"
        elif ext in IMAGE_EXTENSIONS:
            media_type = "image"
        else:
            return None

        # Check for duplicate (same absolute path)
        abs_path = str(file_path.resolve())
        for item in self._items:
            if item.file_path == abs_path:
                return item  # Already exists

        # Build item
        item_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()

        # Get file size
        try:
            file_size = file_path.stat().st_size
        except OSError:
            file_size = 0

        # Generate thumbnail
        thumb_path = self._generate_thumbnail(file_path, media_type, item_id)

        # Get dimensions and duration
        width, height, duration_ms = 0, 0, 0
        if media_type == "video":
            width, height, duration_ms = self._get_video_info(file_path)
        elif media_type == "image":
            width, height = self._get_image_dimensions(file_path)

        item = MediaItem(
            item_id=item_id,
            file_path=abs_path,
            file_name=original_name,
            media_type=media_type,
            added_at=now,
            thumbnail_path=str(thumb_path) if thumb_path else "",
            duration_ms=duration_ms,
            width=width,
            height=height,
            file_size=file_size,
        )
        self._items.append(item)
        self.save()
        return item

    def remove_item(self, item_id: str) -> bool:
        """Remove an item and its thumbnail. Returns True if found."""
        for i, item in enumerate(self._items):
            if item.item_id == item_id:
                # Clean up thumbnail
                if item.thumbnail_path:
                    thumb = Path(item.thumbnail_path)
                    if thumb.exists():
                        thumb.unlink(missing_ok=True)
                self._items.pop(i)
                self.save()
                return True
        return False

    def clear_all(self) -> int:
        """Remove all items and their thumbnails. Returns count removed."""
        count = len(self._items)
        for item in self._items:
            if item.thumbnail_path:
                thumb = Path(item.thumbnail_path)
                if thumb.exists():
                    thumb.unlink(missing_ok=True)
        self._items.clear()
        self.save()
        return count

    def list_items(self, media_type: str | None = None) -> list[MediaItem]:
        """List items, optionally filtered by media type."""
        if media_type is None:
            return list(self._items)
        return [item for item in self._items if item.media_type == media_type]

    def get_item(self, item_id: str) -> MediaItem | None:
        for item in self._items:
            if item.item_id == item_id:
                return item
        return None

    def toggle_favorite(self, item_id: str) -> bool:
        """Toggle favorite status. Returns new favorite state."""
        item = self.get_item(item_id)
        if item:
            item.favorite = not item.favorite
            self.save()
            return item.favorite
        return False

    def get_favorites(self) -> list[MediaItem]:
        return [item for item in self._items if item.favorite]

    # ------------------------------------------------------------------ GIF Conversion

    def _convert_gif_to_mp4(self, gif_path: Path) -> Path | None:
        """Convert an animated GIF to MP4 using FFmpeg. Returns the MP4 path or None."""
        runner = get_ffmpeg_runner()
        if not runner.is_available():
            return None

        conv_dir = _get_converted_dir()
        mp4_name = f"{gif_path.stem}_{uuid.uuid4().hex[:8]}.mp4"
        mp4_path = conv_dir / mp4_name

        args = [
            "-i", str(gif_path),
            "-movflags", "faststart",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-y",
            str(mp4_path),
        ]
        try:
            runner.run(args, timeout=60)
            if mp4_path.exists() and mp4_path.stat().st_size > 0:
                return mp4_path
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ Thumbnails

    def _generate_thumbnail(
        self, file_path: Path, media_type: str, item_id: str
    ) -> Path | None:
        thumb_dir = _get_thumbnail_dir()
        thumb_path = thumb_dir / f"{item_id}.png"

        try:
            if media_type == "video":
                return self._generate_video_thumbnail(file_path, thumb_path)
            elif media_type == "image":
                return self._generate_image_thumbnail(file_path, thumb_path)
        except Exception:
            return None
        return None

    def _generate_video_thumbnail(self, video_path: Path, thumb_path: Path) -> Path | None:
        runner = get_ffmpeg_runner()
        if not runner.is_available():
            return None

        args = [
            "-ss", "1",
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", "scale=160:-1",
            "-y",
            str(thumb_path),
        ]
        try:
            runner.run(args, timeout=10)
            if thumb_path.exists() and thumb_path.stat().st_size > 0:
                return thumb_path
        except Exception:
            pass
        return None

    def _generate_image_thumbnail(self, image_path: Path, thumb_path: Path) -> Path | None:
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QImage

            img = QImage(str(image_path))
            if img.isNull():
                return None
            scaled = img.scaledToWidth(160, Qt.TransformationMode.SmoothTransformation)
            if scaled.save(str(thumb_path), "PNG"):
                return thumb_path
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ Metadata

    def _get_video_info(self, video_path: Path) -> tuple[int, int, int]:
        """Returns (width, height, duration_ms)."""
        runner = get_ffmpeg_runner()
        if not runner.ffprobe_path:
            return 0, 0, 0

        try:
            result = runner.run_ffprobe(
                [
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-show_entries", "format=duration",
                    "-of", "json",
                    str(video_path),
                ],
                timeout=10,
            )
            data = json.loads(result.stdout)
            width = 0
            height = 0
            if data.get("streams"):
                stream = data["streams"][0]
                width = stream.get("width", 0)
                height = stream.get("height", 0)
            duration_ms = 0
            if data.get("format", {}).get("duration"):
                duration_ms = int(float(data["format"]["duration"]) * 1000)
            return width, height, duration_ms
        except Exception:
            return 0, 0, 0

    def _get_image_dimensions(self, image_path: Path) -> tuple[int, int]:
        """Returns (width, height)."""
        try:
            from PySide6.QtGui import QImage

            img = QImage(str(image_path))
            if not img.isNull():
                return img.width(), img.height()
        except Exception:
            pass
        return 0, 0
