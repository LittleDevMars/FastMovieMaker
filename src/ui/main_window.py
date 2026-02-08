"""Main application window."""

import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QUrl, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut, QUndoStack
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.models.image_overlay import ImageOverlay, ImageOverlayTrack
from src.models.project import ProjectState
from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.audio_merger import AudioMerger
from src.services.autosave import AutoSaveManager
from src.services.subtitle_exporter import export_srt, import_srt
from src.services.translator import TranslatorService
from src.ui.dialogs.preferences_dialog import PreferencesDialog
from src.ui.dialogs.recovery_dialog import RecoveryDialog
from src.ui.dialogs.translate_dialog import TranslateDialog
from src.ui.commands import (
    AddSegmentCommand,
    BatchShiftCommand,
    DeleteSegmentCommand,
    EditStyleCommand,
    EditTextCommand,
    EditTimeCommand,
    EditVolumeCommand,
    MergeCommand,
    MoveSegmentCommand,
    SplitCommand,
)
from src.ui.media_library_panel import MediaLibraryPanel
from src.ui.templates_panel import TemplatesPanel
from src.ui.playback_controls import PlaybackControls
from src.ui.subtitle_panel import SubtitlePanel
from src.ui.timeline_widget import TimelineWidget
from src.ui.track_selector import TrackSelector
from src.ui.video_player_widget import VideoPlayerWidget
from src.ui.dialogs.whisper_dialog import WhisperDialog
from src.ui.dialogs.tts_dialog import TTSDialog
from src.utils.config import APP_NAME, APP_VERSION, VIDEO_FILTER, find_ffmpeg
from src.workers.waveform_worker import WaveformWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1280, 900)  # Increased to ensure timeline is always visible
        self.resize(1440, 950)

        # App icon
        icon_path = Path(__file__).resolve().parent.parent.parent / "resources" / "icon.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Enable drag & drop
        self.setAcceptDrops(True)

        self._project = ProjectState()
        self._temp_video_path: Path | None = None  # for converted MKV etc.
        self._current_project_path: Path | None = None

        # Autosave manager
        self._autosave = AutoSaveManager(self)
        self._autosave.set_project(self._project)
        self._autosave.save_completed.connect(self._on_autosave_completed)

        # Check for crash recovery
        self._check_recovery()

        # Undo stack
        self._undo_stack = QUndoStack(self)
        # Connect to autosave for edit notification
        self._undo_stack.indexChanged.connect(self._on_document_edited)

        # Media stack
        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(1.0)  # Ensure volume is at maximum
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)

        # TTS audio player (separate from video player)
        self._tts_audio_output = QAudioOutput()
        self._tts_audio_output.setVolume(1.0)
        self._tts_player = QMediaPlayer()
        self._tts_player.setAudioOutput(self._tts_audio_output)

        # Waveform worker
        self._waveform_thread: QThread | None = None
        self._waveform_worker: WaveformWorker | None = None

        self._build_ui()
        self._build_menu()
        self._setup_shortcuts()
        self._connect_signals()
        self._restore_geometry()

        # FFmpeg check
        if not find_ffmpeg():
            self.statusBar().showMessage("Warning: FFmpeg not found – subtitle generation won't work")
        else:
            self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        # Video player
        self._video_widget = VideoPlayerWidget(self._player)

        # Track selector + subtitle panel (right side)
        self._track_selector = TrackSelector()
        self._subtitle_panel = SubtitlePanel()

        # Subtitles tab
        subtitle_tab = QWidget()
        subtitle_layout = QVBoxLayout(subtitle_tab)
        subtitle_layout.setContentsMargins(0, 0, 0, 0)
        subtitle_layout.setSpacing(0)
        subtitle_layout.addWidget(self._track_selector)
        subtitle_layout.addWidget(self._subtitle_panel, 1)

        # Media library tab
        self._media_panel = MediaLibraryPanel()

        # Templates tab
        self._templates_panel = TemplatesPanel()

        # Overlay state
        self._overlay_template = None  # OverlayTemplate | None

        # Right tabs
        self._right_tabs = QTabWidget()
        self._right_tabs.addTab(subtitle_tab, "Subtitles")
        self._right_tabs.addTab(self._media_panel, "Media")
        self._right_tabs.addTab(self._templates_panel, "Templates")

        # Top splitter: video | right tabs
        self._top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._top_splitter.addWidget(self._video_widget)
        self._top_splitter.addWidget(self._right_tabs)
        self._top_splitter.setStretchFactor(0, 3)
        self._top_splitter.setStretchFactor(1, 1)
        self._top_splitter.setSizes([1050, 390])

        # Playback controls
        self._controls = PlaybackControls(self._player, self._audio_output)
        self._controls.set_tts_audio_output(self._tts_audio_output)

        # Timeline
        self._timeline = TimelineWidget()

        # Timeline zoom toolbar
        self._zoom_toolbar = QWidget()
        self._zoom_toolbar.setFixedHeight(28)
        self._zoom_toolbar.setStyleSheet("background-color: rgb(40, 40, 40); border-top: 1px solid rgb(60, 60, 60);")
        zoom_layout = QHBoxLayout(self._zoom_toolbar)
        zoom_layout.setContentsMargins(6, 2, 6, 2)
        zoom_layout.setSpacing(4)

        btn_style = "QPushButton { background: rgb(60,60,60); color: white; border: 1px solid rgb(80,80,80); border-radius: 3px; padding: 1px 8px; font-size: 12px; } QPushButton:hover { background: rgb(80,80,80); }"

        self._zoom_fit_btn = QPushButton("Fit")
        self._zoom_fit_btn.setFixedWidth(36)
        self._zoom_fit_btn.setStyleSheet(btn_style)
        self._zoom_fit_btn.setToolTip("Fit entire timeline (Ctrl+0)")
        self._zoom_fit_btn.clicked.connect(self._timeline.zoom_fit)

        self._zoom_out_btn = QPushButton("-")
        self._zoom_out_btn.setFixedWidth(28)
        self._zoom_out_btn.setStyleSheet(btn_style)
        self._zoom_out_btn.setToolTip("Zoom out (Ctrl+-)")
        self._zoom_out_btn.clicked.connect(self._timeline.zoom_out)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(50)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setStyleSheet("color: rgb(180,180,180); font-size: 11px; border: none;")

        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setFixedWidth(28)
        self._zoom_in_btn.setStyleSheet(btn_style)
        self._zoom_in_btn.setToolTip("Zoom in (Ctrl++)")
        self._zoom_in_btn.clicked.connect(self._timeline.zoom_in)

        zoom_layout.addWidget(self._zoom_fit_btn)
        zoom_layout.addWidget(self._zoom_out_btn)
        zoom_layout.addWidget(self._zoom_label)
        zoom_layout.addWidget(self._zoom_in_btn)
        zoom_layout.addStretch()

        self._timeline.zoom_changed.connect(lambda pct: self._zoom_label.setText(f"{pct}%"))

        # Main layout
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._top_splitter, 1)
        main_layout.addWidget(self._controls)
        main_layout.addWidget(self._zoom_toolbar)
        main_layout.addWidget(self._timeline)

        # Status bar
        self.setStatusBar(QStatusBar())

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open Video...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._on_open_video)
        file_menu.addAction(open_action)

        import_srt_action = QAction("&Import SRT...", self)
        import_srt_action.setShortcut(QKeySequence("Ctrl+I"))
        import_srt_action.triggered.connect(self._on_import_srt)
        file_menu.addAction(import_srt_action)

        import_srt_track_action = QAction("Import SRT to &New Track...", self)
        import_srt_track_action.triggered.connect(self._on_import_srt_new_track)
        file_menu.addAction(import_srt_track_action)

        file_menu.addSeparator()

        export_action = QAction("&Export SRT...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export_srt)
        file_menu.addAction(export_action)

        export_video_action = QAction("Export &Video...", self)
        export_video_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        export_video_action.triggered.connect(self._on_export_video)
        file_menu.addAction(export_video_action)

        batch_export_action = QAction("&Batch Export...", self)
        batch_export_action.triggered.connect(self._on_batch_export)
        file_menu.addAction(batch_export_action)

        file_menu.addSeparator()

        save_action = QAction("&Save Project...", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._on_save_project)
        file_menu.addAction(save_action)

        load_action = QAction("&Load Project...", self)
        load_action.setShortcut(QKeySequence("Ctrl+L"))
        load_action.triggered.connect(self._on_load_project)
        file_menu.addAction(load_action)

        # Recent files submenu
        self._recent_menu = QMenu("Recent &Projects", self)
        file_menu.addMenu(self._recent_menu)
        self._update_recent_menu()

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        undo_action = self._undo_stack.createUndoAction(self, "&Undo")
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        edit_menu.addAction(undo_action)

        redo_action = self._undo_stack.createRedoAction(self, "&Redo")
        redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        split_action = QAction("S&plit Subtitle", self)
        split_action.triggered.connect(self._on_split_subtitle)
        edit_menu.addAction(split_action)

        merge_action = QAction("&Merge Subtitles", self)
        merge_action.triggered.connect(self._on_merge_subtitles)
        edit_menu.addAction(merge_action)

        edit_menu.addSeparator()

        batch_shift_action = QAction("&Batch Shift Timing...", self)
        batch_shift_action.triggered.connect(self._on_batch_shift)
        edit_menu.addAction(batch_shift_action)

        edit_menu.addSeparator()

        preferences_action = QAction("&Preferences...", self)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self._on_preferences)
        edit_menu.addAction(preferences_action)

        # Subtitles menu
        sub_menu = menubar.addMenu("&Subtitles")

        gen_action = QAction("&Generate (Whisper)...", self)
        gen_action.setShortcut(QKeySequence("Ctrl+G"))
        gen_action.triggered.connect(self._on_generate_subtitles)
        sub_menu.addAction(gen_action)

        tts_action = QAction("Generate &Speech (TTS)...", self)
        tts_action.setShortcut(QKeySequence("Ctrl+T"))
        tts_action.triggered.connect(self._on_generate_tts)
        sub_menu.addAction(tts_action)

        play_tts_action = QAction("&Play TTS Audio", self)
        play_tts_action.setShortcut(QKeySequence("Ctrl+P"))
        play_tts_action.triggered.connect(self._on_play_tts_audio)
        sub_menu.addAction(play_tts_action)

        regen_audio_action = QAction("&Regenerate Audio from Timeline", self)
        regen_audio_action.setShortcut(QKeySequence("Ctrl+R"))
        regen_audio_action.triggered.connect(self._on_regenerate_audio)
        sub_menu.addAction(regen_audio_action)

        clear_action = QAction("&Clear Subtitles", self)
        clear_action.triggered.connect(self._on_clear_subtitles)
        sub_menu.addAction(clear_action)

        sub_menu.addSeparator()

        translate_action = QAction("&Translate Track...", self)
        translate_action.triggered.connect(self._on_translate_track)
        sub_menu.addAction(translate_action)

        sub_menu.addSeparator()

        style_action = QAction("Default &Style...", self)
        style_action.triggered.connect(self._on_edit_default_style)
        sub_menu.addAction(style_action)

        sub_menu.addSeparator()

        edit_position_action = QAction("Edit Subtitle &Position", self)
        edit_position_action.setCheckable(True)
        edit_position_action.setShortcut(QKeySequence("Ctrl+E"))
        edit_position_action.triggered.connect(self._on_toggle_position_edit)
        sub_menu.addAction(edit_position_action)
        self._edit_position_action = edit_position_action  # Store reference

        # Help menu
        help_menu = menubar.addMenu("&Help")

        screenshot_action = QAction("Take &Screenshot", self)
        screenshot_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        screenshot_action.triggered.connect(self._on_take_screenshot)
        help_menu.addAction(screenshot_action)

        help_menu.addSeparator()

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_shortcuts(self) -> None:
        """Bind keyboard shortcuts not already covered by menu actions."""
        # Space → play/pause toggle
        sc_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        sc_space.activated.connect(self._toggle_play_pause)

        # Left/Right → seek ±5 seconds
        sc_left = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        sc_left.activated.connect(lambda: self._seek_relative(-5000))
        sc_right = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        sc_right.activated.connect(lambda: self._seek_relative(5000))

        # Shift+Left/Right → seek ±1 frame
        sc_frame_left = QShortcut(QKeySequence("Shift+Left"), self)
        sc_frame_left.activated.connect(lambda: self._seek_frame_relative(-1))
        sc_frame_right = QShortcut(QKeySequence("Shift+Right"), self)
        sc_frame_right.activated.connect(lambda: self._seek_frame_relative(1))

        # Delete → delete selected subtitle
        sc_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        sc_del.activated.connect(self._on_delete_selected_subtitle)

        # Ctrl+Plus → Zoom in timeline
        sc_zoom_in = QShortcut(QKeySequence("Ctrl+="), self)
        sc_zoom_in.activated.connect(self._timeline.zoom_in)
        sc_zoom_in2 = QShortcut(QKeySequence("Ctrl++"), self)
        sc_zoom_in2.activated.connect(self._timeline.zoom_in)

        # Ctrl+Minus → Zoom out timeline
        sc_zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        sc_zoom_out.activated.connect(self._timeline.zoom_out)

        # Ctrl+0 → Zoom fit timeline
        sc_zoom_fit = QShortcut(QKeySequence("Ctrl+0"), self)
        sc_zoom_fit.activated.connect(self._timeline.zoom_fit)

    def _toggle_play_pause(self) -> None:
        # Check if we're currently playing
        is_playing = (
            self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState or
            self._tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )

        if is_playing:
            # Pause both players
            self._player.pause()
            self._tts_player.pause()
        else:
            # Play
            if self._project.has_video:
                # Video exists - play video and sync TTS
                self._player.play()
                self._sync_tts_playback()
            else:
                # No video - play TTS only
                track = self._project.subtitle_track
                if track and track.audio_path and track.audio_duration_ms > 0:
                    audio_path = Path(track.audio_path)
                    if audio_path.exists():
                        if self._tts_player.source() != QUrl.fromLocalFile(str(audio_path)):
                            self._tts_player.setSource(QUrl.fromLocalFile(str(audio_path)))
                        self._tts_player.play()

    def _sync_tts_playback(self) -> None:
        """Synchronize TTS audio playback with video position."""
        try:
            track = self._project.subtitle_track

            # Check if track has TTS audio
            if not track or not track.audio_path or track.audio_duration_ms <= 0:
                return

            # Check if audio file exists
            audio_path = Path(track.audio_path)
            if not audio_path.exists():
                return

            # Get current playback position
            current_pos_ms = self._player.position()
            audio_start_ms = track.audio_start_ms
            audio_end_ms = audio_start_ms + track.audio_duration_ms

            # Check if current position is within TTS audio range
            if audio_start_ms <= current_pos_ms < audio_end_ms:
                # Calculate TTS audio position (offset from audio start)
                tts_pos_ms = current_pos_ms - audio_start_ms

                # Load audio if not already loaded or different source
                current_source = self._tts_player.source()
                new_source = QUrl.fromLocalFile(str(audio_path))

                # Compare source URLs (handle empty source case)
                if not current_source.isValid() or current_source != new_source:
                    self._tts_player.setSource(new_source)

                # Set position and play
                self._tts_player.setPosition(tts_pos_ms)

                # Only call play() if not already playing
                if self._tts_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                    self._tts_player.play()
            else:
                # Outside TTS audio range, stop TTS playback
                if self._tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    self._tts_player.pause()

        except Exception as e:
            # Silently handle TTS sync errors to avoid disrupting playback
            print(f"Warning: TTS sync error: {e}")

    def _seek_relative(self, delta_ms: int) -> None:
        pos = max(0, self._player.position() + delta_ms)
        self._player.setPosition(pos)
        self._sync_tts_playback()

    def _seek_frame_relative(self, frame_delta: int) -> None:
        """Seek by a relative number of frames.

        Args:
            frame_delta: Number of frames to move (+/- integer)
        """
        if self._player.duration() <= 0:
            return

        from src.services.settings_manager import SettingsManager
        from src.utils.time_utils import frame_to_ms

        settings = SettingsManager()
        fps = settings.get_frame_seek_fps()
        ms_delta = frame_to_ms(frame_delta, fps)

        self._seek_relative(ms_delta)
        self._sync_tts_playback()

    def _on_delete_selected_subtitle(self) -> None:
        # Check if an image overlay is selected in timeline
        sel_img = self._timeline._selected_overlay_index
        if sel_img >= 0:
            self._on_delete_image_overlay(sel_img)
            self._timeline.select_image_overlay(-1)
            return

        rows = self._subtitle_panel._table.selectionModel().selectedRows()
        if rows and self._project.has_subtitles:
            index = rows[0].row()
            self._on_segment_delete(index)

    def _connect_signals(self) -> None:
        # Player signals
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._on_player_position_changed)
        self._player.errorOccurred.connect(self._on_player_error)
        self._controls.position_changed_by_user.connect(self._timeline.set_playhead)
        self._controls.position_changed_by_user.connect(self._on_position_changed_by_user)

        # TTS player signals for playhead when no video
        self._tts_player.positionChanged.connect(self._on_tts_position_changed)

        # Seek signals
        self._timeline.seek_requested.connect(self._on_timeline_seek)
        self._subtitle_panel.seek_requested.connect(self._on_timeline_seek)

        # Subtitle editing signals (SubtitlePanel)
        self._subtitle_panel.text_edited.connect(self._on_text_edited)
        self._subtitle_panel.time_edited.connect(self._on_time_edited)
        self._subtitle_panel.segment_add_requested.connect(self._on_segment_add)
        self._subtitle_panel.segment_delete_requested.connect(self._on_segment_delete)
        self._subtitle_panel.style_edit_requested.connect(self._on_edit_segment_style)
        self._subtitle_panel.volume_edited.connect(self._on_segment_volume_edited)

        # Timeline editing signals
        self._timeline.segment_selected.connect(self._on_timeline_segment_selected)
        self._timeline.segment_moved.connect(self._on_timeline_segment_moved)
        self._timeline.audio_moved.connect(self._on_timeline_audio_moved)

        # Image overlay signals
        self._timeline.insert_image_requested.connect(self._on_insert_image_overlay)
        self._timeline.image_overlay_moved.connect(self._on_image_overlay_moved)
        self._timeline.image_overlay_selected.connect(self._on_image_overlay_selected)

        # PIP drag on video player
        self._video_widget.pip_position_changed.connect(self._on_pip_position_changed)

        # Track selector signals
        self._track_selector.track_changed.connect(self._on_track_changed)
        self._track_selector.track_added.connect(self._on_track_added)
        self._track_selector.track_removed.connect(self._on_track_removed)
        self._track_selector.track_renamed.connect(self._on_track_renamed)

        # Media library signals
        self._media_panel.video_open_requested.connect(
            lambda path: self._load_video(Path(path))
        )
        self._media_panel.image_insert_to_timeline.connect(
            self._on_media_image_insert_to_timeline
        )

        # Template signals
        self._templates_panel.template_applied.connect(self._on_template_applied)
        self._templates_panel.template_cleared.connect(self._on_template_cleared)

        # Undo stack
        self._undo_stack.indexChanged.connect(lambda _: self._refresh_all_widgets())

    # ------------------------------------------------------------ Refresh

    def _refresh_all_widgets(self) -> None:
        """Push current model state to all widgets."""
        track = self._project.subtitle_track
        self._video_widget.set_subtitle_track(track if len(track) > 0 else None)
        self._subtitle_panel.set_track(track if len(track) > 0 else None)
        self._timeline.set_track(track if len(track) > 0 else None)
        # Sync image overlay track
        io_track = self._project.image_overlay_track
        self._timeline.set_image_overlay_track(io_track if len(io_track) > 0 else None)
        self._video_widget.set_image_overlay_track(io_track if len(io_track) > 0 else None)
        # Notify autosave of edits
        self._autosave.notify_edit()

    def _refresh_track_selector(self) -> None:
        """Sync track selector with project state."""
        names = [t.name or f"Track {i+1}" for i, t in enumerate(self._project.subtitle_tracks)]
        self._track_selector.set_tracks(names, self._project.active_track_index)

    # ---------------------------------------------------- Edit handlers (with Undo)

    def _on_text_edited(self, index: int, new_text: str) -> None:
        track = self._project.subtitle_track
        if 0 <= index < len(track):
            old_text = track[index].text
            cmd = EditTextCommand(track, index, old_text, new_text)
            self._undo_stack.push(cmd)
            self.statusBar().showMessage(f"Text updated (segment {index + 1})")

    def _on_time_edited(self, index: int, start_ms: int, end_ms: int) -> None:
        track = self._project.subtitle_track
        if 0 <= index < len(track):
            seg = track[index]
            cmd = EditTimeCommand(track, index, seg.start_ms, seg.end_ms, start_ms, end_ms)
            self._undo_stack.push(cmd)
            self.statusBar().showMessage(f"Time updated (segment {index + 1})")

    def _on_segment_volume_edited(self, index: int, volume: float) -> None:
        track = self._project.subtitle_track
        if 0 <= index < len(track):
            old_volume = track[index].volume
            cmd = EditVolumeCommand(track, index, old_volume, volume)
            self._undo_stack.push(cmd)
            self.statusBar().showMessage(f"Volume updated: {int(volume * 100)}% (segment {index + 1})")

    def _on_segment_add(self, start_ms: int, end_ms: int) -> None:
        seg = SubtitleSegment(start_ms, end_ms, "New subtitle")
        cmd = AddSegmentCommand(self._project.subtitle_track, seg)
        self._undo_stack.push(cmd)
        self.statusBar().showMessage("Subtitle added")

    def _on_segment_delete(self, index: int) -> None:
        track = self._project.subtitle_track
        if 0 <= index < len(track):
            seg = track[index]
            cmd = DeleteSegmentCommand(track, index, seg)
            self._undo_stack.push(cmd)
            self.statusBar().showMessage("Subtitle deleted")

    def _on_timeline_segment_selected(self, index: int) -> None:
        if self._project.has_subtitles and 0 <= index < len(self._project.subtitle_track):
            self._subtitle_panel._table.selectRow(index)

    def _on_timeline_segment_moved(self, index: int, new_start: int, new_end: int) -> None:
        track = self._project.subtitle_track
        if 0 <= index < len(track):
            seg = track[index]
            cmd = MoveSegmentCommand(track, index, seg.start_ms, seg.end_ms, new_start, new_end)
            self._undo_stack.push(cmd)

            # Force video player to refresh subtitle display
            self._video_widget.set_subtitle_track(track)

            # Refresh subtitle panel
            self._subtitle_panel.set_track(track)

            self.statusBar().showMessage(f"Segment {index + 1} moved")

    def _on_timeline_audio_moved(self, new_start_ms: int, new_duration_ms: int) -> None:
        """Handle audio track moved/resized in timeline."""
        track = self._project.subtitle_track
        if track and track.audio_path:
            # Update audio position (no undo/redo for now, direct update)
            track.audio_start_ms = new_start_ms
            track.audio_duration_ms = new_duration_ms
            self.statusBar().showMessage(
                f"Audio track adjusted: {new_start_ms}ms ~ {new_start_ms + new_duration_ms}ms"
            )

    # --------------------------------------------- Image Overlay handlers

    def _on_insert_image_overlay(self, position_ms: int) -> None:
        """Handle timeline request to insert an image overlay at position."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image for Overlay", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not path:
            return

        duration = 5000  # 5 seconds default
        end_ms = position_ms + duration
        if self._project.duration_ms > 0:
            end_ms = min(end_ms, self._project.duration_ms)

        overlay = ImageOverlay(
            start_ms=position_ms,
            end_ms=end_ms,
            image_path=str(Path(path).resolve()),
        )
        self._project.image_overlay_track.add_overlay(overlay)

        io_track = self._project.image_overlay_track
        self._timeline.set_image_overlay_track(io_track)
        self._video_widget.set_image_overlay_track(io_track)
        self._autosave.notify_edit()
        self.statusBar().showMessage(f"Image overlay inserted: {Path(path).name}")

    def _on_image_overlay_moved(self, index: int, new_start: int, new_end: int) -> None:
        """Handle image overlay drag/resize in timeline."""
        io_track = self._project.image_overlay_track
        if 0 <= index < len(io_track):
            ov = io_track[index]
            ov.start_ms = new_start
            ov.end_ms = new_end
            self._timeline.update()
            self._autosave.notify_edit()
            self.statusBar().showMessage(f"Image overlay {index + 1} moved")

    def _on_image_overlay_selected(self, index: int) -> None:
        """Handle image overlay selection in timeline."""
        self._video_widget.select_pip(index)
        self.statusBar().showMessage(f"Image overlay {index + 1} selected")

    def _on_media_image_insert_to_timeline(self, file_path: str) -> None:
        """Insert an image from the media library onto the timeline at the playhead."""
        position_ms = self._player.position()
        duration = 5000
        end_ms = position_ms + duration
        if self._project.duration_ms > 0:
            end_ms = min(end_ms, self._project.duration_ms)

        overlay = ImageOverlay(
            start_ms=position_ms,
            end_ms=end_ms,
            image_path=str(Path(file_path).resolve()),
        )
        self._project.image_overlay_track.add_overlay(overlay)

        io_track = self._project.image_overlay_track
        self._timeline.set_image_overlay_track(io_track)
        self._video_widget.set_image_overlay_track(io_track)
        self._autosave.notify_edit()
        self.statusBar().showMessage(f"Image overlay inserted from library: {Path(file_path).name}")

    def _on_delete_image_overlay(self, index: int) -> None:
        """Delete an image overlay by index."""
        io_track = self._project.image_overlay_track
        if 0 <= index < len(io_track):
            io_track.remove_overlay(index)
            self._timeline.set_image_overlay_track(io_track if len(io_track) > 0 else None)
            self._video_widget.set_image_overlay_track(io_track if len(io_track) > 0 else None)
            self._autosave.notify_edit()
            self.statusBar().showMessage("Image overlay deleted")

    def _on_pip_position_changed(self, index: int, x_pct: float, y_pct: float, scale_pct: float) -> None:
        """Handle PIP image dragged/scaled on video player."""
        io_track = self._project.image_overlay_track
        if 0 <= index < len(io_track):
            ov = io_track[index]
            ov.x_percent = round(x_pct, 2)
            ov.y_percent = round(y_pct, 2)
            ov.scale_percent = round(scale_pct, 2)
            self._autosave.notify_edit()

    # --------------------------------------------- Split / Merge / Batch Shift

    def _on_split_subtitle(self) -> None:
        if not self._project.has_subtitles:
            QMessageBox.warning(self, "No Subtitles", "No subtitles to split.")
            return

        rows = self._subtitle_panel._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "No Selection", "Select a subtitle to split.")
            return

        index = rows[0].row()
        track = self._project.subtitle_track
        if index < 0 or index >= len(track):
            return

        seg = track[index]
        split_ms = self._player.position()

        if split_ms <= seg.start_ms or split_ms >= seg.end_ms:
            QMessageBox.warning(
                self, "Invalid Position",
                "Move the playhead inside the selected subtitle to split it."
            )
            return

        # Split text at midpoint of words
        words = seg.text.split()
        mid = max(1, len(words) // 2)
        text1 = " ".join(words[:mid])
        text2 = " ".join(words[mid:])
        if not text1:
            text1 = seg.text
        if not text2:
            text2 = seg.text

        first = SubtitleSegment(seg.start_ms, split_ms, text1, style=seg.style)
        second = SubtitleSegment(split_ms, seg.end_ms, text2, style=seg.style)

        cmd = SplitCommand(track, index, split_ms, seg, first, second)
        self._undo_stack.push(cmd)
        self.statusBar().showMessage(f"Segment {index + 1} split at {split_ms}ms")

    def _on_merge_subtitles(self) -> None:
        if not self._project.has_subtitles:
            QMessageBox.warning(self, "No Subtitles", "No subtitles to merge.")
            return

        rows = self._subtitle_panel._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "No Selection", "Select a subtitle to merge with the next one.")
            return

        index = rows[0].row()
        track = self._project.subtitle_track
        if index < 0 or index + 1 >= len(track):
            QMessageBox.warning(self, "Cannot Merge", "Select a subtitle that has a following subtitle.")
            return

        first = track[index]
        second = track[index + 1]
        merged_text = first.text + " " + second.text
        merged = SubtitleSegment(first.start_ms, second.end_ms, merged_text, style=first.style)

        cmd = MergeCommand(track, index, first, second, merged)
        self._undo_stack.push(cmd)
        self.statusBar().showMessage(f"Segments {index + 1}-{index + 2} merged")

    def _on_batch_shift(self) -> None:
        if not self._project.has_subtitles:
            QMessageBox.warning(self, "No Subtitles", "No subtitles to shift.")
            return

        offset, ok = QInputDialog.getInt(
            self, "Batch Shift", "Offset (ms, negative=earlier):", 0, -60000, 60000, 100
        )
        if not ok or offset == 0:
            return

        cmd = BatchShiftCommand(self._project.subtitle_track, offset)
        self._undo_stack.push(cmd)
        self.statusBar().showMessage(f"All subtitles shifted by {offset:+d}ms")

    def _on_preferences(self) -> None:
        """Show the preferences dialog."""
        dialog = PreferencesDialog(self)
        if dialog.exec():
            # Settings are saved in the dialog, just show a message
            self.statusBar().showMessage("Preferences updated")
            # Note: Some settings (like theme) require restart

    # ------------------------------------------------------------ Track management

    def _on_track_changed(self, index: int) -> None:
        if 0 <= index < len(self._project.subtitle_tracks):
            self._project.active_track_index = index
            track = self._project.subtitle_track
            self._video_widget.set_subtitle_track(track if len(track) > 0 else None)
            self._subtitle_panel.set_track(track if len(track) > 0 else None)
            self._timeline.set_track(track if len(track) > 0 else None)
            self._undo_stack.clear()
            self.statusBar().showMessage(f"Switched to track: {track.name or f'Track {index+1}'}")

    def _on_track_added(self, name: str) -> None:
        new_track = SubtitleTrack(name=name)
        self._project.subtitle_tracks.append(new_track)
        self._project.active_track_index = len(self._project.subtitle_tracks) - 1
        self._refresh_track_selector()
        self._on_track_changed(self._project.active_track_index)

    def _on_track_removed(self, index: int) -> None:
        if len(self._project.subtitle_tracks) <= 1:
            QMessageBox.warning(self, "Cannot Remove", "At least one track must remain.")
            return
        if 0 <= index < len(self._project.subtitle_tracks):
            self._project.subtitle_tracks.pop(index)
            self._project.active_track_index = min(
                self._project.active_track_index, len(self._project.subtitle_tracks) - 1
            )
            self._refresh_track_selector()
            self._on_track_changed(self._project.active_track_index)

    def _on_track_renamed(self, index: int, name: str) -> None:
        if 0 <= index < len(self._project.subtitle_tracks):
            self._project.subtitle_tracks[index].name = name
            self._refresh_track_selector()

    # ------------------------------------------------------------ Actions

    def _on_open_video(self) -> None:
        settings = QSettings()
        last_dir = settings.value("last_video_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", last_dir, VIDEO_FILTER
        )
        if not path:
            return

        settings.setValue("last_video_dir", str(Path(path).parent))
        self._load_video(Path(path))

    # Formats that macOS AVFoundation cannot play natively
    _NEEDS_CONVERT = {".mkv", ".avi", ".flv", ".wmv", ".webm"}

    # All supported video formats
    _VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v"}

    def _load_video(self, path: Path) -> None:
        self._project.reset()
        self._undo_stack.clear()
        self._cleanup_temp_video()
        self._project.video_path = path

        playback_path = path
        if sys.platform == "darwin" and path.suffix.lower() in self._NEEDS_CONVERT:
            converted = self._convert_to_mp4(path)
            if converted:
                playback_path = converted
                self._temp_video_path = converted
            else:
                QMessageBox.critical(
                    self, "Conversion Failed",
                    f"Could not convert {path.suffix} to MP4 for playback.\n"
                    "Make sure FFmpeg is installed."
                )
                return

        # Detect if video has audio
        try:
            self._project.video_has_audio = AudioMerger.has_audio_stream(path)
        except Exception:
            self._project.video_has_audio = False

        self._player.setSource(QUrl.fromLocalFile(str(playback_path)))
        self._player.play()

        self._video_widget.set_subtitle_track(None)
        self._subtitle_panel.set_track(None)
        self._timeline.set_track(None)
        self._timeline.set_image_overlay_track(None)
        self._video_widget.set_image_overlay_track(None)
        self._refresh_track_selector()

        # Start waveform generation in background
        if self._project.video_has_audio:
            self._start_waveform_generation(path)
        else:
            self._timeline.clear_waveform()

        self.setWindowTitle(f"{path.name} – {APP_NAME}")
        self.statusBar().showMessage(f"Loaded: {path.name}")

    def _convert_to_mp4(self, source: Path) -> Path | None:
        """Convert a non-MP4 video to a temp MP4 file using FFmpeg."""
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return None

        tmp = Path(tempfile.mktemp(suffix=".mp4", prefix="fmm_"))
        cmd = [
            ffmpeg,
            "-i", str(source),
            "-map", "0:v:0",  # Map first video stream
            "-map", "0:a:0?",  # Map first audio stream if exists
            "-c:v", "copy",
            "-c:a", "aac",
            "-ac", "2",  # Downmix to stereo (critical for laptop speakers!)
            "-b:a", "192k",
            "-strict", "experimental",
            "-y",
            str(tmp),
        ]

        progress = QProgressDialog(f"Converting {source.name} to MP4...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=300,
            )
            progress.close()
            if result.returncode == 0 and tmp.is_file():
                self.statusBar().showMessage(f"Converted {source.suffix} to MP4 for playback")
                return tmp
            else:
                # If copy codec fails, try re-encoding
                cmd_reencode = [
                    ffmpeg,
                    "-i", str(source),
                    "-map", "0:v:0",
                    "-map", "0:a:0?",
                    "-c:v", "libx264", "-preset", "fast",
                    "-c:a", "aac",
                    "-ac", "2",  # Downmix to stereo
                    "-b:a", "192k",
                    "-strict", "experimental",
                    "-y",
                    str(tmp),
                ]
                progress2 = QProgressDialog(f"Re-encoding {source.name}...", None, 0, 0, self)
                progress2.setWindowModality(Qt.WindowModality.WindowModal)
                progress2.setMinimumDuration(0)
                progress2.show()
                QApplication.processEvents()
                result2 = subprocess.run(
                    cmd_reencode, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=600,
                )
                progress2.close()
                if result2.returncode == 0 and tmp.is_file():
                    return tmp
                return None
        except subprocess.TimeoutExpired:
            progress.close()
            tmp.unlink(missing_ok=True)
            return None

    def _cleanup_temp_video(self) -> None:
        """Remove previously created temp video file."""
        if self._temp_video_path and self._temp_video_path.is_file():
            self._temp_video_path.unlink(missing_ok=True)
        self._temp_video_path = None

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._project.duration_ms = duration_ms
        self._timeline.set_duration(duration_ms)

    def _on_generate_subtitles(self) -> None:
        if not self._project.has_video:
            QMessageBox.warning(self, "No Video", "Please open a video file first.")
            return

        if not find_ffmpeg():
            QMessageBox.critical(
                self, "FFmpeg Missing",
                "FFmpeg is required for subtitle generation but was not found."
            )
            return

        dialog = WhisperDialog(self._project.video_path, parent=self)
        if dialog.exec():
            track = dialog.result_track()
            if track and len(track) > 0:
                self._apply_subtitle_track(track)

    def _on_generate_tts(self) -> None:
        """Open TTS dialog to generate speech from script."""
        # Check FFmpeg
        if not find_ffmpeg():
            QMessageBox.critical(
                self,
                "FFmpeg Missing",
                "FFmpeg is required for TTS generation but was not found."
            )
            return

        # Get video audio path if video is loaded (optional for mixing)
        video_audio_path = self._project.video_path if self._project.has_video else None

        # Open TTS dialog
        dialog = TTSDialog(video_audio_path=video_audio_path, parent=self)
        if dialog.exec():
            track = dialog.result_track()
            audio_path = dialog.result_audio_path()

            if track and len(track) > 0:
                # Add as new track
                track.name = f"TTS Track {len(self._project.subtitle_tracks)}"
                track.audio_path = audio_path  # Store audio path for playback

                # Set audio duration for timeline visualization
                try:
                    duration_sec = AudioMerger.get_audio_duration(Path(audio_path))
                    track.audio_duration_ms = int(duration_sec * 1000)
                    track.audio_start_ms = 0  # Start at beginning of timeline
                except Exception as e:
                    # Fallback: use last segment end time
                    if len(track) > 0:
                        track.audio_duration_ms = track[-1].end_ms
                    track.audio_start_ms = 0

                self._project.subtitle_tracks.append(track)

                # Update track selector with new track list
                track_names = [t.name for t in self._project.subtitle_tracks]
                new_track_index = len(self._project.subtitle_tracks) - 1
                self._track_selector.set_tracks(track_names, new_track_index)

                # Update active track index
                self._project.active_track_index = new_track_index

                # Refresh UI to show the new track
                self._refresh_all_widgets()

                # Set timeline duration to TTS audio length if no video
                if not self._project.has_video and track.audio_duration_ms > 0:
                    self._timeline.set_duration(track.audio_duration_ms)

                self.statusBar().showMessage(
                    f"TTS generated: {len(track)} segments, audio: {audio_path}"
                )

    def _on_play_tts_audio(self) -> None:
        """Play TTS audio for the current track."""
        # Get current track
        current_track = self._project.subtitle_track

        # Check if track has audio
        if not current_track or not current_track.audio_path:
            QMessageBox.information(
                self,
                "No TTS Audio",
                "The current track doesn't have TTS audio.\n\n"
                "Generate TTS audio first (Ctrl+T)."
            )
            return

        # Check if audio file exists
        audio_path = Path(current_track.audio_path)
        if not audio_path.exists():
            QMessageBox.warning(
                self,
                "Audio File Not Found",
                f"TTS audio file not found:\n{audio_path}\n\n"
                "It may have been deleted."
            )
            return

        # Stop current TTS playback if any
        if self._tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._tts_player.stop()

        # Play TTS audio
        self._tts_player.setSource(QUrl.fromLocalFile(str(audio_path)))
        self._tts_player.play()

        self.statusBar().showMessage(
            f"Playing TTS audio: {current_track.name}"
        )

    def _on_regenerate_audio(self) -> None:
        """Regenerate merged audio file from timeline segment positions."""
        from src.services.audio_regenerator import AudioRegenerator

        # Get current track
        current_track = self._project.subtitle_track

        # Check if track has audio segments
        audio_segments = [seg for seg in current_track.segments if seg.audio_file]
        if not audio_segments:
            QMessageBox.information(
                self,
                "No Audio Segments",
                "The current track doesn't have audio segments.\n\n"
                "Generate TTS audio first (Ctrl+T)."
            )
            return

        # Confirm regeneration
        reply = QMessageBox.question(
            self,
            "Regenerate Audio?",
            f"Regenerate merged audio based on current timeline positions?\n\n"
            f"This will create a new audio file with segments positioned "
            f"according to the timeline.\n\n"
            f"Segments: {len(audio_segments)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # Show progress
            self.statusBar().showMessage("Regenerating audio from timeline...")
            QApplication.processEvents()

            # Prepare output path
            from src.utils.config import APP_NAME
            import uuid
            user_data_dir = Path.home() / f".{APP_NAME.lower()}"
            user_data_dir.mkdir(parents=True, exist_ok=True)
            output_path = user_data_dir / f"tts_regen_{uuid.uuid4().hex[:8]}.mp3"

            # Get video audio path if exists
            video_audio_path = None
            if self._project.video_path and self._project.video_has_audio:
                video_audio_path = self._project.video_path

            # Regenerate audio
            regenerated_audio, total_duration_ms = AudioRegenerator.regenerate_track_audio(
                track=current_track,
                output_path=output_path,
                video_audio_path=video_audio_path,
                bg_volume=0.5,
                tts_volume=1.0
            )

            # Update track with new audio
            current_track.audio_path = str(regenerated_audio)
            current_track.audio_start_ms = 0
            current_track.audio_duration_ms = total_duration_ms

            # Update timeline
            if not self._project.has_video:
                self._timeline.set_duration(total_duration_ms)

            self._refresh_all_widgets()

            # Stop current playback and load new audio
            self._player.pause()
            self._tts_player.stop()

            # Refresh subtitle display with updated timeline positions
            self._video_widget.set_subtitle_track(current_track)
            current_pos = self._player.position()
            self._on_player_position_changed(current_pos)

            self.statusBar().showMessage(
                f"Audio regenerated: {len(audio_segments)} segments, "
                f"{total_duration_ms/1000:.1f}s",
                5000
            )

            QMessageBox.information(
                self,
                "Audio Regenerated",
                f"Audio has been regenerated successfully!\n\n"
                f"Segments: {len(audio_segments)}\n"
                f"Duration: {total_duration_ms/1000:.1f}s\n\n"
                f"Play to hear the updated audio."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Regeneration Failed",
                f"Failed to regenerate audio:\n\n{e}"
            )
            self.statusBar().showMessage("Audio regeneration failed", 5000)

    def _on_toggle_position_edit(self, checked: bool) -> None:
        """Toggle subtitle position editing mode."""
        self._video_widget.set_subtitle_edit_mode(checked)

        if checked:
            self.statusBar().showMessage(
                "Edit Mode: Drag subtitle to reposition. Press Ctrl+E again to save."
            )
        else:
            # Save position when exiting edit mode
            position = self._video_widget.get_subtitle_position()
            if position:
                x, y = position
                # Update current segment's style
                current_track = self._project.subtitle_track
                if current_track and len(current_track) > 0:
                    # Update default style with custom position
                    self._project.default_style.custom_x = x
                    self._project.default_style.custom_y = y
                    self._video_widget.set_default_style(self._project.default_style)

                    # Refresh subtitle display with new position
                    self._video_widget.set_subtitle_track(current_track)

                    # Force update at current playback position
                    current_pos = self._player.position()
                    self._on_player_position_changed(current_pos)

                    self.statusBar().showMessage(
                        f"Subtitle position saved: ({x}, {y})"
                    )
                    # Mark as edited for autosave
                    self._on_document_edited()
            else:
                self.statusBar().showMessage("Edit Mode OFF")

    def _apply_subtitle_track(self, track: SubtitleTrack) -> None:
        self._project.subtitle_track = track
        self._undo_stack.clear()
        self._video_widget.set_subtitle_track(track)
        self._subtitle_panel.set_track(track)
        self._timeline.set_track(track)
        self._refresh_track_selector()
        self.statusBar().showMessage(
            f"Subtitles loaded: {len(track)} segments"
        )

    def _on_clear_subtitles(self) -> None:
        self._project.subtitle_track = SubtitleTrack(name=self._project.subtitle_track.name)
        self._undo_stack.clear()
        self._video_widget.set_subtitle_track(None)
        self._subtitle_panel.set_track(None)
        self._timeline.set_track(None)
        self.statusBar().showMessage("Subtitles cleared")

    def _on_translate_track(self) -> None:
        """Open the translate dialog and process the translation."""
        if not self._project.has_subtitles:
            QMessageBox.warning(self, "No Subtitles", "There are no subtitles to translate.")
            return

        # Available languages
        available_langs = [
            "Korean", "English", "Japanese", "Chinese", "Spanish", "French",
            "German", "Russian", "Portuguese", "Italian", "Dutch"
        ]

        # Create and show the dialog
        dialog = TranslateDialog(self._project.subtitle_track, available_langs, self)
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            translated_track = dialog.get_result_track()
            if translated_track:
                if dialog.is_new_track():
                    # Add as new track
                    self._project.subtitle_tracks.append(translated_track)
                    self._project.active_track_index = len(self._project.subtitle_tracks) - 1
                    self._refresh_track_selector()
                    self._on_track_changed(self._project.active_track_index)
                    self.statusBar().showMessage(f"Added translated track: {translated_track.name}")
                else:
                    # Replace current track
                    self._project.subtitle_track = translated_track
                    self._refresh_all_widgets()
                    self.statusBar().showMessage("Track translated")

                # Notify autosave
                self._autosave.notify_edit()

    def _on_edit_default_style(self) -> None:
        from src.ui.dialogs.style_dialog import StyleDialog
        dialog = StyleDialog(self._project.default_style, parent=self, title="Default Subtitle Style")
        if dialog.exec():
            self._project.default_style = dialog.result_style()
            self._video_widget.set_default_style(self._project.default_style)
            self.statusBar().showMessage("Default style updated")

    def _on_edit_segment_style(self, index: int) -> None:
        if not self._project.has_subtitles or index < 0 or index >= len(self._project.subtitle_track):
            return
        from src.ui.dialogs.style_dialog import StyleDialog
        seg = self._project.subtitle_track[index]
        current_style = seg.style if seg.style is not None else self._project.default_style
        dialog = StyleDialog(current_style, parent=self, title=f"Style - Segment {index + 1}")
        if dialog.exec():
            old_style = seg.style
            new_style = dialog.result_style()
            cmd = EditStyleCommand(self._project.subtitle_track, index, old_style, new_style)
            self._undo_stack.push(cmd)
            self._video_widget.set_default_style(self._project.default_style)
            self.statusBar().showMessage(f"Style updated (segment {index + 1})")

    def _on_import_srt(self, path=None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Import SRT", "", "SRT Files (*.srt);;All Files (*)"
            )
            if not path:
                return

        try:
            path = Path(path) if isinstance(path, str) else path
            track = import_srt(path)
            track.name = self._project.subtitle_track.name
            self._apply_subtitle_track(track)
            self._autosave.notify_edit()
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _on_import_srt_new_track(self, path=None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Import SRT to New Track", "", "SRT Files (*.srt);;All Files (*)"
            )
            if not path:
                return

        try:
            path = Path(path) if isinstance(path, str) else path
            track = import_srt(path)
            track_name = path.stem
            track.name = track_name
            self._project.subtitle_tracks.append(track)
            self._project.active_track_index = len(self._project.subtitle_tracks) - 1
            self._undo_stack.clear()
            self._refresh_track_selector()
            self._on_track_changed(self._project.active_track_index)
            self._autosave.notify_edit()
            self.statusBar().showMessage(f"Imported to new track: {track_name}")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _on_export_srt(self) -> None:
        if not self._project.has_subtitles:
            QMessageBox.warning(self, "No Subtitles", "There are no subtitles to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export SRT", "", "SRT Files (*.srt);;All Files (*)"
        )
        if not path:
            return

        try:
            export_srt(self._project.subtitle_track, Path(path))
            self.statusBar().showMessage(f"Exported: {path}")
        except OSError as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _on_export_video(self) -> None:
        if not self._project.has_video:
            QMessageBox.warning(self, "No Video", "Please open a video file first.")
            return
        if not self._project.has_subtitles:
            QMessageBox.warning(self, "No Subtitles", "There are no subtitles to burn in.")
            return
        if not find_ffmpeg():
            QMessageBox.critical(self, "FFmpeg Missing", "FFmpeg is required for video export.")
            return

        from src.ui.dialogs.export_dialog import ExportDialog
        overlay_path = None
        if self._overlay_template:
            overlay_path = Path(self._overlay_template.image_path)
        io_track = self._project.image_overlay_track
        img_overlays = list(io_track.overlays) if len(io_track) > 0 else None
        dialog = ExportDialog(
            self._project.video_path,
            self._project.subtitle_track,
            parent=self,
            video_has_audio=self._project.video_has_audio,
            overlay_path=overlay_path,
            image_overlays=img_overlays,
        )
        dialog.exec()

    def _on_batch_export(self) -> None:
        if not self._project.has_video:
            QMessageBox.warning(self, "No Video", "Please open a video file first.")
            return
        if not self._project.has_subtitles:
            QMessageBox.warning(self, "No Subtitles", "There are no subtitles to burn in.")
            return
        if not find_ffmpeg():
            QMessageBox.critical(self, "FFmpeg Missing", "FFmpeg is required for video export.")
            return

        from src.ui.dialogs.batch_export_dialog import BatchExportDialog
        dialog = BatchExportDialog(
            self._project.video_path,
            self._project.subtitle_track,
            parent=self,
            video_has_audio=self._project.video_has_audio,
        )
        dialog.exec()

    # ------------------------------------------------------------ Templates

    def _on_template_applied(self, template) -> None:
        """Apply an overlay template to the video player."""
        self._overlay_template = template
        self._video_widget.set_overlay(template.image_path, template.opacity)
        self.statusBar().showMessage(f"Template applied: {template.name}")

    def _on_template_cleared(self) -> None:
        """Remove the overlay template from the video player."""
        self._overlay_template = None
        self._video_widget.clear_overlay()
        self.statusBar().showMessage("Template cleared")

    def _on_save_project(self) -> None:
        if not self._project.has_video:
            QMessageBox.warning(self, "No Video", "Please open a video file first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "FastMovieMaker Project (*.fmm.json);;All Files (*)"
        )
        if not path:
            return
        try:
            from src.services.project_io import save_project
            path = Path(path)
            save_project(self._project, path)
            self._current_project_path = path
            self._autosave.set_active_file(path)
            self._update_recent_menu()
            self.statusBar().showMessage(f"Project saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _on_load_project(self, path=None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load Project", "", "FastMovieMaker Project (*.fmm.json);;All Files (*)"
            )
            if not path:
                return

        try:
            from src.services.project_io import load_project
            path = Path(path)
            project = load_project(path)
            self._project = project
            self._current_project_path = path
            self._autosave.set_project(project)
            self._autosave.set_active_file(path)
            self._undo_stack.clear()

            # Load video if it exists
            if project.video_path and project.video_path.is_file():
                self._player.setSource(QUrl.fromLocalFile(str(project.video_path)))
                self._player.play()
                self.setWindowTitle(f"{project.video_path.name} – {APP_NAME}")

            # Apply subtitles
            self._video_widget.set_default_style(project.default_style)
            self._refresh_track_selector()
            if project.has_subtitles:
                track = project.subtitle_track
                self._video_widget.set_subtitle_track(track)
                self._subtitle_panel.set_track(track)
                self._timeline.set_track(track)

            # Apply image overlays
            io_track = project.image_overlay_track
            if len(io_track) > 0:
                self._timeline.set_image_overlay_track(io_track)
                self._video_widget.set_image_overlay_track(io_track)

            self._update_recent_menu()
            self.statusBar().showMessage(f"Project loaded: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", str(e))

    def _on_timeline_seek(self, position_ms: int) -> None:
        if self._project.has_video:
            self._player.setPosition(position_ms)
            self._sync_tts_playback()
        else:
            # No video - directly seek TTS player
            track = self._project.subtitle_track
            if track and track.audio_path and track.audio_duration_ms > 0:
                audio_start = track.audio_start_ms
                audio_end = audio_start + track.audio_duration_ms
                if audio_start <= position_ms < audio_end:
                    tts_pos = position_ms - audio_start
                    self._tts_player.setPosition(tts_pos)
            self._timeline.set_playhead(position_ms)

    def _on_position_changed_by_user(self, position_ms: int) -> None:
        """Handle position change from playback controls slider."""
        self._sync_tts_playback()

    def _on_player_position_changed(self, position_ms: int) -> None:
        """Handle video player position change."""
        # If video is loaded, use video position
        if self._project.has_video:
            self._timeline.set_playhead(position_ms)
            # Update subtitle display based on current position
            self._video_widget._update_subtitle(position_ms)

    def _on_tts_position_changed(self, position_ms: int) -> None:
        """Handle TTS player position change."""
        track = self._project.subtitle_track
        if track and track.audio_path:
            timeline_pos = track.audio_start_ms + position_ms

            # Apply per-segment volume
            seg = track.segment_at(timeline_pos)
            if seg:
                self._tts_audio_output.setVolume(seg.volume)
            else:
                self._tts_audio_output.setVolume(1.0)

            # If no video, use TTS position for timeline
            if not self._project.has_video:
                self._timeline.set_playhead(timeline_pos)
                # Update subtitle display based on timeline position
                self._video_widget._update_subtitle(timeline_pos)

    def _on_player_error(self, error, error_string: str) -> None:
        self.statusBar().showMessage(f"Player error: {error_string}")

    def _on_take_screenshot(self) -> None:
        """Capture a screenshot of the main window for debugging."""
        try:
            # Generate timestamp filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = Path(f"/tmp/fastmoviemaker_screenshot_{timestamp}.png")

            # Capture the window directly (more reliable on macOS)
            pixmap = self.grab()
            pixmap.save(str(screenshot_path))

            # Show status message with path
            self.statusBar().showMessage(
                f"Screenshot saved: {screenshot_path} ({pixmap.width()}x{pixmap.height()})", 5000
            )
            print(f"✅ Screenshot saved to: {screenshot_path}")
            print(f"   Pixmap size: {pixmap.width()}x{pixmap.height()}")

        except Exception as e:
            QMessageBox.warning(
                self,
                "Screenshot Failed",
                f"Failed to capture screenshot:\n{e}"
            )
            print(f"❌ Screenshot error: {e}")

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "Video subtitle editor with Whisper-based\n"
            "automatic subtitle generation.",
        )

    # --------------------------------------------------------- Lifecycle

    def _restore_geometry(self) -> None:
        settings = QSettings()
        geo = settings.value("window_geometry")
        if geo:
            self.restoreGeometry(geo)
        state = settings.value("window_state")
        if state:
            self.restoreState(state)

    # ------------------------------------------------- Autosave & Recovery

    def _check_recovery(self) -> None:
        """Check for any recovery files on startup."""
        recovery_path = self._autosave.check_for_recovery()
        if recovery_path:
            dialog = RecoveryDialog([recovery_path], self)
            result = dialog.exec()

            if result == 1:  # Accepted (restore)
                try:
                    recovery_file = dialog.get_selected_file()
                    recovered_project = self._autosave.load_recovery(recovery_file)
                    self._project = recovered_project

                    # Load video if it exists
                    if recovered_project.video_path and recovered_project.video_path.is_file():
                        self._player.setSource(QUrl.fromLocalFile(str(recovered_project.video_path)))
                        self.setWindowTitle(f"{recovered_project.video_path.name} – {APP_NAME} (Recovered)")

                    # Apply subtitles
                    if recovered_project.has_subtitles:
                        self._video_widget.set_default_style(recovered_project.default_style)
                        track = recovered_project.subtitle_track
                        self._video_widget.set_subtitle_track(track)
                        self._subtitle_panel.set_track(track)
                        self._timeline.set_track(track)
                        self._refresh_track_selector()

                    self.statusBar().showMessage("Project recovered successfully")
                except Exception as e:
                    QMessageBox.critical(self, "Recovery Error", str(e))

            # Clean up recovery files whether restored or discarded
            self._autosave.cleanup_recovery_files()

    def _update_recent_menu(self) -> None:
        """Update the Recent Projects menu with latest entries."""
        self._recent_menu.clear()

        recent_files = self._autosave.get_recent_files()
        if not recent_files:
            no_recent = QAction("No Recent Projects", self)
            no_recent.setEnabled(False)
            self._recent_menu.addAction(no_recent)
            return

        for i, path in enumerate(recent_files):
            action = QAction(f"{i+1}. {path.name}", self)
            action.setData(str(path))
            action.triggered.connect(self._on_open_recent)
            self._recent_menu.addAction(action)

        self._recent_menu.addSeparator()
        clear_action = QAction("Clear Recent Projects", self)
        clear_action.triggered.connect(self._on_clear_recent)
        self._recent_menu.addAction(clear_action)

    def _on_open_recent(self) -> None:
        """Open a project from the recent files menu."""
        action = self.sender()
        if action and action.data():
            path = Path(action.data())
            if path.is_file():
                self._on_load_project(path)
            else:
                QMessageBox.warning(
                    self, "File Not Found",
                    f"The file {path} no longer exists."
                )
                # Remove from recent list
                self._autosave.get_recent_files()
                self._update_recent_menu()

    def _on_clear_recent(self) -> None:
        """Clear the recent files list."""
        self._autosave.clear_recent_files()
        self._update_recent_menu()

    def _on_autosave_completed(self, path: Path) -> None:
        """Called when an autosave operation completes."""
        self.statusBar().showMessage(f"Autosaved: {path.name}", 2000)

    def _on_document_edited(self) -> None:
        """Called when the document is edited (via undo stack)."""
        self._autosave.notify_edit()

    # ------------------------------------------------- Lifecycle

    # ----------------------------------------------------- Drag & Drop

    def dragEnterEvent(self, event) -> None:
        """Handle drag enter events for files."""
        if event.mimeData().hasUrls():
            # Check if any URL is a supported file type
            urls = event.mimeData().urls()
            if any(self._is_supported_file(url) for url in urls):
                event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        """Handle drop events for files."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if not urls:
                return

            # Process only the first URL for simplicity
            url = urls[0]
            path = Path(url.toLocalFile())
            if not path.is_file():
                return

            # Determine file type and handle accordingly
            suffix = path.suffix.lower()

            if suffix == ".srt":
                # Ask if they want to create a new track or replace current
                result = QMessageBox.question(
                    self, "Import SRT",
                    "Do you want to import this SRT file as a new track?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if result == QMessageBox.StandardButton.Yes:
                    self._on_import_srt_new_track(path)
                else:
                    self._on_import_srt(path)

            elif suffix == ".fmm.json":
                self._on_load_project(path)

            elif suffix in self._VIDEO_EXTENSIONS:
                self._load_video(path)

            event.acceptProposedAction()

    def _is_supported_file(self, url) -> bool:
        """Check if the URL is a supported file type."""
        path = Path(url.toLocalFile())
        if not path.is_file():
            return False

        suffix = path.suffix.lower()
        return suffix in self._VIDEO_EXTENSIONS or suffix == ".srt" or suffix == ".fmm.json"

    # ----------------------------------------------------- Lifecycle

    def closeEvent(self, event) -> None:
        settings = QSettings()
        settings.setValue("window_geometry", self.saveGeometry())
        settings.setValue("window_state", self.saveState())
        self._player.stop()
        self._stop_waveform_generation()
        self._cleanup_temp_video()
        # Final save before closing
        self._autosave.save_now()
        super().closeEvent(event)

    # ------------------------------------------------ Waveform generation

    def _start_waveform_generation(self, video_path: Path) -> None:
        """Start background waveform peak computation."""
        self._stop_waveform_generation()
        self._timeline.clear_waveform()

        self._waveform_thread = QThread()
        self._waveform_worker = WaveformWorker(video_path)
        self._waveform_worker.moveToThread(self._waveform_thread)

        self._waveform_thread.started.connect(self._waveform_worker.run)
        self._waveform_worker.status_update.connect(
            lambda msg: self.statusBar().showMessage(msg, 3000)
        )
        self._waveform_worker.finished.connect(self._on_waveform_finished)
        self._waveform_worker.error.connect(self._on_waveform_error)
        self._waveform_worker.finished.connect(self._cleanup_waveform_thread)
        self._waveform_worker.error.connect(self._cleanup_waveform_thread)

        self._waveform_thread.start()

    def _on_waveform_finished(self, waveform_data) -> None:
        """Handle completed waveform computation."""
        self._timeline.set_waveform(waveform_data)
        self.statusBar().showMessage("Waveform loaded", 3000)

    def _on_waveform_error(self, message: str) -> None:
        """Handle waveform computation error (non-fatal)."""
        print(f"Warning: Waveform generation failed: {message}")
        self.statusBar().showMessage("Waveform unavailable", 3000)

    def _stop_waveform_generation(self) -> None:
        """Cancel any in-progress waveform computation."""
        if self._waveform_worker:
            self._waveform_worker.cancel()
        self._cleanup_waveform_thread()

    def _cleanup_waveform_thread(self) -> None:
        """Clean up waveform worker thread."""
        if self._waveform_thread and self._waveform_thread.isRunning():
            self._waveform_thread.quit()
            self._waveform_thread.wait(5000)
        self._waveform_thread = None
        self._waveform_worker = None
