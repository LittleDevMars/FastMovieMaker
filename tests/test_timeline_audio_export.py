
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.models.video_clip import VideoClip, VideoClipTrack
from src.services.timeline_audio_exporter import export_timeline_audio, _build_audio_concat_filter

def test_build_audio_concat_filter_single_clip():
    clip = VideoClip(source_path=Path("test.mp4"), source_in_ms=0, source_out_ms=1000)
    filters = _build_audio_concat_filter([clip])
    assert len(filters) == 2
    assert "[0:a]atrim=start=0.000:end=1.000,asetpts=PTS-STARTPTS[a0]" in filters[0]
    assert "[a0]acopy[outa]" in filters[1]

def test_build_audio_concat_filter_multi_clip():
    clip1 = VideoClip(source_path=Path("v1.mp4"), source_in_ms=0, source_out_ms=1000)
    clip2 = VideoClip(source_path=Path("v1.mp4"), source_in_ms=2000, source_out_ms=3000)
    # Multi-clip from same source
    filters = _build_audio_concat_filter([clip1, clip2])
    assert "concat=n=2:v=0:a=1[outa]" in filters[-1]

def test_build_audio_concat_filter_speed_volume():
    clip = VideoClip(source_path=Path("test.mp4"), source_in_ms=0, source_out_ms=1000)
    clip.speed = 2.0
    clip.volume = 0.5
    filters = _build_audio_concat_filter([clip])
    # [0:a]atrim...,atempo=2.000,volume=0.500[a0]
    assert "atempo=2.000" in filters[0]
    assert "volume=0.500" in filters[0]

@patch("src.services.timeline_audio_exporter.find_ffmpeg")
@patch("subprocess.run")
def test_export_timeline_audio_calls_ffmpeg(mock_run, mock_find):
    mock_find.return_value = "ffmpeg"
    mock_run.return_value = MagicMock(returncode=0)
    
    track = VideoClipTrack()
    track.clips.append(VideoClip(source_path=Path("test.mp4"), source_in_ms=0, source_out_ms=1000))
    
    out_path = Path("output.wav")
    export_timeline_audio(track, output_path=out_path)
    
    assert mock_run.called
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "-filter_complex" in args
    assert "[outa]" in args
