"""Integration tests for the export process including audio mixing."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.subtitle import SubtitleTrack
from src.workers.export_worker import ExportWorker
from src.workers.batch_export_worker import BatchExportWorker
from src.models.export_preset import BatchExportJob, ExportPreset


class TestExportIntegration:
    """Test integration of export components."""

    @patch("src.workers.export_worker.export_video")
    def test_export_worker_passes_mixing_params(self, mock_export):
        """Verify ExportWorker correctly passes mixing flag and volumes to export_video."""
        # Setup
        video_path = Path("video.mp4")
        audio_path = Path("tts.mp3")
        output_path = Path("output.mp4")
        track = SubtitleTrack()
        
        # Instantiate worker with mixing enabled and custom volumes
        worker = ExportWorker(
            video_path=video_path,
            track=track,
            output_path=output_path,
            audio_path=audio_path,
            mix_with_original_audio=True,
            video_volume=0.5,
            audio_volume=1.2
        )
        
        # Run
        worker.run()
        
        # Verify
        mock_export.assert_called_once()
        call_kwargs = mock_export.call_args[1]
        assert call_kwargs["mix_with_original_audio"] is True
        assert call_kwargs["audio_path"] == audio_path
        assert call_kwargs["video_volume"] == 0.5
        assert call_kwargs["audio_volume"] == 1.2

    @patch("src.services.audio_regenerator.AudioRegenerator.regenerate_track_audio")
    @patch("src.workers.export_worker.export_video")
    def test_full_export_flow_simulation(self, mock_export, mock_regen):
        """Simulate the flow from Dialog preparation to Worker execution."""
        # 1. Simulate Dialog preparation (AudioRegenerator)
        # In the new logic, we don't pass video_audio_path to regenerator if we want mixing in export_video
        mock_regen.return_value = (Path("generated_tts.mp3"), 10000)
        
        # 2. Create Worker with the generated audio and mixing flag
        worker = ExportWorker(
            video_path=Path("video.mp4"),
            track=SubtitleTrack(),
            output_path=Path("out.mp4"),
            audio_path=Path("generated_tts.mp3"),
            mix_with_original_audio=True,
            video_volume=0.8,
            audio_volume=1.0
        )
        
        # 3. Run Worker
        worker.run()
        
        # 4. Verify export_video called with correct params
        mock_export.assert_called_once()
        args = mock_export.call_args[1]
        assert args["mix_with_original_audio"] is True
        assert args["audio_path"] == Path("generated_tts.mp3")
        assert args["video_volume"] == 0.8
        assert args["audio_volume"] == 1.0

    @patch("src.workers.batch_export_worker.export_video")
    def test_batch_export_worker_passes_mixing_params(self, mock_export):
        """Verify BatchExportWorker passes mixing flag and volumes to export_video."""
        # Setup
        job = BatchExportJob(
            preset=ExportPreset("Test", 1920, 1080, "h264", "mp4"),
            output_path="out.mp4"
        )
        
        worker = BatchExportWorker(
            video_path=Path("video.mp4"),
            track=SubtitleTrack(),
            jobs=[job],
            audio_path=Path("tts.mp3"),
            mix_with_original_audio=True,
            video_volume=0.3,
            audio_volume=1.5
        )
        
        worker.run()
        
        mock_export.assert_called_once()
        args = mock_export.call_args[1]
        assert args["mix_with_original_audio"] is True
        assert args["video_volume"] == 0.3
        assert args["audio_volume"] == 1.5