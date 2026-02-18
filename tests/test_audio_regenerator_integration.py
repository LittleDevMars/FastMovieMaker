"""Integration tests for AudioRegenerator with segment settings."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.audio_regenerator import AudioRegenerator


class TestAudioRegeneratorIntegration:
    """Test AudioRegenerator integration with segment settings."""

    @pytest.fixture
    def mock_ffmpeg_runner(self):
        """Mock FFmpeg runner and create dummy output files so copy2(tts_audio, output_path) succeeds."""
        def run_side_effect(args, check=False):
            # Create any .mp3 output file that FFmpeg would have created (last path in args)
            for a in args:
                if isinstance(a, str) and a.endswith(".mp3"):
                    p = Path(a)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(b"\x00\x00")  # minimal dummy
            return MagicMock(returncode=0)

        with patch("src.services.audio_regenerator.get_ffmpeg_runner") as mock_get:
            runner = MagicMock()
            runner.is_available.return_value = True
            runner.run.side_effect = run_side_effect
            mock_get.return_value = runner
            yield runner

    def test_regenerate_track_audio_applies_segment_volume(self, mock_ffmpeg_runner, tmp_path):
        """Test that regenerate_track_audio applies per-segment volume settings."""
        # Setup track with segments having different volumes
        track = SubtitleTrack()
        
        # Create dummy audio files
        audio1 = tmp_path / "seg1.mp3"
        audio1.write_text("dummy audio content 1")
        
        audio2 = tmp_path / "seg2.mp3"
        audio2.write_text("dummy audio content 2")
        
        # Segment 1: Volume 1.5 (should trigger volume filter)
        seg1 = SubtitleSegment(0, 1000, "Segment 1", audio_file=str(audio1), volume=1.5)
        track.add_segment(seg1)
        
        # Segment 2: Volume 1.0 (should NOT trigger volume filter)
        seg2 = SubtitleSegment(1000, 2000, "Segment 2", audio_file=str(audio2), volume=1.0)
        track.add_segment(seg2)
        
        output_path = tmp_path / "output.mp3"
        
        # Run regeneration
        AudioRegenerator.regenerate_track_audio(
            track=track,
            output_path=output_path,
            apply_segment_volumes=True
        )
        
        # Verify FFmpeg calls
        # We expect calls to create silence, apply volume, and concat
        
        # Check for volume filter call for segment 1
        volume_filter_called = False
        for call in mock_ffmpeg_runner.run.call_args_list:
            args = call[0][0]
            # Check if this call is applying volume filter
            if "-af" in args and "volume=1.50" in args[args.index("-af") + 1]:
                volume_filter_called = True
                # Verify input file is correct
                assert str(audio1) in args
                
        assert volume_filter_called, "FFmpeg volume filter was not called for segment with volume 1.5"
        
        # Check that NO volume filter was called for segment 2 (volume 1.0)
        volume_1_0_called = False
        for call in mock_ffmpeg_runner.run.call_args_list:
            args = call[0][0]
            if "-af" in args and "volume=1.00" in args[args.index("-af") + 1]:
                volume_1_0_called = True
                
        assert not volume_1_0_called, "FFmpeg volume filter should not be called for volume 1.0"