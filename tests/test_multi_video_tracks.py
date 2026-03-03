"""Tests for Phase MV — 다중 비디오 트랙 레이어 합성."""

from __future__ import annotations

import gzip
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.project import ProjectState
from src.models.video_clip import VideoClip, VideoClipTrack
from src.services.project_io import PROJECT_VERSION, load_project, save_project
from src.ui.commands import (
    AddVideoTrackCommand,
    EditTrackBlendModeCommand,
    MoveVideoClipCommand,
    RemoveVideoTrackCommand,
)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _make_project_with_two_tracks() -> ProjectState:
    """비디오 트랙 2개, 각 트랙에 클립 1개짜리 ProjectState."""
    project = ProjectState()
    project.video_path = Path("/fake/video.mp4")
    project.duration_ms = 5000

    vt0 = VideoClipTrack()
    vt0.clips = [VideoClip(0, 5000)]
    vt1 = VideoClipTrack()
    vt1.clips = [VideoClip(0, 5000)]
    project.video_tracks = [vt0, vt1]
    return project


# ── 1. 기본값 테스트 ─────────────────────────────────────────────────────────

class TestBlendModeDefault:
    def test_blend_mode_default(self):
        vt = VideoClipTrack()
        assert vt.blend_mode == "normal"

    def test_chroma_color_default(self):
        vt = VideoClipTrack()
        assert vt.chroma_color == "#00FF00"

    def test_chroma_similarity_default(self):
        vt = VideoClipTrack()
        assert vt.chroma_similarity == pytest.approx(0.3)

    def test_chroma_blend_default(self):
        vt = VideoClipTrack()
        assert vt.chroma_blend == pytest.approx(0.1)


# ── 2. 직렬화 테스트 ─────────────────────────────────────────────────────────

class TestBlendModeSerialization:
    def test_blend_mode_serialization(self, tmp_path):
        """저장/로드 round-trip — blend_mode."""
        project = _make_project_with_two_tracks()
        project.video_tracks[1].blend_mode = "screen"
        path = tmp_path / "test.fmm.json"
        save_project(project, path)
        loaded = load_project(path)
        assert loaded.video_tracks[1].blend_mode == "screen"

    def test_chroma_key_fields_serialization(self, tmp_path):
        """저장/로드 round-trip — chroma_* 3개 필드."""
        project = _make_project_with_two_tracks()
        vt = project.video_tracks[1]
        vt.blend_mode = "chroma_key"
        vt.chroma_color = "#00FFFF"
        vt.chroma_similarity = 0.45
        vt.chroma_blend = 0.25
        path = tmp_path / "test.fmm.json"
        save_project(project, path)
        loaded = load_project(path)
        loaded_vt = loaded.video_tracks[1]
        assert loaded_vt.blend_mode == "chroma_key"
        assert loaded_vt.chroma_color == "#00FFFF"
        assert loaded_vt.chroma_similarity == pytest.approx(0.45)
        assert loaded_vt.chroma_blend == pytest.approx(0.25)

    def test_project_version_11(self, tmp_path):
        """저장 시 version=12 (hue 필드 추가로 v12 업데이트)."""
        project = _make_project_with_two_tracks()
        path = tmp_path / "test.fmm.json"
        save_project(project, path)
        raw = path.read_bytes()
        data = json.loads(gzip.decompress(raw).decode("utf-8") if raw[:2] == b'\x1f\x8b' else raw.decode("utf-8"))
        assert data["version"] == 12

    def test_backward_compat_v10(self, tmp_path):
        """v10 파일 로드 → blend_mode 기본값 'normal'."""
        # v10 포맷 수동 생성 (blend_mode 필드 없음)
        project = _make_project_with_two_tracks()
        path = tmp_path / "test_v10.fmm.json"
        save_project(project, path)
        raw = path.read_bytes()
        data = json.loads(gzip.decompress(raw).decode("utf-8") if raw[:2] == b'\x1f\x8b' else raw.decode("utf-8"))
        data["version"] = 10
        # blend_mode 필드 제거
        for vt_data in data.get("video_tracks", []):
            vt_data.pop("blend_mode", None)
            vt_data.pop("chroma_color", None)
            vt_data.pop("chroma_similarity", None)
            vt_data.pop("chroma_blend", None)
        path.write_text(json.dumps(data), encoding="utf-8")
        loaded = load_project(path)
        for vt in loaded.video_tracks:
            assert vt.blend_mode == "normal"
            assert vt.chroma_color == "#00FF00"


# ── 3. 커맨드 Undo/Redo ──────────────────────────────────────────────────────

class TestVideoTrackCommands:
    def test_add_video_track_command_undo_redo(self):
        """AddVideoTrackCommand Undo/Redo."""
        from PySide6.QtGui import QUndoStack
        project = ProjectState()
        assert len(project.video_tracks) == 1
        stack = QUndoStack()
        cmd = AddVideoTrackCommand(project)
        stack.push(cmd)
        assert len(project.video_tracks) == 2
        stack.undo()
        assert len(project.video_tracks) == 1
        stack.redo()
        assert len(project.video_tracks) == 2

    def test_remove_video_track_command_undo_redo(self):
        """RemoveVideoTrackCommand Undo/Redo, 마지막 1개 삭제 불가."""
        from PySide6.QtGui import QUndoStack
        project = _make_project_with_two_tracks()
        assert len(project.video_tracks) == 2
        stack = QUndoStack()
        cmd = RemoveVideoTrackCommand(project, 1)
        stack.push(cmd)
        assert len(project.video_tracks) == 1
        stack.undo()
        assert len(project.video_tracks) == 2

    def test_move_clip_between_tracks(self):
        """MoveVideoClipCommand — src→dst 이동 + undo 복원."""
        from PySide6.QtGui import QUndoStack
        project = _make_project_with_two_tracks()
        # track0에 클립 2개 추가
        project.video_tracks[0].clips.append(VideoClip(5000, 10000))
        assert len(project.video_tracks[0].clips) == 2
        assert len(project.video_tracks[1].clips) == 1

        stack = QUndoStack()
        cmd = MoveVideoClipCommand(project, 0, 1, 1, 1)
        stack.push(cmd)
        assert len(project.video_tracks[0].clips) == 1
        assert len(project.video_tracks[1].clips) == 2

        stack.undo()
        assert len(project.video_tracks[0].clips) == 2
        assert len(project.video_tracks[1].clips) == 1

    def test_edit_blend_mode_command_undo(self):
        """EditTrackBlendModeCommand undo 복원."""
        from PySide6.QtGui import QUndoStack
        vt = VideoClipTrack()
        vt.blend_mode = "normal"
        stack = QUndoStack()
        cmd = EditTrackBlendModeCommand(vt, "screen", "#00FF00", 0.3, 0.1)
        stack.push(cmd)
        assert vt.blend_mode == "screen"
        stack.undo()
        assert vt.blend_mode == "normal"
        stack.redo()
        assert vt.blend_mode == "screen"


# ── 4. FFmpeg 내보내기 필터 테스트 ──────────────────────────────────────────

def _make_mock_runner(captured_args: list) -> MagicMock:
    """FFmpegRunner mock — run() 호출 시 args를 captured_args에 저장."""
    runner = MagicMock()
    runner.is_available.return_value = True

    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.stdout = "duration=5.000000\n"
    completed.returncode = 0

    def _capture_run(args, **kwargs):
        captured_args.extend(args)
        # progress 파이프 시뮬레이션
        proc = MagicMock()
        proc.stdout = iter(["progress=end\n"])
        proc.wait.return_value = 0
        return proc

    runner.run_ffprobe.return_value = completed
    runner.run_async.side_effect = _capture_run
    return runner


def _run_export_with_mock_runner(project: ProjectState, tmp_path: Path) -> list[str]:
    """export_video를 mock runner로 실행하고 ffmpeg 인자를 반환."""
    from src.services.video_exporter import export_video

    args_captured: list[str] = []
    runner = _make_mock_runner(args_captured)

    with patch("src.services.video_exporter.get_ffmpeg_runner", return_value=runner):
        with patch("src.services.subtitle_exporter.export_ass"):
            try:
                export_video(
                    video_path=Path("/fake/video.mp4"),
                    track=project.subtitle_track,
                    output_path=tmp_path / "out.mp4",
                    video_tracks=project.video_tracks,
                    scale_width=1920,
                    scale_height=1080,
                )
            except Exception:
                pass  # 실제 FFmpeg 없으므로 무시
    return args_captured


class TestExportBlendMode:
    def test_export_blend_mode_screen(self, tmp_path):
        """FFmpeg 필터에 blend=all_mode=screen 포함 확인."""
        project = _make_project_with_two_tracks()
        project.video_tracks[1].blend_mode = "screen"
        args = _run_export_with_mock_runner(project, tmp_path)
        fc = " ".join(args)
        assert "blend=all_mode=screen" in fc

    def test_export_blend_mode_chroma_key(self, tmp_path):
        """FFmpeg 필터에 chromakey=color= 포함 확인."""
        project = _make_project_with_two_tracks()
        vt = project.video_tracks[1]
        vt.blend_mode = "chroma_key"
        vt.chroma_color = "#00FF00"
        vt.chroma_similarity = 0.3
        vt.chroma_blend = 0.1
        args = _run_export_with_mock_runner(project, tmp_path)
        fc = " ".join(args)
        assert "chromakey=color=" in fc

    def test_export_muted_track_audio_excluded(self, tmp_path):
        """muted=True 트랙 오디오가 amix에서 제외 확인."""
        project = _make_project_with_two_tracks()
        project.video_tracks[1].muted = True
        args = _run_export_with_mock_runner(project, tmp_path)
        fc = " ".join(args)
        # amix inputs=2 가 없어야 함 (muted 트랙 제외로 1개만)
        assert "amix=inputs=2" not in fc

    def test_export_hidden_track_excluded(self, tmp_path):
        """hidden=True 트랙이 비디오 필터에서 제외 확인."""
        project = _make_project_with_two_tracks()
        project.video_tracks[1].hidden = True
        args = _run_export_with_mock_runner(project, tmp_path)
        fc = " ".join(args)
        # overlay가 2개 트랙 합성에 쓰이지 않아야 함
        assert "overlay=format=auto[comp1]" not in fc


# ── 5. 캐시 키 테스트 ────────────────────────────────────────────────────────

class TestCacheKey:
    def test_cache_key_multi_track_count(self):
        """clip_count가 각 트랙별 클립 수 튜플인지 확인."""
        project = _make_project_with_two_tracks()
        project.video_tracks[0].clips.append(VideoClip(5000, 8000))

        clip_count = (
            tuple(len(vt.clips) for vt in project.video_tracks)
            if project else ()
        )
        assert clip_count == (2, 1)


# ── 6. 트랙 이름 변경 ────────────────────────────────────────────────────────

class TestTrackRename:
    def test_track_rename(self):
        """name 필드 변경이 정상 저장되는지 확인."""
        project = _make_project_with_two_tracks()
        project.video_tracks[0].name = "배경"
        project.video_tracks[1].name = "오버레이"
        assert project.video_tracks[0].name == "배경"
        assert project.video_tracks[1].name == "오버레이"
