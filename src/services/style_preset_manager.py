"""Manager for saving and loading subtitle style presets."""

from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import QSettings

from src.models.style import SubtitleStyle


class StylePresetManager:
    """Manages subtitle style presets using QSettings."""

    def __init__(self):
        self._settings = QSettings()
        self._settings.beginGroup("StylePresets")

    def __del__(self):
        """Clean up settings group."""
        try:
            self._settings.endGroup()
        except:
            pass

    def save_preset(self, name: str, style: SubtitleStyle) -> None:
        """Save a style as a preset.

        Args:
            name: Preset name (will be used as the key)
            style: SubtitleStyle to save
        """
        # Save each field individually
        self._settings.beginGroup(name)
        self._settings.setValue("font_family", style.font_family)
        self._settings.setValue("font_size", style.font_size)
        self._settings.setValue("font_bold", style.font_bold)
        self._settings.setValue("font_italic", style.font_italic)
        self._settings.setValue("font_color", style.font_color)
        self._settings.setValue("outline_color", style.outline_color)
        self._settings.setValue("outline_width", style.outline_width)
        self._settings.setValue("bg_color", style.bg_color)
        self._settings.setValue("position", style.position)
        self._settings.setValue("margin_bottom", style.margin_bottom)
        self._settings.endGroup()
        self._settings.sync()

    def load_preset(self, name: str) -> SubtitleStyle | None:
        """Load a style preset by name.

        Args:
            name: Preset name

        Returns:
            SubtitleStyle if found, None otherwise
        """
        if not self._settings.contains(f"{name}/font_family"):
            return None

        self._settings.beginGroup(name)

        style = SubtitleStyle(
            font_family=self._settings.value("font_family", "Arial"),
            font_size=int(self._settings.value("font_size", 18)),
            font_bold=self._settings.value("font_bold", True, type=bool),
            font_italic=self._settings.value("font_italic", False, type=bool),
            font_color=self._settings.value("font_color", "#FFFFFF"),
            outline_color=self._settings.value("outline_color", "#000000"),
            outline_width=int(self._settings.value("outline_width", 1)),
            bg_color=self._settings.value("bg_color", ""),
            position=self._settings.value("position", "bottom-center"),
            margin_bottom=int(self._settings.value("margin_bottom", 40)),
        )

        self._settings.endGroup()
        return style

    def delete_preset(self, name: str) -> None:
        """Delete a preset by name.

        Args:
            name: Preset name to delete
        """
        self._settings.remove(name)
        self._settings.sync()

    def rename_preset(self, old_name: str, new_name: str) -> bool:
        """Rename a preset.

        Args:
            old_name: Current preset name
            new_name: New preset name

        Returns:
            True if successful, False if old preset not found or new name exists
        """
        # Check if old preset exists
        if not self._settings.contains(f"{old_name}/font_family"):
            return False

        # Check if new name already exists
        if self._settings.contains(f"{new_name}/font_family"):
            return False

        # Load old preset
        style = self.load_preset(old_name)
        if not style:
            return False

        # Save with new name
        self.save_preset(new_name, style)

        # Delete old preset
        self.delete_preset(old_name)

        return True

    def list_presets(self) -> List[str]:
        """Get list of all preset names.

        Returns:
            List of preset names sorted alphabetically
        """
        # Get all child groups (each preset is a group)
        presets = self._settings.childGroups()
        return sorted(presets)

    def preset_exists(self, name: str) -> bool:
        """Check if a preset exists.

        Args:
            name: Preset name to check

        Returns:
            True if preset exists
        """
        return self._settings.contains(f"{name}/font_family")

    def get_all_presets(self) -> Dict[str, SubtitleStyle]:
        """Get all presets as a dictionary.

        Returns:
            Dictionary mapping preset names to SubtitleStyle objects
        """
        result = {}
        for name in self.list_presets():
            style = self.load_preset(name)
            if style:
                result[name] = style
        return result

    def create_default_presets(self) -> None:
        """Create some default presets if none exist."""
        if self.list_presets():
            return  # Already have presets

        # YouTube Style
        youtube_style = SubtitleStyle(
            font_family="Arial",
            font_size=24,
            font_bold=True,
            font_italic=False,
            font_color="#FFFFFF",
            outline_color="#000000",
            outline_width=2,
            bg_color="",
            position="bottom-center",
            margin_bottom=50,
        )
        self.save_preset("YouTube", youtube_style)

        # Cinema Style
        cinema_style = SubtitleStyle(
            font_family="Times New Roman",
            font_size=20,
            font_bold=False,
            font_italic=True,
            font_color="#FFFFCC",
            outline_color="#000000",
            outline_width=1,
            bg_color="",
            position="bottom-center",
            margin_bottom=30,
        )
        self.save_preset("Cinema", cinema_style)

        # Karaoke Style
        karaoke_style = SubtitleStyle(
            font_family="Comic Sans MS",
            font_size=28,
            font_bold=True,
            font_italic=False,
            font_color="#FFFF00",
            outline_color="#FF0000",
            outline_width=3,
            bg_color="#00000080",
            position="top-center",
            margin_bottom=20,
        )
        self.save_preset("Karaoke", karaoke_style)

        # Minimal Style
        minimal_style = SubtitleStyle(
            font_family="Helvetica",
            font_size=16,
            font_bold=False,
            font_italic=False,
            font_color="#FFFFFF",
            outline_color="#000000",
            outline_width=1,
            bg_color="",
            position="bottom-center",
            margin_bottom=40,
        )
        self.save_preset("Minimal", minimal_style)
