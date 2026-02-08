"""Template service - loads and manages overlay templates."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from src.models.overlay_template import OverlayTemplate


def _get_builtin_dir() -> Path:
    """Return the built-in templates directory."""
    return Path(__file__).resolve().parent.parent.parent / "resources" / "templates"


def _get_user_dir() -> Path:
    """Return the user templates directory, creating it if needed."""
    user_dir = Path.home() / ".fastmoviemaker" / "templates"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


class TemplateService:
    """Manages built-in and user overlay templates."""

    def __init__(self):
        self._builtin: list[OverlayTemplate] = []
        self._user: list[OverlayTemplate] = []
        self._load_builtin()
        self._load_user()

    # ------------------------------------------------------------------ Load

    def _load_builtin(self) -> None:
        manifest_path = _get_builtin_dir() / "manifest.json"
        if not manifest_path.exists():
            self._builtin = []
            return
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            templates_dir = _get_builtin_dir()
            self._builtin = []
            for item in data.get("templates", []):
                # Resolve relative paths to absolute
                if item.get("image_path") and not Path(item["image_path"]).is_absolute():
                    item["image_path"] = str(templates_dir / item["image_path"])
                if item.get("thumbnail_path") and not Path(item["thumbnail_path"]).is_absolute():
                    item["thumbnail_path"] = str(templates_dir / item["thumbnail_path"])
                item["is_builtin"] = True
                self._builtin.append(OverlayTemplate.from_dict(item))
        except (json.JSONDecodeError, KeyError):
            self._builtin = []

    def _load_user(self) -> None:
        manifest_path = _get_user_dir() / "user_manifest.json"
        if not manifest_path.exists():
            self._user = []
            return
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            self._user = [
                OverlayTemplate.from_dict({**item, "is_builtin": False})
                for item in data.get("templates", [])
            ]
        except (json.JSONDecodeError, KeyError):
            self._user = []

    def _save_user(self) -> None:
        manifest_path = _get_user_dir() / "user_manifest.json"
        data = {"templates": [t.to_dict() for t in self._user]}
        manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ Query

    def list_templates(
        self,
        aspect_ratio: str | None = None,
        builtin_only: bool = False,
        user_only: bool = False,
    ) -> list[OverlayTemplate]:
        if builtin_only:
            items = list(self._builtin)
        elif user_only:
            items = list(self._user)
        else:
            items = self._builtin + self._user

        if aspect_ratio:
            items = [
                t for t in items
                if t.aspect_ratio == aspect_ratio or t.aspect_ratio == "any"
            ]
        return items

    def get_template(self, template_id: str) -> OverlayTemplate | None:
        for t in self._builtin + self._user:
            if t.template_id == template_id:
                return t
        return None

    # ------------------------------------------------------------------ User CRUD

    def add_user_template(
        self,
        image_path: str | Path,
        name: str,
        aspect_ratio: str = "16:9",
        category: str = "frame",
        opacity: float = 1.0,
    ) -> OverlayTemplate | None:
        image_path = Path(image_path)
        if not image_path.exists():
            return None

        template_id = uuid.uuid4().hex[:12]
        user_dir = _get_user_dir()

        # Copy image to user templates dir
        dest = user_dir / f"{template_id}{image_path.suffix}"
        shutil.copy2(image_path, dest)

        # Generate thumbnail
        thumb_path = self._generate_thumbnail(dest, template_id)

        template = OverlayTemplate(
            template_id=template_id,
            name=name,
            image_path=str(dest),
            thumbnail_path=str(thumb_path) if thumb_path else "",
            category=category,
            aspect_ratio=aspect_ratio,
            opacity=opacity,
            is_builtin=False,
        )
        self._user.append(template)
        self._save_user()
        return template

    def remove_user_template(self, template_id: str) -> bool:
        for i, t in enumerate(self._user):
            if t.template_id == template_id:
                # Clean up files
                if t.image_path and Path(t.image_path).exists():
                    Path(t.image_path).unlink(missing_ok=True)
                if t.thumbnail_path and Path(t.thumbnail_path).exists():
                    Path(t.thumbnail_path).unlink(missing_ok=True)
                self._user.pop(i)
                self._save_user()
                return True
        return False

    def _generate_thumbnail(self, image_path: Path, template_id: str) -> Path | None:
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QImage

            img = QImage(str(image_path))
            if img.isNull():
                return None
            scaled = img.scaledToWidth(160, Qt.TransformationMode.SmoothTransformation)
            thumb_path = _get_user_dir() / f"{template_id}_thumb.png"
            if scaled.save(str(thumb_path), "PNG"):
                return thumb_path
        except Exception:
            pass
        return None
