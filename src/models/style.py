"""Subtitle style model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SubtitleStyle:
    """Visual style for subtitle rendering."""

    font_family: str = "Arial"
    font_size: int = 18
    font_bold: bool = True
    font_italic: bool = False
    font_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = 1
    bg_color: str = ""  # empty = transparent
    position: str = "bottom-center"  # bottom-center, top-center, bottom-left, bottom-right
    margin_bottom: int = 40

    def copy(self) -> SubtitleStyle:
        """Return a shallow copy."""
        return SubtitleStyle(
            font_family=self.font_family,
            font_size=self.font_size,
            font_bold=self.font_bold,
            font_italic=self.font_italic,
            font_color=self.font_color,
            outline_color=self.outline_color,
            outline_width=self.outline_width,
            bg_color=self.bg_color,
            position=self.position,
            margin_bottom=self.margin_bottom,
        )
