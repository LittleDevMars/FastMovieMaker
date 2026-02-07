"""Tests for audio extractor (requires FFmpeg)."""

import pytest
from pathlib import Path

from src.utils.config import find_ffmpeg


class TestFindFfmpeg:
    def test_ffmpeg_exists(self):
        result = find_ffmpeg()
        # May be None in CI without FFmpeg, so just check it doesn't crash
        assert result is None or Path(result).name.startswith("ffmpeg")
