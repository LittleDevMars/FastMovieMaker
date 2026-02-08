"""Tests for i18n (internationalization) module."""

from src.utils.i18n import init_language, tr, current_language


class TestI18n:
    """Test the tr() translation function."""

    def test_tr_returns_key_for_english(self):
        init_language("en")
        assert tr("&File") == "&File"
        assert tr("Ready") == "Ready"

    def test_tr_returns_korean(self):
        init_language("ko")
        assert tr("&File") == "파일(&F)"
        assert tr("Ready") == "준비"

    def test_tr_fallback_for_missing_key(self):
        init_language("ko")
        assert tr("nonexistent_key_xyz_12345") == "nonexistent_key_xyz_12345"

    def test_unknown_language_falls_back(self):
        init_language("xx")
        assert tr("&File") == "&File"

    def test_current_language(self):
        init_language("en")
        assert current_language() == "en"
        init_language("ko")
        assert current_language() == "ko"

    def test_ko_coverage_menus(self):
        """Verify key menu items have Korean translations."""
        init_language("ko")
        assert tr("&Edit") != "&Edit"
        assert tr("&Subtitles") != "&Subtitles"
        assert tr("&Help") != "&Help"
        assert tr("&Quit") != "&Quit"

    def test_ko_coverage_dialogs(self):
        """Verify key dialog strings have Korean translations."""
        init_language("ko")
        assert tr("Preferences") != "Preferences"
        assert tr("Export Video") != "Export Video"
        assert tr("Generate Subtitles (Whisper)") != "Generate Subtitles (Whisper)"
        assert tr("Translate Subtitles") != "Translate Subtitles"

    def test_ko_coverage_status(self):
        """Verify key status messages have Korean translations."""
        init_language("ko")
        assert tr("No Video") != "No Video"
        assert tr("No Subtitles") != "No Subtitles"
        assert tr("FFmpeg Missing") != "FFmpeg Missing"

    def test_reinit_switches_language(self):
        """Verify that re-initializing switches the language."""
        init_language("ko")
        assert tr("Ready") == "준비"
        init_language("en")
        assert tr("Ready") == "Ready"
