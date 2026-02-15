"""MediaController — 비디오 로드/프록시/웨이브폼/프레임캐시/BGM 로직."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, QUrl, Qt, Slot
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from src.models.video_clip import VideoClipTrack
from src.services.frame_cache_service import FrameCacheService
from src.utils.config import APP_NAME, find_ffmpeg
from src.utils.i18n import tr
from src.workers.video_load_worker import VideoLoadWorker
from src.workers.waveform_worker import WaveformWorker

if TYPE_CHECKING:
    from src.workers.frame_cache_worker import FrameCacheWorker
    from src.ui.controllers.app_context import AppContext


class MediaController(QObject):
    """비디오 로드, 프록시, 웨이브폼, 프레임캐시, BGM Controller.

    QObject를 상속해야 worker signal → slot 연결에서
    AutoConnection이 QueuedConnection으로 해석되어
    GUI 조작이 메인 스레드에서 실행된다.
    """

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(parent=ctx.window)
        self.ctx = ctx
        # 웨이브폼
        self._waveform_thread: QThread | None = None
        self._waveform_worker: WaveformWorker | None = None
        # 프레임 캐시
        self._frame_cache_thread: QThread | None = None
        self._frame_cache_worker: FrameCacheWorker | None = None
        # 프록시
        self._proxy_threads: list[QThread] = []

    # ---- 비디오 로드 ----

    def on_open_video(self) -> None:
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QFileDialog
        from src.utils.config import VIDEO_FILTER
        ctx = self.ctx
        settings = QSettings()
        last_dir = settings.value("last_video_dir", "")
        path, _ = QFileDialog.getOpenFileName(ctx.window, tr("Open Video"), last_dir, VIDEO_FILTER)
        if not path:
            return
        settings.setValue("last_video_dir", str(Path(path).parent))
        self.load_video(Path(path))

    def load_video(self, path: Path) -> None:
        """비동기 비디오 로딩.

        MediaController는 QObject가 아니므로 signal→slot 연결 시
        QueuedConnection이 메인 스레드로 마샬링되지 않는다.
        따라서 워커 결과를 변수에 저장(DirectConnection, GIL 보호)하고,
        progress.exec() 반환 후 메인 스레드에서 GUI 작업을 수행한다.
        """
        ctx = self.ctx
        self._cleanup_temp_video()
        self._video_thread = QThread()
        self._video_worker = VideoLoadWorker(path)
        self._video_worker.moveToThread(self._video_thread)

        progress = QProgressDialog(f"{tr('Loading')} {path.name}...", tr("Cancel"), 0, 0, ctx.window)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        # 워커 결과를 저장할 변수 (워커 스레드에서 DirectConnection으로 설정)
        _result: list = []   # [(playback_path, has_audio, source_path)]
        _error: list = []    # [error_message]

        def _store_result(playback_path: Path, has_audio: bool, source_path: Path) -> None:
            _result.append((playback_path, has_audio, source_path))

        def _store_error(msg: str) -> None:
            _error.append(msg)

        # progress는 QObject(메인 스레드)이므로 AutoConnection이
        # 자동으로 QueuedConnection으로 처리됨 → setLabelText/accept/reject 안전
        self._video_worker.progress.connect(progress.setLabelText)

        # finished: 결과 저장(DirectConn) → progress 닫기(Queued) → 스레드 정리
        self._video_worker.finished.connect(_store_result)
        self._video_worker.finished.connect(progress.accept)
        self._video_worker.finished.connect(self._video_thread.quit)
        self._video_worker.finished.connect(self._video_worker.deleteLater)
        self._video_worker.finished.connect(self._video_thread.deleteLater)

        # error: 에러 저장(DirectConn) → progress 닫기(Queued) → 스레드 정리
        self._video_worker.error.connect(_store_error)
        self._video_worker.error.connect(progress.reject)
        self._video_worker.error.connect(self._video_thread.quit)
        self._video_worker.error.connect(self._video_worker.deleteLater)
        self._video_worker.error.connect(self._video_thread.deleteLater)

        progress.canceled.connect(self._video_worker.cancel)
        progress.canceled.connect(self._video_thread.quit)
        progress.canceled.connect(self._video_worker.deleteLater)
        progress.canceled.connect(self._video_thread.deleteLater)

        self._video_thread.started.connect(self._video_worker.run)
        self._video_thread.start()
        progress.exec()

        # ---- progress.exec() 반환 후: 메인 스레드에서 안전하게 GUI 조작 ----
        if _result:
            self._on_video_prepared(*_result[0])
        elif _error:
            QMessageBox.critical(ctx.window, tr("Error"), _error[0])

    def _on_video_prepared(self, playback_path: Path, has_audio: bool, source_path: Path) -> None:
        ctx = self.ctx
        existing_tracks = [t for t in ctx.project.subtitle_tracks if len(t) > 0]
        existing_overlays = ctx.project.image_overlay_track
        ctx.project.reset()
        ctx.undo_stack.clear()
        ctx.project.video_path = source_path
        if playback_path != source_path:
            ctx.temp_video_path = playback_path
        if existing_tracks:
            ctx.project.subtitle_tracks = existing_tracks
            ctx.project.active_track_index = 0
        if len(existing_overlays) > 0:
            ctx.project.image_overlay_track = existing_overlays
        ctx.project.video_has_audio = has_audio
        ctx.current_playback_source = str(playback_path)
        ctx.current_clip_index = 0
        ctx.player.setSource(QUrl.fromLocalFile(str(playback_path)))
        ctx.timeline.set_primary_video_path(str(source_path))
        ctx.player.play()
        ctx.refresh_all()
        ctx.refresh_track_selector()
        if ctx.project.video_has_audio:
            self.start_waveform_generation(source_path)
        else:
            ctx.timeline.clear_waveform()
        ctx.window.setWindowTitle(f"{source_path.name} – {APP_NAME}")
        ctx.status_bar().showMessage(f"{tr('Loaded')}: {source_path.name}")
        self.start_frame_cache_generation()
        if ctx.use_proxies:
            self.start_proxy_generation(source_path)

    def _cleanup_temp_video(self) -> None:
        ctx = self.ctx
        if ctx.temp_video_path is not None and ctx.temp_video_path.is_file():
            ctx.temp_video_path.unlink(missing_ok=True)
        ctx.temp_video_path = None

    # ---- 재생 경로 해석 ----

    def resolve_playback_path(self, source_path: str | Path | None) -> str:
        ctx = self.ctx
        if source_path is None:
            if not ctx.project.video_path:
                return ""
            src_str = str(ctx.project.video_path)
        else:
            src_str = str(source_path)

        if ctx.use_proxies:
            proxy = ctx.proxy_map.get(src_str)
            if proxy and Path(proxy).exists():
                return proxy

        if source_path is None:
            if not ctx.project.video_path:
                return ""
            if ctx.temp_video_path and ctx.temp_video_path.exists():
                return str(ctx.temp_video_path)
            return str(ctx.project.video_path)
        if ctx.project.video_path and Path(src_str).resolve() == Path(ctx.project.video_path).resolve():
            if ctx.temp_video_path and ctx.temp_video_path.exists():
                return str(ctx.temp_video_path)
            return str(ctx.project.video_path)
        return src_str

    def switch_player_source(self, source_path: str, seek_ms: int, auto_play: bool = False) -> None:
        ctx = self.ctx
        if ctx.frame_cache_service:
            from PySide6.QtGui import QPixmap
            frame_path = ctx.frame_cache_service.get_nearest_frame(source_path, seek_ms, threshold_ms=2000)
            if frame_path:
                pixmap = QPixmap(str(frame_path))
                if not pixmap.isNull():
                    ctx.video_widget.show_cached_frame(pixmap)
                    ctx.showing_cached_frame = True

        ctx.render_pause_timer.stop()
        ctx.current_playback_source = source_path
        ctx.pending_seek_ms = seek_ms
        ctx.pending_auto_play = ctx.pending_auto_play or auto_play or ctx.play_intent
        ctx.pending_seek_timer.start()
        ctx.player.setSource(QUrl.fromLocalFile(source_path))
        if ctx.pending_auto_play:
            ctx.player.play()

    # ---- 미디어 상태 ----

    def on_media_status_changed(self, status) -> None:
        ctx = self.ctx
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        ready_status = (_QMP.MediaStatus.LoadedMedia, _QMP.MediaStatus.BufferedMedia)
        if status in ready_status and ctx.pending_seek_ms is not None:
            seek_ms = ctx.pending_seek_ms
            auto_play = ctx.pending_auto_play or ctx.play_intent
            ctx.pending_seek_ms = None
            ctx.pending_auto_play = False
            ctx.pending_seek_timer.stop()
            ctx.player.setPosition(seek_ms)
            if auto_play:
                ctx.player.play()
            else:
                ctx.player.play()
                ctx.render_pause_timer.start()
            if ctx.showing_cached_frame:
                ctx.video_widget.hide_cached_frame()
                ctx.showing_cached_frame = False
        elif status == _QMP.MediaStatus.EndOfMedia and ctx.pending_seek_ms is None:
            clip_track = ctx.project.video_clip_track
            if not clip_track:
                return
            idx = ctx.current_clip_index
            if idx + 1 >= len(clip_track.clips):
                return
            next_clip = clip_track.clips[idx + 1]
            ctx.current_clip_index = idx + 1
            next_source = next_clip.source_path or str(ctx.project.video_path)
            if next_source != ctx.current_playback_source:
                self.switch_player_source(next_source, next_clip.source_in_ms, auto_play=ctx.play_intent)
            else:
                ctx.player.setPosition(next_clip.source_in_ms)
                if ctx.play_intent:
                    ctx.player.play()
        elif status == _QMP.MediaStatus.InvalidMedia and ctx.pending_seek_ms is not None:
            ctx.pending_seek_ms = None
            ctx.pending_auto_play = False
            ctx.pending_seek_timer.stop()

    def on_duration_changed(self, duration_ms: int) -> None:
        ctx = self.ctx
        if ctx.pending_seek_ms is not None:
            return
        if ctx.project.video_clip_track is not None:
            return
        ctx.project.duration_ms = duration_ms
        if duration_ms > 0:
            ctx.project.video_clip_track = VideoClipTrack.from_full_video(duration_ms)
            output_dur = ctx.project.video_clip_track.output_duration_ms
            ctx.timeline.set_duration(output_dur, has_video=True)
            ctx.timeline.set_clip_track(ctx.project.video_clip_track)
            ctx.controls.enable_output_time_mode()
            ctx.controls.set_output_duration(output_dur)

    def on_player_error(self, error, error_string: str) -> None:
        ctx = self.ctx
        ctx.pending_seek_ms = None
        ctx.pending_auto_play = False
        ctx.status_bar().showMessage(f"{tr('Player error')}: {error_string}")

    # ---- 프록시 ----

    def toggle_proxies(self, checked: bool) -> None:
        ctx = self.ctx
        ctx.use_proxies = checked
        ctx.status_bar().showMessage(
            tr("Using Proxy Media") if checked else tr("Using Original Media")
        )
        if checked and ctx.project.has_video:
            self.start_proxy_generation(ctx.project.video_path)

    def start_proxy_generation(self, source_path: Path) -> None:
        from src.services.proxy_service import ProxyService
        ctx = self.ctx
        proxy_svc = ProxyService()
        if proxy_svc.has_proxy(str(source_path)):
            ctx.proxy_map[str(source_path)] = proxy_svc.get_proxy_path(str(source_path))
            return
        thread = QThread()
        worker = proxy_svc.create_worker(str(source_path))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda p: self._on_proxy_finished(str(source_path), p))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.deleteLater)
        self._proxy_threads.append(thread)
        thread.start()

    def _on_proxy_finished(self, source_path: str, proxy_path: str) -> None:
        if proxy_path:
            self.ctx.proxy_map[source_path] = proxy_path

    # ---- 웨이브폼 생성 ----

    def start_waveform_generation(self, video_path: Path) -> None:
        ctx = self.ctx
        self.stop_waveform_generation()
        ctx.timeline.clear_waveform()
        self._waveform_thread = QThread()
        self._waveform_worker = WaveformWorker(video_path)
        self._waveform_worker.moveToThread(self._waveform_thread)
        self._waveform_thread.started.connect(self._waveform_worker.run)
        self._waveform_worker.status_update.connect(self._on_worker_status)
        self._waveform_worker.finished.connect(self._on_waveform_finished)
        self._waveform_worker.error.connect(self._on_waveform_error)
        self._waveform_worker.finished.connect(self._cleanup_waveform_thread)
        self._waveform_worker.error.connect(self._cleanup_waveform_thread)
        self._waveform_thread.start()

    def _on_waveform_finished(self, waveform_data) -> None:
        self.ctx.timeline.set_waveform(waveform_data)
        self.ctx.status_bar().showMessage(tr("Waveform loaded"), 3000)

    def _on_waveform_error(self, message: str) -> None:
        print(f"Warning: Waveform generation failed: {message}")
        self.ctx.status_bar().showMessage(tr("Waveform unavailable"), 3000)

    def stop_waveform_generation(self) -> None:
        if self._waveform_worker:
            self._waveform_worker.cancel()
        self._cleanup_waveform_thread()

    def _cleanup_waveform_thread(self) -> None:
        if self._waveform_thread and self._waveform_thread.isRunning():
            self._waveform_thread.quit()
            self._waveform_thread.wait(5000)
        self._waveform_thread = None
        self._waveform_worker = None

    # ---- 프레임 캐시 ----

    def start_frame_cache_generation(self) -> None:
        ctx = self.ctx
        self.stop_frame_cache_generation()
        source_paths: list[str] = []
        durations: dict[str, int] = {}
        if ctx.project.video_path:
            primary = str(ctx.project.video_path)
            source_paths.append(primary)
            durations[primary] = ctx.project.duration_ms
        clip_track = ctx.project.video_clip_track
        if clip_track:
            for sp in clip_track.unique_source_paths():
                if sp not in source_paths:
                    source_paths.append(sp)
                    from src.services.video_probe import probe_video
                    info = probe_video(sp)
                    durations[sp] = info.duration_ms
        if not source_paths:
            return
        if ctx.frame_cache_service is None:
            ctx.frame_cache_service = FrameCacheService()
        ctx.frame_cache_service.initialize()
        uncached = [sp for sp in source_paths if not ctx.frame_cache_service.is_cached(sp)]
        if not uncached:
            return
        from src.workers.frame_cache_worker import FrameCacheWorker
        self._frame_cache_thread = QThread()
        self._frame_cache_worker = FrameCacheWorker(uncached, durations, ctx.frame_cache_service)
        self._frame_cache_worker.moveToThread(self._frame_cache_thread)
        self._frame_cache_thread.started.connect(self._frame_cache_worker.run)
        self._frame_cache_worker.status_update.connect(self._on_worker_status)
        self._frame_cache_worker.finished.connect(self._on_frame_cache_finished)
        self._frame_cache_worker.error.connect(self._on_frame_cache_error)
        self._frame_cache_worker.finished.connect(self._cleanup_frame_cache_thread)
        self._frame_cache_worker.error.connect(self._cleanup_frame_cache_thread)
        self._frame_cache_thread.start()

    def _on_frame_cache_finished(self, cache_service) -> None:
        self.ctx.status_bar().showMessage(tr("Frame cache ready"), 3000)

    def _on_frame_cache_error(self, message: str) -> None:
        print(f"Warning: Frame cache generation failed: {message}")
        self.ctx.status_bar().showMessage(tr("Frame cache unavailable"), 3000)

    def stop_frame_cache_generation(self) -> None:
        if self._frame_cache_worker:
            self._frame_cache_worker.cancel()
        self._cleanup_frame_cache_thread()

    def _cleanup_frame_cache_thread(self) -> None:
        if self._frame_cache_thread and self._frame_cache_thread.isRunning():
            self._frame_cache_thread.quit()
            self._frame_cache_thread.wait(5000)
        self._frame_cache_thread = None
        self._frame_cache_worker = None

    def _on_worker_status(self, msg: str) -> None:
        self.ctx.status_bar().showMessage(msg, 3000)

    # ---- BGM ----

    def on_audio_file_dropped(self, file_path: str, position_ms: int) -> None:
        ctx = self.ctx
        path = Path(file_path)
        if not path.is_file():
            return
        from src.models.audio import AudioClip, AudioTrack
        duration_ms = self._get_audio_duration_ms(path)
        if duration_ms <= 0:
            duration_ms = 5000
        clip = AudioClip(source_path=path, start_ms=position_ms, duration_ms=duration_ms)
        if not ctx.project.bgm_tracks:
            ctx.project.bgm_tracks = [AudioTrack()]
        from src.ui.commands import AddAudioClipCommand
        cmd = AddAudioClipCommand(ctx.project, 0, clip)
        ctx.undo_stack.push(cmd)
        ctx.refresh_all()
        ctx.project_ctrl.on_document_edited()
        ctx.status_bar().showMessage(tr("BGM added: {}").format(path.name))

    def on_bgm_clip_selected(self, track_idx: int, clip_idx: int) -> None:
        pass

    def on_bgm_clip_moved(self, track_idx: int, clip_idx: int, new_start_ms: int) -> None:
        ctx = self.ctx
        if not (0 <= track_idx < len(ctx.project.bgm_tracks)):
            return
        track = ctx.project.bgm_tracks[track_idx]
        if not (0 <= clip_idx < len(track.clips)):
            return
        clip = track.clips[clip_idx]
        old_start = clip.start_ms
        if old_start == new_start_ms:
            return
        from src.ui.commands import MoveAudioClipCommand
        cmd = MoveAudioClipCommand(clip, old_start, new_start_ms)
        ctx.undo_stack.push(cmd)
        ctx.project_ctrl.on_document_edited()
        ctx.refresh_all()

    def on_bgm_clip_trimmed(self, track_idx: int, clip_idx: int, new_start_ms: int, new_dur_ms: int) -> None:
        ctx = self.ctx
        if not (0 <= track_idx < len(ctx.project.bgm_tracks)):
            return
        track = ctx.project.bgm_tracks[track_idx]
        if not (0 <= clip_idx < len(track.clips)):
            return
        clip = track.clips[clip_idx]
        old_start = clip.start_ms
        old_dur = clip.duration_ms
        if old_start == new_start_ms and old_dur == new_dur_ms:
            return
        from src.ui.commands import TrimAudioClipCommand
        cmd = TrimAudioClipCommand(clip, old_start, old_dur, new_start_ms, new_dur_ms)
        ctx.undo_stack.push(cmd)
        ctx.project_ctrl.on_document_edited()
        ctx.refresh_all()

    def on_bgm_clip_delete_requested(self, track_idx: int, clip_idx: int) -> None:
        ctx = self.ctx
        if not (0 <= track_idx < len(ctx.project.bgm_tracks)):
            return
        track = ctx.project.bgm_tracks[track_idx]
        if not (0 <= clip_idx < len(track.clips)):
            return
        from src.ui.commands import DeleteAudioClipCommand
        cmd = DeleteAudioClipCommand(ctx.project, track_idx, clip_idx)
        ctx.undo_stack.push(cmd)
        ctx.project_ctrl.on_document_edited()
        ctx.refresh_all()
        ctx.status_bar().showMessage(tr("BGM clip deleted"))

    def _get_audio_duration_ms(self, path: Path) -> int:
        try:
            ffmpeg_bin = find_ffmpeg()
            if not ffmpeg_bin:
                return 0
            ffprobe_bin = str(Path(ffmpeg_bin).parent / "ffprobe")
            if sys.platform == "win32" and not ffprobe_bin.endswith(".exe"):
                ffprobe_bin += ".exe"
            cmd = [
                ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path)
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
            return int(float(out) * 1000)
        except Exception as e:
            print(f"Error getting audio duration: {e}")
            return 0

    # ---- closeEvent용 정리 ----

    def cleanup(self) -> None:
        """앱 종료 시 리소스 정리."""
        self.stop_waveform_generation()
        self.stop_frame_cache_generation()
        if self.ctx.frame_cache_service:
            self.ctx.frame_cache_service.cleanup()
        self._cleanup_temp_video()
