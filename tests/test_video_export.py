"""Tests for video export with TTS audio integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.subtitle import SubtitleSegment, SubtitleTrack


# --- video_exporter tests ---

class TestExportVideoCommand:
    """Test FFmpeg command construction in export_video."""

    @patch("src.utils.ffmpeg_utils.find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("src.services.video_exporter.export_srt")
    @patch("src.infrastructure.ffmpeg_runner.subprocess.Popen")
    @patch("src.services.video_exporter._get_video_duration", return_value=10.0)
    def test_export_without_audio_path(self, mock_dur, mock_popen, mock_srt, mock_ffmpeg):
        """Without audio_path, command should use -c:a copy."""
        from src.services.video_exporter import export_video

        process_mock = MagicMock()
        process_mock.stdout = iter([])
        process_mock.stderr = MagicMock()
        process_mock.stderr.read.return_value = ""
        process_mock.returncode = 0
        process_mock.wait.return_value = None
        mock_popen.return_value = process_mock

        track = SubtitleTrack(segments=[SubtitleSegment(0, 1000, "Hello")])
        export_video(Path("/tmp/test.mp4"), track, Path("/tmp/out.mp4"))

        cmd = mock_popen.call_args[0][0]
        assert "-c:a" in cmd
        idx = cmd.index("-c:a")
        assert cmd[idx + 1] == "copy"
        # Should NOT have -map flags
        assert "-map" not in cmd

    @patch("src.utils.ffmpeg_utils.find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("src.services.video_exporter.export_srt")
    @patch("src.infrastructure.ffmpeg_runner.subprocess.Popen")
    @patch("src.services.video_exporter._get_video_duration", return_value=10.0)
    def test_export_with_audio_path(self, mock_dur, mock_popen, mock_srt, mock_ffmpeg, tmp_path):
        """With audio_path, command should map video from input 0 and audio from input 1."""
        from src.services.video_exporter import export_video

        process_mock = MagicMock()
        process_mock.stdout = iter([])
        process_mock.stderr = MagicMock()
        process_mock.stderr.read.return_value = ""
        process_mock.returncode = 0
        process_mock.wait.return_value = None
        mock_popen.return_value = process_mock

        # Create a fake audio file
        audio_file = tmp_path / "tts_audio.mp3"
        audio_file.write_text("fake")

        track = SubtitleTrack(segments=[SubtitleSegment(0, 1000, "Hello")])
        export_video(
            Path("/tmp/test.mp4"), track, Path("/tmp/out.mp4"),
            audio_path=audio_file,
        )

        cmd = mock_popen.call_args[0][0]
        # Should have two -i inputs
        i_indices = [i for i, v in enumerate(cmd) if v == "-i"]
        assert len(i_indices) == 2
        # Second input should be our audio file
        assert cmd[i_indices[1] + 1] == str(audio_file)
        # Should have -map flags
        assert "-map" in cmd
        assert "0:v" in cmd
        assert "1:a" in cmd
        # Audio should be re-encoded to aac
        assert "-c:a" in cmd
        idx = cmd.index("-c:a")
        assert cmd[idx + 1] == "aac"


# --- ExportWorker tests ---

class TestExportWorker:
    """Test ExportWorker parameter passing."""

    def test_worker_stores_audio_path(self):
        from src.workers.export_worker import ExportWorker
        worker = ExportWorker(
            Path("/tmp/test.mp4"),
            SubtitleTrack(),
            Path("/tmp/out.mp4"),
            audio_path=Path("/tmp/audio.mp3"),
        )
        assert worker._audio_path == Path("/tmp/audio.mp3")

    def test_worker_default_no_audio(self):
        from src.workers.export_worker import ExportWorker
        worker = ExportWorker(
            Path("/tmp/test.mp4"),
            SubtitleTrack(),
            Path("/tmp/out.mp4"),
        )
        assert worker._audio_path is None


# --- AudioRegenerator segment volume tests ---

class TestAudioRegeneratorSegmentVolumes:
    """Test AudioRegenerator segment volume support."""

    def test_regenerate_accepts_apply_segment_volumes(self):
        """Verify the parameter signature includes apply_segment_volumes."""
        from src.services.audio_regenerator import AudioRegenerator
        import inspect
        sig = inspect.signature(AudioRegenerator.regenerate_track_audio)
        assert "apply_segment_volumes" in sig.parameters

    def test_create_timeline_audio_accepts_apply_segment_volumes(self):
        """Verify _create_timeline_audio accepts apply_segment_volumes."""
        from src.services.audio_regenerator import AudioRegenerator
        import inspect
        sig = inspect.signature(AudioRegenerator._create_timeline_audio)
        assert "apply_segment_volumes" in sig.parameters

    def test_segment_volume_default_true(self):
        """Verify apply_segment_volumes defaults to True."""
        from src.services.audio_regenerator import AudioRegenerator
        import inspect
        sig = inspect.signature(AudioRegenerator.regenerate_track_audio)
        param = sig.parameters["apply_segment_volumes"]
        assert param.default is True


# --- ExportDialog option detection tests ---

class TestExportDialogOptions:
    """Test ExportDialog TTS detection logic (no Qt required)."""

    def test_has_tts_detection_with_audio(self):
        """Track with audio segments should be detected as having TTS."""
        track = SubtitleTrack(segments=[
            SubtitleSegment(0, 1000, "Hello", audio_file="/tmp/seg1.mp3"),
            SubtitleSegment(1000, 2000, "World"),
        ])
        has_tts = any(seg.audio_file for seg in track.segments)
        assert has_tts is True

    def test_has_tts_detection_without_audio(self):
        """Track without audio segments should not be detected as having TTS."""
        track = SubtitleTrack(segments=[
            SubtitleSegment(0, 1000, "Hello"),
            SubtitleSegment(1000, 2000, "World"),
        ])
        has_tts = any(seg.audio_file for seg in track.segments)
        assert has_tts is False

    def test_segment_volume_values(self):
        """Segments should have volume attribute for export."""
        seg = SubtitleSegment(0, 1000, "Test", volume=1.5)
        assert seg.volume == 1.5

        seg_default = SubtitleSegment(0, 1000, "Test")
        assert seg_default.volume == 1.0


# --- Multi-source concat filter tests ---

class TestMultiSourceConcatFilter:
    """Test _build_concat_filter for multi-source video clips."""

    def test_single_source_no_index_map(self):
        """Without source_index_map, all clips use input 0."""
        from src.services.video_exporter import _build_concat_filter
        from src.models.video_clip import VideoClip

        clips = [VideoClip(0, 5000), VideoClip(8000, 15000)]
        parts, v_label, a_label = _build_concat_filter(clips)

        assert v_label == "[concatv]"
        assert a_label == "[concata]"
        # Input-referencing parts (trim/atrim) should use [0:v] and [0:a]
        input_parts = [p for p in parts if ":v]trim=" in p or ":a]atrim=" in p]
        for part in input_parts:
            assert "[0:v]" in part or "[0:a]" in part

    def test_multi_source_index_map(self):
        """With source_index_map, clips map to correct input indices."""
        from src.services.video_exporter import _build_concat_filter
        from src.models.video_clip import VideoClip

        clips = [
            VideoClip(0, 5000),                          # primary (None)
            VideoClip(0, 3000, source_path="extra.mp4"), # extra
        ]
        source_map = {None: 0, "extra.mp4": 1}
        parts, v_label, a_label = _build_concat_filter(
            clips, source_map, out_w=1920, out_h=1080,
        )

        assert v_label == "[concatv]"
        assert a_label == "[concata]"
        # First clip: input 0
        assert "[0:v]" in parts[0]
        assert "[0:a]" in parts[1]
        # Second clip: input 1
        assert "[1:v]" in parts[2]
        assert "[1:a]" in parts[3]

    def test_multi_source_resolution_normalization(self):
        """Multi-source with out_w/out_h adds scale+pad."""
        from src.services.video_exporter import _build_concat_filter
        from src.models.video_clip import VideoClip

        clips = [
            VideoClip(0, 5000),
            VideoClip(0, 3000, source_path="extra.mp4"),
        ]
        source_map = {None: 0, "extra.mp4": 1}
        parts, _, _ = _build_concat_filter(clips, source_map, 1920, 1080)

        # Each video filter part should have scale and pad for normalization
        video_parts = [p for p in parts if ":v]trim=" in p]
        for vp in video_parts:
            assert "scale=1920:1080" in vp
            assert "pad=1920:1080" in vp

    def test_concat_n_matches_clip_count(self):
        """All N clips are processed in the xfade chain."""
        from src.services.video_exporter import _build_concat_filter
        from src.models.video_clip import VideoClip

        clips = [VideoClip(0, 2000), VideoClip(2000, 4000), VideoClip(4000, 6000)]
        parts, v_label, a_label = _build_concat_filter(clips)

        # Should have 2*N trim/atrim parts (one video + one audio per clip)
        input_parts = [p for p in parts if ":v]trim=" in p or ":a]atrim=" in p]
        assert len(input_parts) == 2 * len(clips)
        # Final output labels
        assert v_label == "[concatv]"
        assert a_label == "[concata]"
        assert "[concatv]" in "".join(parts)
        assert "[concata]" in "".join(parts)
