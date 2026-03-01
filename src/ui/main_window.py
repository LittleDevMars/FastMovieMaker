"""Main application window.

Controller 패턴으로 리팩토링됨.
실제 비즈니스 로직은 src/ui/controllers/ 에 분리되어 있고,
MainWindow는 초기화 + 시그널 배선 + UI 구성만 담당한다.
"""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt, Slot
from PySide6.QtGui import QIcon, QKeySequence, QShortcut, QUndoStack
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
)

from src.models.project import ProjectState
from src.services.autosave import AutoSaveManager
from src.ui.controllers.app_context import AppContext
from src.ui.controllers.clip_controller import ClipController
from src.services.frame_cache_service import FrameCacheService
from src.services.video_frame_player import VideoFramePlayer
from src.ui.controllers.media_controller import MediaController
from src.ui.controllers.overlay_controller import OverlayController
from src.ui.controllers.playback_controller import PlaybackController
from src.ui.controllers.project_controller import ProjectController
from src.ui.controllers.subtitle_controller import SubtitleController
from src.ui.dialogs.preferences_dialog import PreferencesDialog
from src.utils.config import APP_NAME, APP_VERSION, find_ffmpeg
from src.utils.i18n import tr


class MainWindow(QMainWindow):
    # 지원 비디오 형식
    _VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v"}

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1280, 900)
        self.resize(1440, 950)

        # App icon
        icon_path = Path(__file__).resolve().parent.parent.parent / "resources" / "icon.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Enable drag & drop
        self.setAcceptDrops(True)

        # ---- Core state ----
        self._project = ProjectState()
        self._autosave = AutoSaveManager(self)
        self._autosave.set_project(self._project)
        self._undo_stack = QUndoStack(self)

        # ---- Media players ----
        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(1.0)
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._tts_audio_output = QAudioOutput()
        self._tts_audio_output.setVolume(1.0)
        self._tts_player = QMediaPlayer()
        self._tts_player.setAudioOutput(self._tts_audio_output)

        # ---- Timers ----
        self._pending_seek_timer = QTimer(self)
        self._pending_seek_timer.setSingleShot(True)
        self._pending_seek_timer.setInterval(1500)
        self._render_pause_timer = QTimer(self)
        self._render_pause_timer.setSingleShot(True)
        self._render_pause_timer.setInterval(50)

        # ---- Waveform service (MainWindow 소유) ----
        from src.services.timeline_waveform_service import TimelineWaveformService
        self._waveform_service = TimelineWaveformService(self)

        # ---- Frame-based Player Services ----
        self._frame_cache = FrameCacheService()
        self._frame_cache.initialize()
        self._frame_player = VideoFramePlayer(self._frame_cache)

        # ---- Build UI first (controllers need widget refs) ----
        self._build_ui()

        # ---- AppContext 생성 및 모든 참조 연결 ----
        ctx = AppContext()
        ctx.project = self._project
        ctx.undo_stack = self._undo_stack
        ctx.window = self
        ctx.player = self._player
        ctx.audio_output = self._audio_output
        ctx.tts_player = self._tts_player
        ctx.tts_audio_output = self._tts_audio_output
        ctx.video_widget = self._video_widget
        ctx.timeline = self._timeline
        ctx.subtitle_panel = self._subtitle_panel
        ctx.controls = self._controls
        ctx.track_selector = self._track_selector
        ctx.media_panel = self._media_panel
        ctx.templates_panel = self._templates_panel
        ctx.track_header = self._track_headers
        ctx.autosave = self._autosave
        ctx.pending_seek_timer = self._pending_seek_timer
        ctx.render_pause_timer = self._render_pause_timer
        ctx.frame_cache = self._frame_cache
        ctx.frame_player = self._frame_player
        # MainWindow 콜백 등록
        ctx.refresh_all = self._refresh_all_widgets
        ctx.ensure_timeline_duration = self._ensure_timeline_duration
        ctx.refresh_track_selector = self._refresh_track_selector
        self._ctx = ctx

        # ---- Controller 생성 ----
        self._playback = PlaybackController(ctx)
        self._subtitle_ctrl = SubtitleController(ctx)
        self._clip = ClipController(ctx)
        self._overlay = OverlayController(ctx)
        self._project_ctrl = ProjectController(ctx)
        self._media = MediaController(ctx)
        # Controller 간 참조 등록
        ctx.playback_ctrl = self._playback
        ctx.subtitle_ctrl = self._subtitle_ctrl
        ctx.clip_ctrl = self._clip
        ctx.overlay_ctrl = self._overlay
        ctx.project_ctrl = self._project_ctrl
        ctx.media_ctrl = self._media

        # ---- Timer → Controller 연결 ----
        self._pending_seek_timer.timeout.connect(self._playback.on_pending_seek_timeout)
        self._render_pause_timer.timeout.connect(self._playback.on_render_pause)
        self._autosave.save_completed.connect(self._project_ctrl.on_autosave_completed)
        self._undo_stack.indexChanged.connect(lambda _: self._project_ctrl.on_document_edited())

        # ---- Recovery check (UI 필요) ----
        self._project_ctrl.check_recovery()

        # ---- Frame Player Signals ----
        self._frame_player.frame_ready.connect(self._on_frame_player_frame_ready)

        self._build_menu()
        self._setup_shortcuts()
        self._connect_signals()
        self._playback.apply_frame_fps()
        self._restore_geometry()

        # FFmpeg check
        if not find_ffmpeg():
            self.statusBar().showMessage(tr("Warning: FFmpeg not found – subtitle generation won't work"))
        else:
            self.statusBar().showMessage(tr("Ready"))
            
        # Check proxies for media library items
        self._media_panel.check_proxies()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        from src.ui.main_window_ui import build_main_window_ui
        build_main_window_ui(
            self,
            self._player,
            self._audio_output,
            self._tts_audio_output,
            self._waveform_service,
        )

    def _build_menu(self) -> None:
        from src.ui.main_window_menu import build_main_window_menu
        build_main_window_menu(self)

    # ---------------------------------------------------------------- Shortcuts

    def _setup_shortcuts(self) -> None:
        from src.services.settings_manager import SettingsManager
        sm = SettingsManager()

        self._shortcuts: dict[str, QShortcut] = {}

        def _make(action: str, slot) -> QShortcut:
            key = sm.get_shortcut(action)
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(slot)
            self._shortcuts[action] = sc
            return sc

        _make("play_pause", self._playback.toggle_play_pause)
        _make("seek_back", lambda: self._playback.seek_relative(-5000))
        _make("seek_forward", lambda: self._playback.seek_relative(5000))
        _make("seek_back_frame", lambda: self._playback.seek_frame_relative(-1))
        _make("seek_forward_frame", lambda: self._playback.seek_frame_relative(1))
        _make("delete", self._on_delete_pressed)
        _make("copy_clip", self._on_copy)
        _make("paste_clip", self._on_paste)
        _make("split_clip", lambda: self._clip.on_split_clip(-1, self._timeline._playhead_ms))
        _make("zoom_in", self._timeline.zoom_in)
        _make("zoom_out", self._timeline.zoom_out)
        _make("zoom_fit", self._timeline.zoom_fit)
        _make("snap_toggle", self._toggle_magnetic_snap)

        # Ctrl++ 보조 단축키 (커스터마이징 불가)
        sc_zoom_in2 = QShortcut(QKeySequence("Ctrl++"), self)
        sc_zoom_in2.activated.connect(self._timeline.zoom_in)

    def apply_shortcuts(self) -> None:
        """저장된 단축키 설정을 즉시 적용한다 (앱 재시작 불필요)."""
        from src.services.settings_manager import SettingsManager
        sm = SettingsManager()
        for action, sc in self._shortcuts.items():
            key = sm.get_shortcut(action)
            if key:
                sc.setKey(QKeySequence(key))

    def _on_delete_pressed(self) -> None:
        """Handle delete key press: delete selected item from timeline or subtitle panel."""
        item_type, track_idx, item_idx = self._timeline.get_selected_item()
        
        if item_type == "clip":
            self._clip.on_delete_clip(track_idx, item_idx)
        elif item_type == "image":
            self._overlay.on_delete_image_overlay(item_idx)
        elif item_type == "text":
            self._overlay.on_text_overlay_delete_requested(item_idx)
        elif item_type == "bgm":
            self._media.on_bgm_clip_delete_requested(track_idx, item_idx)
        elif item_type == "subtitle":
            self._subtitle_ctrl.on_segment_delete(item_idx)
        else:
            self._subtitle_ctrl.on_delete_selected()

    def _on_copy(self) -> None:
        item_type, _, _ = self._timeline.get_selected_item()
        if item_type == "clip":
            self._clip.copy_selected_clip()
        # Future: handle other types

    def _on_paste(self) -> None:
        # Check clipboard content type
        from PySide6.QtWidgets import QApplication
        mime = QApplication.clipboard().mimeData()
        if mime.hasFormat("application/x-fmm-clip"):
            self._clip.paste_clip()

    # ------------------------------------------------------------ Signal wiring

    def _connect_signals(self) -> None:
        # Player → MediaController / PlaybackController
        self._player.durationChanged.connect(self._media.on_duration_changed)
        self._player.positionChanged.connect(self._playback.on_player_position_changed)
        self._player.mediaStatusChanged.connect(self._media.on_media_status_changed)
        self._player.errorOccurred.connect(self._media.on_player_error)

        # Controls → PlaybackController
        self._controls.play_toggled.connect(self._playback.toggle_play_pause)
        self._controls.stop_requested.connect(self._playback.on_stop_all)
        self._controls.position_changed_by_user.connect(self._timeline.set_playhead)
        self._controls.position_changed_by_user.connect(self._playback.on_position_changed_by_user)
        self._controls.video_volume_changed.connect(self._playback.update_playback_volume)

        # TTS player
        self._tts_player.positionChanged.connect(self._playback.on_tts_position_changed)

        # Seek
        self._timeline.seek_requested.connect(self._playback.on_timeline_seek)
        self._subtitle_panel.seek_requested.connect(self._playback.on_timeline_seek)

        # Subtitle editing → SubtitleController
        self._subtitle_panel.text_edited.connect(self._subtitle_ctrl.on_text_edited)
        self._subtitle_panel.time_edited.connect(self._subtitle_ctrl.on_time_edited)
        self._subtitle_panel.segment_add_requested.connect(self._subtitle_ctrl.on_segment_add)
        self._subtitle_panel.segment_delete_requested.connect(self._subtitle_ctrl.on_segment_delete)
        self._subtitle_panel.style_edit_requested.connect(self._subtitle_ctrl.on_edit_segment_style)
        self._subtitle_panel.volume_edited.connect(self._subtitle_ctrl.on_segment_volume_edited)
        self._subtitle_panel.tts_edit_requested.connect(self._subtitle_ctrl.on_edit_segment_tts)
        self._subtitle_panel.animation_edit_requested.connect(self._subtitle_ctrl.on_edit_segment_animation)
        self._subtitle_panel.font_changed.connect(self._subtitle_ctrl.on_font_changed)

        # Timeline subtitle
        self._timeline.segment_selected.connect(self._subtitle_ctrl.on_timeline_segment_selected)
        self._timeline.segment_moved.connect(self._subtitle_ctrl.on_timeline_segment_moved)
        self._timeline.audio_moved.connect(self._subtitle_ctrl.on_timeline_audio_moved)

        # Image overlay → OverlayController
        self._timeline.insert_image_requested.connect(self._overlay.on_insert_image_overlay)
        self._timeline.insert_text_requested.connect(self._overlay.on_add_text_overlay)
        self._timeline.image_overlay_moved.connect(self._overlay.on_image_overlay_moved)
        self._timeline.image_overlay_selected.connect(self._overlay.on_image_overlay_selected)
        self._timeline.image_overlay_resize.connect(self._overlay.on_image_overlay_resize)

        # Text overlay → OverlayController
        self._timeline.text_overlay_selected.connect(self._overlay.on_text_overlay_selected)
        self._timeline.text_overlay_moved.connect(self._overlay.on_text_overlay_moved)
        self._timeline.text_overlay_edit_requested.connect(self._overlay.on_text_overlay_edit_requested)
        self._timeline.text_overlay_delete_requested.connect(self._overlay.on_text_overlay_delete_requested)

        # Video clip → ClipController
        self._timeline.clip_selected.connect(self._clip.on_clip_selected)
        self._timeline.clip_split_requested.connect(self._clip.on_split_clip)
        self._timeline.clip_deleted.connect(self._clip.on_delete_clip)
        self._timeline.clip_trimmed.connect(self._clip.on_clip_trimmed)
        self._timeline.clip_speed_requested.connect(self._clip.on_edit_clip_speed)
        self._timeline.clip_moved.connect(self._clip.on_clip_moved)
        self._timeline.transition_requested.connect(self._clip.on_transition_requested)
        self._timeline.transition_remove_requested.connect(self._clip.on_remove_transition)
        self._timeline.clip_volume_requested.connect(self._clip.on_edit_clip_properties)
        self._timeline.clip_color_requested.connect(self._clip.on_edit_clip_color)
        self._timeline.clip_color_label_requested.connect(self._clip.on_set_color_label)
        self._timeline.clip_double_clicked.connect(self._clip.on_edit_clip_properties)
        self._track_headers.track_add_requested.connect(self._clip.on_add_video_track)
        self._track_headers.track_remove_requested.connect(self._clip.on_remove_video_track)
        self._track_headers.track_rename_requested.connect(self._clip.on_rename_video_track)
        self._track_headers.subtitle_rename_requested.connect(self._subtitle_ctrl.on_rename_active_track)
        self._timeline.status_message_requested.connect(lambda msg, t=0: self.statusBar().showMessage(msg, t))

        # PIP / text overlay drag → OverlayController
        self._video_widget.pip_position_changed.connect(self._overlay.on_pip_position_changed)
        self._video_widget.text_overlay_position_changed.connect(self._overlay.on_text_overlay_position_changed)

        # Track selector → SubtitleController
        self._track_selector.track_changed.connect(self._subtitle_ctrl.on_track_changed)
        self._track_selector.track_added.connect(self._subtitle_ctrl.on_track_added)
        self._track_selector.track_removed.connect(self._subtitle_ctrl.on_track_removed)
        self._track_selector.track_renamed.connect(self._subtitle_ctrl.on_track_renamed)

        # Media library
        self._media_panel.video_open_requested.connect(
            lambda path: self._media.load_video(Path(path))
        )
        self._media_panel.image_insert_to_timeline.connect(self._overlay.on_media_image_insert_to_timeline)
        self._media_panel.subtitle_imported.connect(self._subtitle_ctrl.on_import_subtitle)
        self._media.proxy_ready.connect(self._media_panel.on_proxy_ready)
        self._media.proxy_started.connect(self._media_panel.on_proxy_started)
        self._media.proxy_progress.connect(self._media_panel.on_proxy_progress)
        self._media.proxy_failed.connect(self._media_panel.on_proxy_failed)
        self._media_panel.proxy_generation_requested.connect(
            self._on_proxy_generation_requested
        )
        self._media_panel.proxy_generation_cancelled.connect(
            self._media.cancel_proxy_generation
        )

        # Timeline drag-and-drop
        self._timeline.image_files_dropped.connect(self._overlay.on_image_file_dropped)
        self._timeline.video_files_dropped.connect(self._clip.on_video_file_dropped)
        self._timeline.audio_files_dropped.connect(self._media.on_audio_file_dropped)
        self._timeline.bgm_clip_selected.connect(self._media.on_bgm_clip_selected)
        self._timeline.bgm_clip_moved.connect(self._media.on_bgm_clip_moved)
        self._timeline.bgm_clip_trimmed.connect(self._media.on_bgm_clip_trimmed)
        self._timeline.bgm_clip_delete_requested.connect(self._media.on_bgm_clip_delete_requested)

        # Templates
        self._templates_panel.template_applied.connect(self._on_template_applied)
        self._templates_panel.template_cleared.connect(self._on_template_cleared)

        # Undo stack → refresh
        self._undo_stack.indexChanged.connect(lambda _: self._refresh_all_widgets())

    # ------------------------------------------------------------ Refresh

    def _refresh_all_widgets(self) -> None:
        """Push current model state to all widgets."""
        track = self._project.subtitle_track
        font_family = self._project.default_style.font_family
        self._video_widget.set_subtitle_track(track if len(track) > 0 else None)
        self._subtitle_panel.set_track(track if len(track) > 0 else None, font_family)
        self._timeline.set_track(track if len(track) > 0 else None)
        self._timeline.set_bgm_tracks(self._project.bgm_tracks)

        io_track = self._project.image_overlay_track
        self._timeline.set_image_overlay_track(io_track if len(io_track) > 0 else None)
        self._video_widget.set_image_overlay_track(io_track if len(io_track) > 0 else None)

        text_track = self._project.text_overlay_track
        self._video_widget.set_text_overlay_track(text_track if len(text_track) > 0 else None)
        self._timeline.set_text_overlay_track(text_track if len(text_track) > 0 else None)

        v_idx = self._ctx.current_track_index
        if 0 <= v_idx < len(self._project.video_tracks):
            clip_track = self._project.video_tracks[v_idx]
            self._timeline.set_clip_track(clip_track)
            self._timeline.set_duration(self._project.duration_ms, has_video=self._project.has_video)
            self._controls.set_output_duration(self._project.duration_ms)

        self._timeline.set_project(self._project)
        self._autosave.notify_edit()

    def _ensure_timeline_duration(self) -> None:
        """Ensure the timeline has a non-zero duration even without a video."""
        if self._project.has_video and self._project.duration_ms > 0:
            return
        needed_ms = 0
        for t in self._project.subtitle_tracks:
            if t.audio_duration_ms > 0:
                needed_ms = max(needed_ms, t.audio_duration_ms)
            if len(t) > 0:
                needed_ms = max(needed_ms, t[-1].end_ms)
        for ov in self._project.image_overlay_track:
            needed_ms = max(needed_ms, ov.end_ms)
        if needed_ms > 0:
            self._project.duration_ms = max(self._project.duration_ms, needed_ms)
            self._timeline.set_duration(self._project.duration_ms)

    def _refresh_track_selector(self) -> None:
        names = [t.name or f"Track {i+1}" for i, t in enumerate(self._project.subtitle_tracks)]
        self._track_selector.set_tracks(names, self._project.active_track_index)

    # ------------------------------------------------------------ Local handlers

    def _on_scene_detect(self) -> None:
        """장면 감지 → 선택된 경계에서 클립 분할."""
        if not self._ctx.project or not self._ctx.project.has_video:
            QMessageBox.warning(self, tr("No Video"), tr("Please open a video file first."))
            return

        from src.ui.dialogs.scene_detect_dialog import SceneDetectDialog
        from src.ui.commands import SplitClipCommand

        video_path = str(self._ctx.project.video_path or "")
        dlg = SceneDetectDialog(self, video_path)
        if not dlg.exec():
            return

        boundaries = dlg.get_selected_boundaries()
        if not boundaries:
            return

        vt = self._ctx.project.video_clip_track
        if not vt or not vt.clips:
            return

        # 뒤에서부터 분할 → 앞쪽 클립 인덱스 불변 보장
        self._undo_stack.beginMacro(tr("Detect Scenes"))
        for ms in sorted(boundaries, reverse=True):
            res = vt.clip_at_timeline(ms)
            if not res:
                continue
            clip_idx, clip = res
            local_ms = ms - vt.clip_timeline_start(clip_idx)
            split_src = clip.source_in_ms + int(local_ms * clip.speed)
            if split_src <= clip.source_in_ms + 100 or split_src >= clip.source_out_ms - 100:
                continue
            first, second = clip.split_at(local_ms)
            self._undo_stack.push(
                SplitClipCommand(self._ctx.project, 0, clip_idx, clip, first, second)
            )
        self._undo_stack.endMacro()
        self._refresh_all_widgets()

    def _on_preferences(self) -> None:
        dialog = PreferencesDialog(self)
        if dialog.exec():
            self.apply_shortcuts()
            self.statusBar().showMessage(tr("Preferences updated"))

    def _toggle_magnetic_snap(self) -> None:
        enabled = self._snap_toggle_btn.isChecked()
        self._timeline.set_magnetic_snap(enabled)

    def _toggle_ripple_mode(self) -> None:
        enabled = self._ripple_toggle_btn.isChecked()
        self._timeline.set_ripple_mode(enabled)

    def _on_proxy_generation_requested(self, path: str) -> None:
        """Handle proxy generation request from media panel."""
        self.statusBar().showMessage(tr("Requesting proxy generation..."), 2000)
        self._media.start_proxy_generation(Path(path))

    def _on_track_state_changed(self) -> None:
        self._timeline._invalidate_static_cache()
        self._timeline.update()
        if self._project.video_clip_track:
            self._audio_output.setMuted(self._project.video_clip_track.muted)
            self._video_widget.set_video_hidden(self._project.video_clip_track.hidden)
        track = self._project.subtitle_track
        if track:
            self._tts_audio_output.setMuted(track.muted)
            pos = self._player.position()
            self._video_widget._update_subtitle(pos)
            self._video_widget._update_image_overlays(pos)
            self._video_widget._update_text_overlays(pos)
        
        # BGM Mute update
        # Note: BGM mute state is checked during playback mixing or regeneration.
        # For real-time preview, we might need to update audio output if we support separate BGM channels.
        # Currently BGM is mixed via AudioMerger for export/regen. 
        # If we have a separate QMediaPlayer for BGM preview, we would mute it here.
        # For now, just updating UI state is enough as BGM preview might not be fully real-time separated yet.
        
        self.statusBar().showMessage(tr("Track states updated"), 2000)

    def _on_template_applied(self, template) -> None:
        self._overlay_template = template
        self._video_widget.set_overlay(template=template)
        self.statusBar().showMessage(f"{tr('Template applied')}: {template.name}")

    def _on_template_cleared(self) -> None:
        self._overlay_template = None
        self._video_widget.clear_overlay()
        self.statusBar().showMessage(tr("Template cleared"))

    def _on_frame_player_frame_ready(self, image) -> None:
        """Handle frame updates from VideoFramePlayer."""
        # VideoPlayerWidget에 set_image 메서드가 있다고 가정하거나
        # QGraphicsPixmapItem을 업데이트하는 로직이 필요합니다.
        if hasattr(self._video_widget, "set_image"):
            self._video_widget.set_image(image)

    def _on_take_screenshot(self) -> None:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = Path(f"/tmp/fastmoviemaker_screenshot_{timestamp}.png")
            pixmap = self.grab()
            pixmap.save(str(screenshot_path))
            self.statusBar().showMessage(
                f"Screenshot saved: {screenshot_path} ({pixmap.width()}x{pixmap.height()})", 5000
            )
        except Exception as e:
            QMessageBox.warning(self, tr("Screenshot Failed"), f"{tr('Failed to capture screenshot')}:\n{e}")

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            f"{tr('About')} {APP_NAME}",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            f"{tr('Video subtitle editor with Whisper-based automatic subtitle generation.')}",
        )

    # ------------------------------------------------------------ Lifecycle

    def _restore_geometry(self) -> None:
        settings = QSettings()
        geo = settings.value("window_geometry")
        if geo:
            self.restoreGeometry(geo)
        state = settings.value("window_state")
        if state:
            self.restoreState(state)

    def closeEvent(self, event) -> None:
        if self._media.is_proxy_generating():
            reply = QMessageBox.question(
                self,
                tr("Warning"),
                tr("Proxy generation is in progress. Quitting will cancel it.\nAre you sure you want to quit?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        settings = QSettings()
        settings.setValue("window_geometry", self.saveGeometry())
        settings.setValue("window_state", self.saveState())
        self._player.stop()
        self._media.cleanup()
        self._frame_cache.cleanup()
        thumb_svc = getattr(self._timeline, "_thumbnail_service", None)
        if thumb_svc:
            if hasattr(thumb_svc, "cancel_all_requests"):
                thumb_svc.cancel_all_requests()
            if hasattr(thumb_svc, "wait_for_done"):
                thumb_svc.wait_for_done(30000)
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(15000)
        self._autosave.save_now()
        super().closeEvent(event)

    # ----------------------------------------------------- Drag & Drop

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(self._is_supported_file(url) for url in urls):
                event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if not urls:
                return
            url = urls[0]
            path = Path(url.toLocalFile())
            if not path.is_file():
                return
            suffix = path.suffix.lower()
            if suffix == ".srt":
                result = QMessageBox.question(
                    self, tr("Import SRT"),
                    tr("Do you want to import this SRT file as a new track?"),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if result == QMessageBox.StandardButton.Yes:
                    self._subtitle_ctrl.on_import_srt_new_track(path)
                else:
                    self._subtitle_ctrl.on_import_srt(path)
            elif suffix == ".fmm.json":
                self._project_ctrl.on_load_project(path)
            elif suffix in self._VIDEO_EXTENSIONS:
                self._media.load_video(path)
            event.acceptProposedAction()

    def _is_supported_file(self, url) -> bool:
        path = Path(url.toLocalFile())
        if not path.is_file():
            return False
        suffix = path.suffix.lower()
        return suffix in self._VIDEO_EXTENSIONS or suffix == ".srt" or suffix == ".fmm.json"
