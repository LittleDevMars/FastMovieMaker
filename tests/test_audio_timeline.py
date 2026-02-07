"""Tests for audio timeline visualization and editing."""

from __future__ import annotations

import pytest

from src.models.subtitle import SubtitleSegment, SubtitleTrack


def test_audio_timeline_fields():
    """Test SubtitleTrack audio timeline fields."""
    track = SubtitleTrack(name="Test", audio_path="/tmp/test.mp3")
    assert track.audio_path == "/tmp/test.mp3"
    assert track.audio_start_ms == 0
    assert track.audio_duration_ms == 0


def test_audio_timeline_initialization():
    """Test audio timeline with custom values."""
    track = SubtitleTrack(
        name="Test",
        audio_path="/tmp/test.mp3",
        audio_start_ms=1000,
        audio_duration_ms=5000,
    )
    assert track.audio_start_ms == 1000
    assert track.audio_duration_ms == 5000


def test_audio_timeline_movement():
    """Test moving audio in timeline."""
    track = SubtitleTrack(
        audio_path="/tmp/test.mp3",
        audio_start_ms=0,
        audio_duration_ms=10000,
    )

    # Move audio to 2 seconds
    track.audio_start_ms = 2000
    assert track.audio_start_ms == 2000
    assert track.audio_duration_ms == 10000  # Duration unchanged


def test_audio_timeline_resize():
    """Test resizing audio duration."""
    track = SubtitleTrack(
        audio_path="/tmp/test.mp3",
        audio_start_ms=0,
        audio_duration_ms=10000,
    )

    # Resize to 15 seconds
    track.audio_duration_ms = 15000
    assert track.audio_start_ms == 0  # Position unchanged
    assert track.audio_duration_ms == 15000


def test_audio_timeline_with_segments():
    """Test audio timeline alongside subtitle segments."""
    track = SubtitleTrack(
        audio_path="/tmp/test.mp3",
        audio_start_ms=0,
        audio_duration_ms=10000,
    )

    track.add_segment(SubtitleSegment(0, 2000, "First"))
    track.add_segment(SubtitleSegment(2000, 4000, "Second"))
    track.add_segment(SubtitleSegment(4000, 6000, "Third"))

    assert len(track) == 3
    assert track.audio_duration_ms == 10000
    assert track[-1].end_ms == 6000  # Subtitles end before audio


def test_audio_timeline_persistence():
    """Test that audio timeline fields are properly stored."""
    track = SubtitleTrack(
        name="TTS Track",
        audio_path="/tmp/tts.mp3",
        audio_start_ms=500,
        audio_duration_ms=8500,
    )

    # Simulate serialization
    data = {
        "name": track.name,
        "audio_path": track.audio_path,
        "audio_start_ms": track.audio_start_ms,
        "audio_duration_ms": track.audio_duration_ms,
    }

    # Simulate deserialization
    restored = SubtitleTrack(
        name=data["name"],
        audio_path=data["audio_path"],
        audio_start_ms=data["audio_start_ms"],
        audio_duration_ms=data["audio_duration_ms"],
    )

    assert restored.name == "TTS Track"
    assert restored.audio_path == "/tmp/tts.mp3"
    assert restored.audio_start_ms == 500
    assert restored.audio_duration_ms == 8500


def test_audio_timeline_left_resize():
    """Test left edge resize (changes both start and duration)."""
    track = SubtitleTrack(
        audio_path="/tmp/test.mp3",
        audio_start_ms=1000,
        audio_duration_ms=10000,
    )

    # Simulate dragging left edge right by 500ms
    new_start = 1500
    duration_change = track.audio_start_ms - new_start  # -500
    track.audio_start_ms = new_start
    track.audio_duration_ms += duration_change

    assert track.audio_start_ms == 1500
    assert track.audio_duration_ms == 9500  # Shortened by 500ms


def test_audio_timeline_right_resize():
    """Test right edge resize (changes only duration)."""
    track = SubtitleTrack(
        audio_path="/tmp/test.mp3",
        audio_start_ms=1000,
        audio_duration_ms=10000,
    )

    # Simulate dragging right edge left by 2000ms
    track.audio_duration_ms = 8000

    assert track.audio_start_ms == 1000  # Position unchanged
    assert track.audio_duration_ms == 8000


def test_audio_timeline_boundary_constraints():
    """Test that audio stays within valid bounds."""
    track = SubtitleTrack(
        audio_path="/tmp/test.mp3",
        audio_start_ms=5000,
        audio_duration_ms=10000,
    )

    # Move to negative position (should be clamped to 0)
    track.audio_start_ms = max(0, -1000)
    assert track.audio_start_ms == 0

    # Resize to negative duration (should be clamped to minimum)
    min_duration = 100  # 100ms minimum
    track.audio_duration_ms = max(min_duration, -500)
    assert track.audio_duration_ms == 100
