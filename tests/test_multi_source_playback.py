"""Tests for multi-source playback: scrubbing, source switching, play/pause.

Uses a lightweight harness that binds actual MainWindow methods to a mock
object tree, avoiding full MainWindow construction (which requires a live
Qt multimedia backend).  Every assertion tests the REAL production code.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from pathlib import Path

from PySide6.QtMultimedia import QMediaPlayer

from src.models.project import ProjectState
from src.models.video_clip import VideoClip, VideoClipTrack

# Import the actual class so we can borrow its methods
from src.ui.main_window import MainWindow


# Use str(Path(...)) so slashes match what production code produces
PRIMARY = str(Path("C:/test/primary.mp4"))
EXTERNAL = str(Path("C:/test/external.mp4"))


# ── Harness ──────────────────────────────────────────────────────────


def _mock_player(**overrides):
    """Create a mock QMediaPlayer with stopped-state defaults."""
    p = MagicMock()
    p.playbackState.return_value = QMediaPlayer.PlaybackState.StoppedState
    p.isPlaying.return_value = False
    p.position.return_value = 0
    for k, v in overrides.items():
        getattr(p, k).return_value = v
    return p


class _Harness:
    """Stand-in for MainWindow — has only playback-related state."""

    def __init__(self):
        self._project = ProjectState()
        self._player = _mock_player()
        self._tts_player = _mock_player()
        self._tts_audio_output = MagicMock()
        self._current_playback_source: str | None = None
        self._current_clip_index: int = 0
        self._pending_seek_ms: int | None = None
        self._pending_auto_play: bool = False
        self._play_intent: bool = False
        self._frame_cache_service = None
        self._showing_cached_frame = False
        self._render_pause_timer = MagicMock()
        self._pending_seek_timer = MagicMock()
        self._timeline = MagicMock()
        self._timeline.get_playhead.return_value = 0  # default timeline position
        self._controls = MagicMock()
        self._video_widget = MagicMock()

    def statusBar(self):  # noqa: N802
        return MagicMock()


# Bind the real MainWindow methods onto the harness class
for _name in (
    "_toggle_play_pause",
    "_on_timeline_seek",
    "_on_position_changed_by_user",
    "_switch_player_source",
    "_on_media_status_changed",
    "_on_player_position_changed",
    "_sync_clip_index_from_position",
    "_sync_tts_playback",
):
    setattr(_Harness, _name, getattr(MainWindow, _name))


# ── Fixture ──────────────────────────────────────────────────────────


@pytest.fixture
def hw():
    """Return a fresh harness wired with a 3-clip multi-source timeline.

    Timeline layout:
        clip 0  primary  0–10 s   →  timeline  0–10 s
        clip 1  external 0– 5 s   →  timeline 10–15 s
        clip 2  primary 10–20 s   →  timeline 15–25 s
    """
    h = _Harness()
    track = VideoClipTrack(clips=[
        VideoClip(0, 10000),
        VideoClip(0, 5000, source_path=EXTERNAL),
        VideoClip(10000, 20000),
    ])
    h._project.video_path = Path(PRIMARY)
    h._project.duration_ms = track.output_duration_ms
    h._project.video_clip_track = track
    h._current_playback_source = PRIMARY
    h._current_clip_index = 0
    return h


# ── 1. Scrubbing across source boundaries ───────────────────────────


class TestScrubSourceSwitch:

    def test_scrub_same_source_no_switch(self, hw):
        hw._on_timeline_seek(5000)  # middle of clip 0

        assert hw._pending_seek_ms is None
        assert hw._current_playback_source == PRIMARY
        hw._player.setPosition.assert_called_with(5000)
        hw._player.setSource.assert_not_called()

    def test_scrub_to_external_switches_source(self, hw):
        hw._on_timeline_seek(12000)  # clip 1, source_ms = 2000

        assert hw._current_playback_source == EXTERNAL
        assert hw._pending_seek_ms == 2000
        assert hw._current_clip_index == 1

    def test_scrub_back_to_primary(self, hw):
        hw._current_playback_source = EXTERNAL
        hw._current_clip_index = 1

        hw._on_timeline_seek(20000)  # clip 2, source_ms = 15000

        assert hw._current_playback_source == PRIMARY
        assert hw._pending_seek_ms == 15000
        assert hw._current_clip_index == 2

    def test_scrub_within_loading_source_updates_pending(self, hw):
        """Scrub within same source while still loading → update _pending_seek_ms."""
        hw._on_timeline_seek(12000)  # switch to external, pending = 2000
        assert hw._pending_seek_ms == 2000

        hw._on_timeline_seek(13000)  # still external, source_ms = 3000
        assert hw._pending_seek_ms == 3000
        hw._player.setPosition.assert_not_called()

    def test_slider_seek_within_loading_source_updates_pending(self, hw):
        """Slider seek within same source while loading → update _pending_seek_ms."""
        hw._on_timeline_seek(12000)  # switch to external, pending = 2000
        assert hw._pending_seek_ms == 2000

        hw._on_position_changed_by_user(13000)  # slider to 13 s
        assert hw._pending_seek_ms == 3000  # source_ms = 3000


# ── 2. Play / pause race condition ──────────────────────────────────


class TestPlayPauseRace:

    def test_play_during_loading_flags_auto_play(self, hw):
        hw._pending_seek_ms = 2000
        hw._pending_auto_play = False

        hw._toggle_play_pause()

        assert hw._pending_auto_play is True
        hw._player.play.assert_not_called()

    def test_play_when_not_loading_works(self, hw):
        hw._toggle_play_pause()

        hw._player.play.assert_called_once()

    def test_pause_during_loading_clears_auto_play(self, hw):
        hw._pending_seek_ms = 2000
        hw._pending_auto_play = True
        hw._player.playbackState.return_value = (
            QMediaPlayer.PlaybackState.PlayingState
        )
        hw._player.isPlaying.return_value = True

        hw._toggle_play_pause()

        assert hw._pending_auto_play is False


# ── 3. _on_media_status_changed ──────────────────────────────────────


class TestMediaStatusChanged:

    def test_loaded_clears_pending_and_seeks(self, hw):
        hw._pending_seek_ms = 3000

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)

        assert hw._pending_seek_ms is None
        hw._player.setPosition.assert_called_with(3000)

    def test_loaded_auto_play_calls_play_only(self, hw):
        hw._pending_seek_ms = 3000
        hw._pending_auto_play = True

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)

        hw._player.play.assert_called_once()
        hw._player.pause.assert_not_called()

    def test_loaded_no_auto_play_calls_play(self, hw):
        hw._pending_seek_ms = 3000
        hw._pending_auto_play = False

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)

        hw._player.play.assert_called_once()

    def test_buffered_media_also_handles(self, hw):
        hw._pending_seek_ms = 4000
        hw._pending_auto_play = True

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.BufferedMedia)

        assert hw._pending_seek_ms is None
        hw._player.play.assert_called_once()

    def test_invalid_media_clears_pending(self, hw):
        hw._pending_seek_ms = 5000

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.InvalidMedia)

        assert hw._pending_seek_ms is None
        assert hw._pending_auto_play is False

    def test_no_pending_is_noop(self, hw):
        hw._pending_seek_ms = None

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)

        hw._player.setPosition.assert_not_called()


# ── 4. _on_player_position_changed ───────────────────────────────────


class TestPositionChanged:

    def test_blocked_during_pending_seek(self, hw):
        hw._pending_seek_ms = 5000

        hw._on_player_position_changed(3000)

        hw._timeline.set_playhead.assert_not_called()

    def test_normal_update(self, hw):
        hw._on_player_position_changed(3000)

        # clip 0: timeline_start=0, source_in=0 → timeline_ms = 3000
        hw._timeline.set_playhead.assert_called_with(3000)

    def test_boundary_transition_different_source(self, hw):
        hw._on_player_position_changed(9975)  # >= 10000 - 30

        assert hw._current_clip_index == 1
        assert hw._current_playback_source == EXTERNAL

    def test_boundary_transition_same_source(self, hw):
        """Same-source transition uses setPosition, not setSource."""
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),
            VideoClip(8000, 15000),
        ])
        hw._project.video_clip_track = track
        hw._project.video_path = Path(PRIMARY)
        hw._current_playback_source = PRIMARY
        hw._current_clip_index = 0
        hw._player = _mock_player()
        hw._tts_player = _mock_player()

        hw._on_player_position_changed(4975)

        assert hw._current_clip_index == 1
        hw._player.setPosition.assert_called_with(8000)
        hw._player.setSource.assert_not_called()

    def test_out_of_range_resyncs(self, hw):
        hw._player.position.return_value = 15000

        hw._on_player_position_changed(15000)  # way outside clip 0 range
        # Should not crash — graceful resync


# ── 5. Full scenario: scrub → play ──────────────────────────────────


class TestScrubThenPlay:

    def test_scrub_load_play(self, hw):
        """Scrub to ext → load completes → press play → plays."""
        hw._on_timeline_seek(12000)
        assert hw._pending_seek_ms == 2000

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)
        assert hw._pending_seek_ms is None

        hw._player.reset_mock()
        hw._player.playbackState.return_value = (
            QMediaPlayer.PlaybackState.PausedState
        )
        hw._player.isPlaying.return_value = False

        hw._toggle_play_pause()
        hw._player.play.assert_called_once()

    def test_scrub_play_before_load(self, hw):
        """Scrub to ext → play BEFORE load → auto-play on load."""
        hw._on_timeline_seek(12000)
        assert hw._pending_seek_ms == 2000

        hw._toggle_play_pause()
        assert hw._pending_auto_play is True
        hw._player.play.assert_not_called()

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)
        assert hw._pending_seek_ms is None
        hw._player.setPosition.assert_called_with(2000)
        hw._player.play.assert_called_once()
        hw._player.pause.assert_not_called()

    def test_rapid_scrub_across_sources(self, hw):
        """Rapid cross-source scrub must not leave pending stuck."""
        hw._on_timeline_seek(12000)  # external
        hw._on_timeline_seek(20000)  # back to primary clip 2
        assert hw._pending_seek_ms == 15000

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)
        assert hw._pending_seek_ms is None
        hw._player.setPosition.assert_called_with(15000)

    def test_rapid_scrub_same_source_during_load(self, hw):
        """Scrub within same source while loading → seeks to latest pos."""
        hw._on_timeline_seek(11000)  # external, source_ms = 1000
        hw._on_timeline_seek(13000)  # still external, source_ms = 3000
        hw._on_timeline_seek(14000)  # still external, source_ms = 4000

        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)
        hw._player.setPosition.assert_called_with(4000)


# ── 6. Play button sync ──────────────────────────────────────────


class TestPlayButtonSync:

    def test_play_after_scrub_to_different_source(self, hw):
        """Play after scrubbing to different source → switches source."""
        hw._on_timeline_seek(12000)  # external clip, source_ms = 2000
        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)
        hw._player.reset_mock()

        # Timeline playhead is at 12000, player is at external source
        hw._timeline.get_playhead.return_value = 12000
        hw._player.position.return_value = 2000
        hw._player.playbackState.return_value = QMediaPlayer.PlaybackState.PausedState
        hw._player.isPlaying.return_value = False

        hw._toggle_play_pause()

        # Should play directly (source already matches)
        hw._player.play.assert_called_once()
        hw._player.setSource.assert_not_called()

    def test_play_when_player_source_mismatched(self, hw):
        """Play when timeline and player source don't match → switches."""
        # Timeline at 12000 (external clip), but player still on primary
        hw._timeline.get_playhead.return_value = 12000
        hw._current_playback_source = PRIMARY
        hw._current_clip_index = 0
        hw._player.position.return_value = 5000
        hw._player.playbackState.return_value = QMediaPlayer.PlaybackState.PausedState
        hw._player.isPlaying.return_value = False

        hw._toggle_play_pause()

        # Should switch to external source
        assert hw._pending_seek_ms == 2000  # source_ms for clip 1
        assert hw._pending_auto_play is True
        hw._player.setSource.assert_called_once()

    def test_play_when_position_mismatched(self, hw):
        """Play when source matches but position is off → seeks first."""
        # Timeline at 5000 (clip 0), player at same source but wrong position
        hw._timeline.get_playhead.return_value = 5000
        hw._current_playback_source = PRIMARY
        hw._player.position.return_value = 1000  # off by >100ms
        hw._player.playbackState.return_value = QMediaPlayer.PlaybackState.PausedState
        hw._player.isPlaying.return_value = False

        hw._toggle_play_pause()

        # Should seek to correct position then play
        hw._player.setPosition.assert_called_with(5000)
        hw._player.play.assert_called_once()
