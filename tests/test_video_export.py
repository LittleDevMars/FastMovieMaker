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

    def test_worker_accepts_mix_audio_param(self):
        """Verify ExportWorker accepts mix_with_original_audio parameter."""
        from src.workers.export_worker import ExportWorker
        import inspect
        sig = inspect.signature(ExportWorker.__init__)
        assert "mix_with_original_audio" in sig.parameters


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

    def test_build_concat_filter_speed_atempo(self):
        """Test that speed changes apply atempo filter to audio."""
        from src.services.video_exporter import _build_concat_filter
        from src.models.video_clip import VideoClip

        clip = VideoClip(0, 1000)
        clip.speed = 2.0
        parts, _, _ = _build_concat_filter([clip])
        filter_str = "".join(parts)
        
        # Audio filter should contain atempo
        assert "atempo=2.0" in filter_str

    def test_build_concat_filter_atempo_chaining(self):
        """Test that extreme speeds use chained atempo filters (FFmpeg limit 0.5-2.0)."""
        from src.services.video_exporter import _build_concat_filter
        from src.models.video_clip import VideoClip

        # Speed 4.0 -> atempo=2.0,atempo=2.0
        clip = VideoClip(0, 1000)
        clip.speed = 4.0
        parts, _, _ = _build_concat_filter([clip])
        filter_str = "".join(parts)
        # Check if atempo appears multiple times
        assert filter_str.count("atempo=2.0") >= 2
        
        # Speed 0.25 -> atempo=0.5,atempo=0.5
        clip = VideoClip(0, 1000)
        clip.speed = 0.25
        parts, _, _ = _build_concat_filter([clip])
        filter_str = "".join(parts)
        assert filter_str.count("atempo=0.5") >= 2


class TestExportVideoOptions:
    """Tests for export_video options."""

    def setup_method(self):
        self.process_mock = MagicMock()
        self.process_mock.stdout = iter([])
        self.process_mock.stderr = iter([])
        self.process_mock.returncode = 0
        self.process_mock.wait.return_value = None

    @patch("src.utils.hw_accel.get_hw_encoder")
    @patch("src.utils.ffmpeg_utils.find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("src.services.video_exporter.export_ass")
    @patch("src.infrastructure.ffmpeg_runner.subprocess.Popen")
    @patch("src.services.video_exporter._get_video_duration", return_value=10.0)
    @patch("src.services.video_exporter._get_video_resolution", return_value=(1920, 1080))
    def test_export_with_gpu(self, mock_res, mock_dur, mock_popen, mock_ass, mock_find, mock_get_hw):
        from src.services.video_exporter import export_video
        
        mock_popen.return_value = self.process_mock
        mock_get_hw.return_value = ("h264_nvenc", ["-preset", "p4"])

        track = SubtitleTrack(segments=[SubtitleSegment(0, 1000, "Hello")])
        export_video(
            Path("test.mp4"), track, Path("out.mp4"),
            use_gpu=True, codec="h264"
        )

        cmd = mock_popen.call_args[0][0]
        assert "-c:v" in cmd
        idx = cmd.index("-c:v")
        assert cmd[idx + 1] == "h264_nvenc"

    @patch("src.utils.ffmpeg_utils.find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("src.services.video_exporter.export_ass")
    @patch("src.infrastructure.ffmpeg_runner.subprocess.Popen")
    @patch("src.services.video_exporter._get_video_duration", return_value=10.0)
    @patch("src.services.video_exporter._get_video_resolution", return_value=(1920, 1080))
    def test_export_scaling(self, mock_res, mock_dur, mock_popen, mock_ass, mock_find):
        from src.services.video_exporter import export_video
        
        mock_popen.return_value = self.process_mock

        track = SubtitleTrack(segments=[SubtitleSegment(0, 1000, "Hello")])
        export_video(
            Path("test.mp4"), track, Path("out.mp4"),
            scale_width=1280, scale_height=720
        )

        cmd = mock_popen.call_args[0][0]
        # Should use -vf with scale
        assert "-vf" in cmd
        vf_arg = cmd[cmd.index("-vf") + 1]
        assert "scale=1280:720" in vf_arg

    @patch("src.utils.ffmpeg_utils.find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("src.services.video_exporter.export_ass")
    @patch("src.infrastructure.ffmpeg_runner.subprocess.Popen")
    @patch("src.services.video_exporter._get_video_duration", return_value=10.0)
    @patch("src.services.video_exporter._get_video_resolution", return_value=(1920, 1080))
    def test_export_with_text_overlay(self, mock_res, mock_dur, mock_popen, mock_ass, mock_find):
        from src.services.video_exporter import export_video
        from src.models.text_overlay import TextOverlay
        
        mock_popen.return_value = self.process_mock

        track = SubtitleTrack(segments=[])
        text_overlays = [TextOverlay(0, 1000, "OverlayText")]
        
        export_video(
            Path("test.mp4"), track, Path("out.mp4"),
            text_overlays=text_overlays
        )

        cmd = mock_popen.call_args[0][0]
        # Should use -filter_complex
        assert "-filter_complex" in cmd
        fc_arg = cmd[cmd.index("-filter_complex") + 1]
        assert "drawtext=" in fc_arg
        assert "OverlayText" in fc_arg

    @patch("src.utils.ffmpeg_utils.find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("src.services.video_exporter.export_ass")
    @patch("src.infrastructure.ffmpeg_runner.subprocess.Popen")
    @patch("src.services.video_exporter._get_video_duration", return_value=10.0)
    @patch("src.services.video_exporter._get_video_resolution", return_value=(1920, 1080))
    def test_export_complex_with_audio_replacement(self, mock_res, mock_dur, mock_popen, mock_ass, mock_find, tmp_path):
        """Test that audio_path replaces track audio in filter_complex mode."""
        from src.services.video_exporter import export_video
        from src.models.text_overlay import TextOverlay
        
        mock_popen.return_value = self.process_mock
        
        # Create dummy audio file
        audio_path = tmp_path / "external_audio.mp3"
        audio_path.touch()

        # Trigger filter_complex with text overlay
        text_overlays = [TextOverlay(0, 1000, "Overlay")]
        track = SubtitleTrack(segments=[])
        
        export_video(
            Path("test.mp4"), track, Path("out.mp4"),
            text_overlays=text_overlays,
            audio_path=audio_path
        )

        cmd = mock_popen.call_args[0][0]
        
        # Check inputs: video (0) and audio (1)
        input_indices = [i for i, x in enumerate(cmd) if x == "-i"]
        assert len(input_indices) >= 2
        assert str(audio_path) in cmd
        
        # Check mapping: should map external audio input (1:a)
        map_indices = [i for i, x in enumerate(cmd) if x == "-map"]
        audio_map_found = False
        for idx in map_indices:
            if idx + 1 < len(cmd) and cmd[idx+1] == "1:a":
                audio_map_found = True
                break
        assert audio_map_found, f"Command should map external audio input (1:a). Cmd: {cmd}"

    @patch("src.utils.ffmpeg_utils.find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("src.services.video_exporter.export_ass")
    @patch("src.infrastructure.ffmpeg_runner.subprocess.Popen")
    @patch("src.services.video_exporter._get_video_duration", return_value=10.0)
    @patch("src.services.video_exporter._get_video_resolution", return_value=(1920, 1080))
    def test_export_with_audio_mixing(self, mock_res, mock_dur, mock_popen, mock_ass, mock_find, tmp_path):
        """Test that mix_with_original_audio=True uses amix filter."""
        from src.services.video_exporter import export_video
        
        mock_popen.return_value = self.process_mock
        
        audio_path = tmp_path / "external.mp3"
        audio_path.touch()
        track = SubtitleTrack(segments=[])
        
        export_video(
            Path("test.mp4"), track, Path("out.mp4"),
            audio_path=audio_path,
            mix_with_original_audio=True,
            video_volume=0.5,
            audio_volume=1.2
        )

        cmd = mock_popen.call_args[0][0]
        assert "-filter_complex" in cmd
        fc_arg = cmd[cmd.index("-filter_complex") + 1]
        # Should contain amix
        assert "amix=inputs=2" in fc_arg
        # Should contain volume filters
        assert "volume=0.50" in fc_arg
        assert "volume=1.20" in fc_arg
        # Should use normalize=0 to respect volumes
        assert "normalize=0" in fc_arg

    @patch("src.utils.ffmpeg_utils.find_ffmpeg", return_value="/usr/bin/ffmpeg")
    @patch("src.services.video_exporter.export_ass")
    @patch("src.infrastructure.ffmpeg_runner.subprocess.Popen")
    @patch("src.services.video_exporter._get_video_duration", return_value=10.0)
    @patch("src.services.video_exporter._get_video_resolution", return_value=(1920, 1080))
    def test_export_multi_track_layering(self, mock_res, mock_dur, mock_popen, mock_ass, mock_find):
        """Test that multiple video tracks are layered correctly using overlay filter."""
        from src.services.video_exporter import export_video
        from src.models.video_clip import VideoClip, VideoClipTrack
        
        mock_popen.return_value = self.process_mock
        
        # Track 0 (Bottom layer)
        track0 = VideoClipTrack(clips=[VideoClip(0, 1000)])
        # Track 1 (Top layer)
        track1 = VideoClipTrack(clips=[VideoClip(0, 1000)])
        
        export_video(
            Path("base.mp4"), SubtitleTrack(), Path("out.mp4"),
            video_tracks=[track0, track1]
        )
        
        cmd = mock_popen.call_args[0][0]
        assert "-filter_complex" in cmd
        fc = cmd[cmd.index("-filter_complex") + 1]
        
        # Check that track 0 is overlaid by track 1
        # Implementation uses labels [t0v] and [t1v]
        # Expected pattern: [t0v][t1v]overlay=format=auto
        assert "[t0v][t1v]overlay=format=auto" in fc
