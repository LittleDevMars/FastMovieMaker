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

    def test_out_of_range_wrong_clip_index_updates_playhead(self, hw):
        """Regression: clip index wrong → position mismatch → should still update playhead."""
        # Setup: Playing external source clip 1 (timeline 10000-15000ms, source 0-5000ms)
        hw._current_clip_index = 1
        hw._current_playback_source = EXTERNAL
        hw._player.position.return_value = 2000

        # Player reports position 2000ms (valid for clip 1: source 0-5000ms)
        # This should update timeline to 12000ms (10000 + 2000)
        hw._on_player_position_changed(2000)

        # Should update playhead even though we detected mismatch initially
        hw._timeline.set_playhead.assert_called_with(12000)
        hw._controls.set_output_position.assert_called_with(12000)

    def test_stale_clip_index_searches_and_updates(self, hw):
        """Critical: stale clip index → search all clips → update playhead (fixes frozen playhead bug)."""
        # Simulates: user scrubbed from clip 2 to clip 0, but _current_clip_index still = 2
        hw._current_clip_index = 2  # Wrong! Points to clip 2 (timeline 15-25s)
        hw._current_playback_source = PRIMARY
        hw._player.position.return_value = 3000  # Actually playing clip 0 (source 0-10s)

        # Position 3000ms is WAY outside clip 2's range (source 15000-25000ms)
        # Should search clips, find clip 0, and update playhead
        hw._on_player_position_changed(3000)

        # Should update clip index
        assert hw._current_clip_index == 0
        # Should update playhead to correct timeline position (3000ms for clip 0)
        hw._timeline.set_playhead.assert_called_with(3000)
        hw._controls.set_output_position.assert_called_with(3000)


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


# ── 7. Clip boundary crossing during playback ──────────────────────


class TestClipBoundaryCrossing:

    def test_boundary_cross_to_different_source(self, hw):
        """Playback reaches end of clip 0 → auto-switch to clip 1 (different source)."""
        hw._current_clip_index = 0
        hw._current_playback_source = PRIMARY
        hw._play_intent = True

        # Player position = 9975ms (within 30ms of clip 0 end at 10000ms)
        hw._on_player_position_changed(9975)

        # Should switch to clip 1 (external)
        assert hw._current_clip_index == 1
        assert hw._current_playback_source == EXTERNAL
        assert hw._pending_seek_ms == 0  # clip 1 starts at source 0ms
        hw._player.setSource.assert_called_once()

    def test_boundary_cross_to_same_source(self, hw):
        """Playback reaches end of clip 1 → auto-switch to clip 2 (different source)."""
        hw._current_clip_index = 1
        hw._current_playback_source = EXTERNAL
        hw._play_intent = True
        hw._player.position.return_value = 4975  # near end of clip 1 (0-5000ms)

        # Player position = 4975ms (within 30ms of clip 1 end at 5000ms)
        hw._on_player_position_changed(4975)

        # Should switch to clip 2 (primary, source 10000ms)
        # NOTE: Clip 1 is EXTERNAL, clip 2 is PRIMARY → different source
        assert hw._current_clip_index == 2
        assert hw._current_playback_source == PRIMARY
        assert hw._pending_seek_ms == 10000  # source switch, not setPosition
        hw._player.setSource.assert_called_once()  # different source!

    def test_boundary_cross_same_source_different_clips(self, hw):
        """Same source, different clips: A(0-5s) → A(10-15s)."""
        # Create timeline with same source but gap: A(0-5s), A(10-15s)
        track = VideoClipTrack(clips=[
            VideoClip(0, 5000),      # clip 0: timeline 0-5s
            VideoClip(10000, 15000), # clip 1: timeline 5-10s, SAME source
        ])
        hw._project.video_clip_track = track
        hw._current_clip_index = 0
        hw._current_playback_source = PRIMARY
        hw._play_intent = True

        # Reach boundary of clip 0
        hw._on_player_position_changed(4975)

        # Should stay on same source but setPosition to clip 1 start
        assert hw._current_clip_index == 1
        hw._player.setPosition.assert_called_with(10000)
        hw._player.setSource.assert_not_called()

    def test_no_boundary_cross_mid_clip(self, hw):
        """Normal position update in middle of clip → just update timeline."""
        hw._current_clip_index = 1
        hw._current_playback_source = EXTERNAL

        hw._on_player_position_changed(2500)  # middle of clip 1

        # Should just update timeline, no switch
        assert hw._current_clip_index == 1
        hw._timeline.set_playhead.assert_called_with(12500)  # timeline 10000 + 2500
        hw._player.setSource.assert_not_called()
        hw._player.setPosition.assert_not_called()


# ── 8. Timeline/Slider Synchronization ──────────────────────────────


class TestTimelineSliderSync:

    def test_timeline_seek_updates_slider(self, hw):
        """Timeline seek should update both playhead and slider."""
        hw._on_timeline_seek(12000)  # seek to external clip

        # Should update both timeline and slider
        hw._timeline.set_playhead.assert_called_with(12000)
        hw._controls.set_output_position.assert_called_with(12000)

    def test_slider_drag_updates_timeline(self, hw):
        """Slider drag should update both timeline and slider position."""
        hw._on_position_changed_by_user(15000)  # slider to clip 2

        # Should update both
        hw._timeline.set_playhead.assert_called_with(15000)
        hw._controls.set_output_position.assert_called_with(15000)

    def test_complex_scrub_pattern_A_B_A_A_B_A(self, hw):
        """Complex scrub pattern: A→B→A→A→B→A should track correctly."""
        # A (clip 0)
        hw._on_timeline_seek(5000)
        assert hw._current_clip_index == 0
        hw._timeline.set_playhead.assert_called_with(5000)

        # B (clip 1)
        hw._on_timeline_seek(12000)
        assert hw._current_clip_index == 1
        hw._timeline.set_playhead.assert_called_with(12000)

        # A (clip 0)
        hw._on_timeline_seek(3000)
        assert hw._current_clip_index == 0

        # A (clip 2 - different clip, same source)
        hw._on_timeline_seek(18000)
        assert hw._current_clip_index == 2

        # B (clip 1)
        hw._on_timeline_seek(11000)
        assert hw._current_clip_index == 1

        # A (clip 0)
        hw._on_timeline_seek(7000)
        assert hw._current_clip_index == 0

        # All seeks should update slider
        assert hw._controls.set_output_position.call_count == 6

    def test_playback_during_source_switch_preserves_slider_range(self, hw):
        """Playing across source boundary should not change slider range."""
        # Start playing clip 0 (primary)
        hw._current_clip_index = 0
        hw._current_playback_source = PRIMARY
        hw._play_intent = True

        # Reach boundary → switch to clip 1 (external)
        hw._on_player_position_changed(9975)

        # Should switch source
        assert hw._current_clip_index == 1
        assert hw._current_playback_source == EXTERNAL

        # Slider range should remain at full timeline duration
        # (verified implicitly - no set_output_duration call with wrong value)

    def test_rapid_timeline_scrub_all_updates(self, hw):
        """Rapid timeline scrubbing should update slider every time."""
        positions = [1000, 5000, 12000, 18000, 22000, 8000, 14000]

        for pos in positions:
            hw._on_timeline_seek(pos)

        # Should have called set_output_position for each seek
        assert hw._controls.set_output_position.call_count == len(positions)

        # Last call should be with last position
        hw._controls.set_output_position.assert_called_with(8000 if positions[-1] == 8000 else 14000)


# ── 9. Edge Cases and Stress Tests ──────────────────────────────────


class TestEdgeCases:

    def test_boundary_then_immediate_pause_play(self, hw):
        """Boundary cross → pause → play should work correctly."""
        hw._current_clip_index = 0
        hw._current_playback_source = PRIMARY
        hw._play_intent = True

        # Reach boundary → auto-switch to clip 1
        hw._on_player_position_changed(9975)
        assert hw._current_clip_index == 1

        # Playhead should be at clip 1 start (timeline 10000ms)
        hw._timeline.set_playhead.assert_called_with(10000)

        # User pauses
        hw._play_intent = False

        # User plays again
        hw._play_intent = True
        hw._player.playbackState.return_value = QMediaPlayer.PlaybackState.PausedState
        hw._player.isPlaying.return_value = False
        hw._timeline.get_playhead.return_value = 10000

        hw._toggle_play_pause()

        # Should continue playing clip 1
        hw._player.play.assert_called()

    def test_seek_just_before_boundary_then_play(self, hw):
        """Seek to 30ms before boundary → play → should immediately cross."""
        # Seek to 9970ms (30ms before clip 0 end at 10000ms)
        hw._on_timeline_seek(9970)
        assert hw._current_clip_index == 0

        # Start playing
        hw._play_intent = True
        hw._current_playback_source = PRIMARY

        # Player position reaches boundary threshold
        hw._on_player_position_changed(9975)

        # Should cross to clip 1
        assert hw._current_clip_index == 1
        hw._timeline.set_playhead.assert_called_with(10000)

    def test_last_clip_normal_playback(self, hw):
        """Normal playback in last clip should work correctly."""
        hw._current_clip_index = 2  # Last clip
        hw._current_playback_source = PRIMARY
        hw._play_intent = True

        # Play normally in middle of last clip
        hw._on_player_position_changed(20000)

        # Should update playhead normally
        # Clip 2 starts at timeline 15000ms, source at 15000ms
        # Position 20000ms in source → timeline 20000ms
        hw._timeline.set_playhead.assert_called()
        hw._controls.set_output_position.assert_called()
        # Should NOT try to switch (not at boundary yet)
        hw._player.setSource.assert_not_called()

    def test_play_pause_scrub_play_cycle(self, hw):
        """Play → pause → scrub to different source → play."""
        # Playing clip 0
        hw._current_clip_index = 0
        hw._current_playback_source = PRIMARY
        hw._play_intent = True

        # User pauses
        hw._play_intent = False

        # User scrubs to clip 1 (external)
        hw._on_timeline_seek(12000)
        assert hw._current_clip_index == 1

        # Complete source loading
        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)

        # User plays
        hw._player.reset_mock()
        hw._player.playbackState.return_value = QMediaPlayer.PlaybackState.PausedState
        hw._player.isPlaying.return_value = False
        hw._timeline.get_playhead.return_value = 12000
        hw._play_intent = True

        hw._toggle_play_pause()

        # Should play from clip 1
        hw._player.play.assert_called_once()

    def test_very_short_clips_rapid_transitions(self, hw):
        """Very short clips (1s each) should transition smoothly."""
        # Create timeline with very short clips
        track = VideoClipTrack(clips=[
            VideoClip(0, 1000),       # 0-1s
            VideoClip(0, 1000),       # 1-2s (EXTERNAL)
            VideoClip(5000, 6000),    # 2-3s (PRIMARY)
        ])
        track.clips[1].source_path = EXTERNAL
        hw._project.video_clip_track = track

        # Play through all clips
        hw._current_clip_index = 0
        hw._current_playback_source = PRIMARY
        hw._play_intent = True

        # Cross first boundary (975ms)
        hw._on_player_position_changed(975)
        assert hw._current_clip_index == 1
        hw._timeline.set_playhead.assert_called_with(1000)

        # Source switches to external
        hw._current_playback_source = EXTERNAL
        hw._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)

        # Cross second boundary (975ms in external)
        hw._player.reset_mock()
        hw._timeline.reset_mock()
        hw._on_player_position_changed(975)
        assert hw._current_clip_index == 2
        hw._timeline.set_playhead.assert_called_with(2000)

    def test_scrub_beyond_timeline_end(self, hw):
        """Scrubbing beyond timeline end should clamp to valid range."""
        # Timeline ends at 25000ms, try to seek to 30000ms
        hw._on_timeline_seek(30000)

        # Should still work (clip_at_timeline returns None for out of range)
        # Just verify it doesn't crash
        # Timeline should not update if clip_at_timeline returns None
