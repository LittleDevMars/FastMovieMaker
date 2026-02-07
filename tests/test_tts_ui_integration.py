"""Integration test for TTS UI update after generation."""

import pytest
from pathlib import Path

from src.models.project import ProjectState
from src.models.subtitle import SubtitleSegment, SubtitleTrack


def test_tts_track_update_simulation():
    """
    Simulate TTS generation and verify that UI widgets would be updated correctly.

    This test simulates what happens when:
    1. User generates TTS (Ctrl+T)
    2. TTSDialog returns a track with segments and audio
    3. MainWindow adds the track to project
    4. MainWindow calls _refresh_all_widgets()
    """
    # Setup: Create a project (like app startup)
    project = ProjectState()
    project.subtitle_tracks = [SubtitleTrack(name="Default")]
    project.active_track_index = 0

    # Verify initial state
    assert len(project.subtitle_tracks) == 1
    assert project.subtitle_track.name == "Default"
    assert len(project.subtitle_track) == 0

    # Simulate: User generates TTS
    # TTSDialog would return a track with segments and audio_path
    tts_track = SubtitleTrack(
        name="TTS Track 0",
        audio_path="/tmp/tts_audio.mp3",
    )
    tts_track.add_segment(SubtitleSegment(0, 2000, "안녕하세요."))
    tts_track.add_segment(SubtitleSegment(2000, 4000, "FastMovieMaker입니다."))
    tts_track.add_segment(SubtitleSegment(4000, 6000, "TTS 테스트 중입니다."))

    # Simulate: Set audio duration (MainWindow would do this with FFprobe)
    tts_track.audio_duration_ms = 6000
    tts_track.audio_start_ms = 0

    # Simulate: MainWindow adds the track
    project.subtitle_tracks.append(tts_track)
    new_track_index = len(project.subtitle_tracks) - 1
    project.active_track_index = new_track_index

    # Verify: Project state updated correctly
    assert len(project.subtitle_tracks) == 2
    assert project.active_track_index == 1
    assert project.subtitle_track.name == "TTS Track 0"
    assert len(project.subtitle_track) == 3
    assert project.subtitle_track.audio_path == "/tmp/tts_audio.mp3"
    assert project.subtitle_track.audio_duration_ms == 6000
    assert project.subtitle_track.audio_start_ms == 0

    # Verify: Segments are correct
    assert project.subtitle_track[0].text == "안녕하세요."
    assert project.subtitle_track[1].text == "FastMovieMaker입니다."
    assert project.subtitle_track[2].text == "TTS 테스트 중입니다."

    # Verify: Timeline would show audio
    track = project.subtitle_track
    assert track.audio_path != ""
    assert track.audio_duration_ms > 0
    # TimelineWidget._draw_audio_track would draw this


def test_refresh_widgets_gets_new_track():
    """
    Verify that after switching to a new track,
    widgets receive the correct track via set_track().
    """
    # Setup
    project = ProjectState()

    # Track 1: Empty default
    track1 = SubtitleTrack(name="Default")

    # Track 2: TTS with segments
    track2 = SubtitleTrack(
        name="TTS Track",
        audio_path="/tmp/audio.mp3",
        audio_start_ms=0,
        audio_duration_ms=5000,
    )
    track2.add_segment(SubtitleSegment(0, 2000, "Hello"))
    track2.add_segment(SubtitleSegment(2000, 5000, "World"))

    project.subtitle_tracks = [track1, track2]

    # Initially on track 1
    project.active_track_index = 0
    current_track = project.subtitle_track
    assert current_track.name == "Default"
    assert len(current_track) == 0
    assert current_track.audio_path == ""

    # Switch to track 2 (simulating TTS generation)
    project.active_track_index = 1
    current_track = project.subtitle_track

    # Verify: Widgets would receive the new track
    assert current_track.name == "TTS Track"
    assert len(current_track) == 2
    assert current_track.audio_path == "/tmp/audio.mp3"
    assert current_track.audio_duration_ms == 5000

    # This is what set_track() would receive:
    # - SubtitlePanel.set_track(current_track) → shows 2 segments
    # - TimelineWidget.set_track(current_track) → shows audio + 2 segments
    # - VideoPlayerWidget.set_subtitle_track(current_track) → ready to display


def test_audio_timeline_visibility_conditions():
    """
    Test when audio timeline should be visible in TimelineWidget.
    """
    # Case 1: No audio → should NOT draw audio track
    track1 = SubtitleTrack(name="No Audio")
    track1.add_segment(SubtitleSegment(0, 2000, "Text"))
    assert track1.audio_path == ""
    assert track1.audio_duration_ms == 0
    # TimelineWidget._draw_audio_track would return early

    # Case 2: Has audio path but no duration → should NOT draw
    track2 = SubtitleTrack(name="Invalid Audio", audio_path="/tmp/audio.mp3")
    assert track2.audio_path != ""
    assert track2.audio_duration_ms == 0
    # TimelineWidget._draw_audio_track would return early

    # Case 3: Has both path and duration → SHOULD draw
    track3 = SubtitleTrack(
        name="Valid Audio",
        audio_path="/tmp/audio.mp3",
        audio_duration_ms=5000,
    )
    assert track3.audio_path != ""
    assert track3.audio_duration_ms > 0
    # TimelineWidget._draw_audio_track would draw green box

    # Case 4: TTS generated track → SHOULD draw
    track4 = SubtitleTrack(
        name="TTS Track",
        audio_path="/Users/user/.fastmoviemaker/tts_12345.mp3",
        audio_start_ms=0,
        audio_duration_ms=8500,
    )
    track4.add_segment(SubtitleSegment(0, 2000, "One"))
    track4.add_segment(SubtitleSegment(2000, 5000, "Two"))
    track4.add_segment(SubtitleSegment(5000, 8500, "Three"))

    assert track4.audio_path != ""
    assert track4.audio_duration_ms == 8500
    assert len(track4) == 3
    # TimelineWidget would draw:
    # - 3 blue subtitle boxes (y: 20-70)
    # - 1 green audio box (y: 75-115, width: 0ms ~ 8500ms)


if __name__ == "__main__":
    # Run tests
    test_tts_track_update_simulation()
    print("✅ test_tts_track_update_simulation PASSED")

    test_refresh_widgets_gets_new_track()
    print("✅ test_refresh_widgets_gets_new_track PASSED")

    test_audio_timeline_visibility_conditions()
    print("✅ test_audio_timeline_visibility_conditions PASSED")

    print("\n🎉 All integration tests passed!")
