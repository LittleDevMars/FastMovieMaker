"""Main application window."""

import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QTimer, QUrl, Qt, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut, QUndoStack
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
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
from src.services.frame_cache_service import FrameCacheService
from src.workers.frame_cache_worker import FrameCacheWorker
from src.services.autosave import AutoSaveManager
from src.services.subtitle_exporter import export_srt, import_srt, import_smi
from src.services.translator import TranslatorService
from src.ui.dialogs.preferences_dialog import PreferencesDialog
from src.ui.dialogs.recovery_dialog import RecoveryDialog
from src.ui.dialogs.translate_dialog import TranslateDialog
from src.models.video_clip import VideoClipTrack
from src.ui.commands import (
    AddSegmentCommand,
    AddVideoClipCommand,
    BatchShiftCommand,
    DeleteClipCommand,
    DeleteSegmentCommand,
    EditStyleCommand,
    EditTextCommand,
    EditTimeCommand,
    EditVolumeCommand,
    EditSpeedCommand,
    MergeCommand,
    MoveSegmentCommand,
    SplitClipCommand,
    SplitCommand,
    TrimClipCommand,
    EditTransitionCommand,
)
from src.ui.dialogs.transition_dialog import TransitionDialog
from src.ui.media_library_panel import MediaLibraryPanel
from src.ui.templates_panel import TemplatesPanel
from src.ui.playback_controls import PlaybackControls
from src.ui.subtitle_panel import SubtitlePanel
from src.ui.timeline_widget import TimelineWidget
from src.ui.track_header_panel import TrackHeaderPanel
from src.ui.track_selector import TrackSelector
from src.ui.video_player_widget import VideoPlayerWidget
from src.ui.dialogs.whisper_dialog import WhisperDialog
from src.ui.dialogs.tts_dialog import TTSDialog
from src.utils.config import APP_NAME, APP_VERSION, VIDEO_FILTER, find_ffmpeg
from src.utils.i18n import tr
from src.workers.waveform_worker import WaveformWorker
from src.workers.video_load_worker import VideoLoadWorker


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
        self._current_playback_source: str | None = None  # track which video is loaded
        self._current_track_index: int = 0
        self._current_clip_index: int = 0  # track which clip in the clip track is playing
        self._pending_seek_ms: int | None = None  # seek after source switch
        self._pending_auto_play: bool = False  # auto-play after source switch
        self._play_intent: bool = False  # user intended playback; persists across clip switches

        # Watchdog timer: clear stuck pending seek when media status callbacks
        # fail to arrive (observed on rapid multi-source scrubs)
        self._pending_seek_timer = QTimer(self)
        self._pending_seek_timer.setSingleShot(True)
        self._pending_seek_timer.setInterval(1500)  # 1.5s timeout
        self._pending_seek_timer.timeout.connect(self._on_pending_seek_timeout)

        # Cancellable timer for play+pause render trick
        self._render_pause_timer = QTimer(self)
        self._render_pause_timer.setSingleShot(True)
        self._render_pause_timer.setInterval(50)
        self._render_pause_timer.timeout.connect(self._on_render_pause)

        # TTS audio player (separate from video player)
        self._tts_audio_output = QAudioOutput()
        self._tts_audio_output.setVolume(1.0)
        self._tts_player = QMediaPlayer()
        self._tts_player.setAudioOutput(self._tts_audio_output)

        # Waveform worker
        self._waveform_thread: QThread | None = None
        self._waveform_worker: WaveformWorker | None = None

        # Frame cache
        self._frame_cache_service: FrameCacheService | None = None
        self._frame_cache_thread: QThread | None = None
        self._frame_cache_worker: FrameCacheWorker | None = None
        self._showing_cached_frame = False

        self._build_ui()
        self._build_menu()
        self._setup_shortcuts()
        self._connect_signals()
        self._apply_frame_fps()
        self._restore_geometry()

        # FFmpeg check
        if not find_ffmpeg():
            self.statusBar().showMessage(tr("Warning: FFmpeg not found – subtitle generation won't work"))
        else:
            self.statusBar().showMessage(tr("Ready"))

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
        self._right_tabs.addTab(subtitle_tab, tr("Subtitles"))
        self._right_tabs.addTab(self._media_panel, tr("Media"))
        self._right_tabs.addTab(self._templates_panel, tr("Templates"))

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
        self._track_headers = TrackHeaderPanel()
        self._track_headers.state_changed.connect(self._on_track_state_changed)

        # Timeline container to hold headers and timeline widget
        self._timeline_container = QWidget()
        timeline_outer_layout = QHBoxLayout(self._timeline_container)
        timeline_outer_layout.setContentsMargins(0, 0, 0, 0)
        timeline_outer_layout.setSpacing(0)
        timeline_outer_layout.addWidget(self._track_headers)
        timeline_outer_layout.addWidget(self._timeline, 1)

        # Timeline zoom toolbar
        self._zoom_toolbar = QWidget()
        self._zoom_toolbar.setFixedHeight(28)
        self._zoom_toolbar.setStyleSheet("background-color: rgb(40, 40, 40); border-top: 1px solid rgb(60, 60, 60);")
        zoom_layout = QHBoxLayout(self._zoom_toolbar)
        zoom_layout.setContentsMargins(6, 2, 6, 2)
        zoom_layout.setSpacing(4)

        btn_style = """
            QPushButton { background: rgb(60,60,60); color: white; border: 1px solid rgb(80,80,80); border-radius: 3px; padding: 1px 8px; font-size: 12px; }
            QPushButton:hover { background: rgb(80,80,80); }
            QPushButton:checked { background: rgb(60, 100, 180); border: 1px solid rgb(100, 160, 240); }
        """

        self._snap_toggle_btn = QPushButton(tr("Snap"))
        self._snap_toggle_btn.setCheckable(True)
        self._snap_toggle_btn.setChecked(True)  # Default on
        self._snap_toggle_btn.setFixedWidth(50)
        self._snap_toggle_btn.setStyleSheet(btn_style)
        self._snap_toggle_btn.setToolTip(tr("Toggle Magnetic Snap (S)"))
        self._snap_toggle_btn.clicked.connect(self._toggle_magnetic_snap)

        self._zoom_fit_btn = QPushButton(tr("Fit"))
        self._zoom_fit_btn.setFixedWidth(36)
        self._zoom_fit_btn.setStyleSheet(btn_style)
        self._zoom_fit_btn.setToolTip(tr("Fit entire timeline (Ctrl+0)"))
        self._zoom_fit_btn.setToolTip(tr("Fit entire timeline (Ctrl+0)"))
        self._zoom_fit_btn.clicked.connect(self._timeline.zoom_fit)

        # Ripple Edit Toggle
        self._ripple_toggle_btn = QPushButton("Ripple")
        self._ripple_toggle_btn.setCheckable(True)
        self._ripple_toggle_btn.setChecked(False)  # Default off
        self._ripple_toggle_btn.setFixedWidth(50)
        self._ripple_toggle_btn.setStyleSheet(btn_style)
        self._ripple_toggle_btn.setToolTip(tr("Toggle Ripple Edit Mode (R)"))
        self._ripple_toggle_btn.clicked.connect(self._toggle_ripple_mode)

        self._zoom_out_btn = QPushButton("-")
        self._zoom_out_btn.setFixedWidth(28)
        self._zoom_out_btn.setStyleSheet(btn_style)
        self._zoom_out_btn.setToolTip(tr("Zoom out (Ctrl+-)"))
        self._zoom_out_btn.clicked.connect(self._timeline.zoom_out)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(50)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setStyleSheet("color: rgb(180,180,180); font-size: 11px; border: none;")

        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setFixedWidth(28)
        self._zoom_in_btn.setStyleSheet(btn_style)
        self._zoom_in_btn.setToolTip(tr("Zoom in (Ctrl++)"))
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
        main_layout.addWidget(self._timeline_container)

        # Status bar
        self.setStatusBar(QStatusBar())

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu(tr("&File"))

        open_action = QAction(tr("&Open Video..."), self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._on_open_video)
        file_menu.addAction(open_action)

        import_srt_action = QAction(tr("&Import SRT..."), self)
        import_srt_action.setShortcut(QKeySequence("Ctrl+I"))
        import_srt_action.triggered.connect(self._on_import_srt)
        file_menu.addAction(import_srt_action)

        import_srt_track_action = QAction(tr("Import SRT to &New Track..."), self)
        import_srt_track_action.triggered.connect(self._on_import_srt_new_track)
        file_menu.addAction(import_srt_track_action)

        file_menu.addSeparator()

        export_action = QAction(tr("&Export SRT..."), self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export_srt)
        file_menu.addAction(export_action)

        export_video_action = QAction(tr("Export &Video..."), self)
        export_video_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        export_video_action.triggered.connect(self._on_export_video)
        file_menu.addAction(export_video_action)

        batch_export_action = QAction(tr("&Batch Export..."), self)
        batch_export_action.triggered.connect(self._on_batch_export)
        file_menu.addAction(batch_export_action)

        file_menu.addSeparator()

        save_action = QAction(tr("&Save Project..."), self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._on_save_project)
        file_menu.addAction(save_action)

        load_action = QAction(tr("&Load Project..."), self)
        load_action.setShortcut(QKeySequence("Ctrl+L"))
        load_action.triggered.connect(self._on_load_project)
        file_menu.addAction(load_action)

        # Recent files submenu
        self._recent_menu = QMenu(tr("Recent &Projects"), self)
        file_menu.addMenu(self._recent_menu)
        self._update_recent_menu()

        file_menu.addSeparator()

        quit_action = QAction(tr("&Quit"), self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu
        edit_menu = menubar.addMenu(tr("&Edit"))

        undo_action = self._undo_stack.createUndoAction(self, tr("&Undo"))
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        edit_menu.addAction(undo_action)

        redo_action = self._undo_stack.createRedoAction(self, tr("&Redo"))
        redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        split_action = QAction(tr("S&plit Subtitle"), self)
        split_action.triggered.connect(self._on_split_subtitle)
        edit_menu.addAction(split_action)

        merge_action = QAction(tr("&Merge Subtitles"), self)
        merge_action.triggered.connect(self._on_merge_subtitles)
        edit_menu.addAction(merge_action)

        edit_menu.addSeparator()

        add_text_overlay_action = QAction(tr("Add &Text Overlay"), self)
        add_text_overlay_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        add_text_overlay_action.triggered.connect(self._on_add_text_overlay)
        edit_menu.addAction(add_text_overlay_action)

        edit_menu.addSeparator()

        batch_shift_action = QAction(tr("&Batch Shift Timing..."), self)
        batch_shift_action.triggered.connect(self._on_batch_shift)
        edit_menu.addAction(batch_shift_action)

        edit_menu.addSeparator()

        jump_frame_action = QAction(tr("&Jump to Frame..."), self)
        jump_frame_action.setShortcut(QKeySequence("Ctrl+J"))
        jump_frame_action.triggered.connect(self._on_jump_to_frame)
        edit_menu.addAction(jump_frame_action)

        edit_menu.addSeparator()

        preferences_action = QAction(tr("&Preferences..."), self)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self._on_preferences)
        edit_menu.addAction(preferences_action)

        # Subtitles menu
        sub_menu = menubar.addMenu(tr("&Subtitles"))

        gen_action = QAction(tr("&Generate (Whisper)..."), self)
        gen_action.setShortcut(QKeySequence("Ctrl+G"))
        gen_action.triggered.connect(self._on_generate_subtitles)
        sub_menu.addAction(gen_action)

        tts_action = QAction(tr("Generate &Speech (TTS)..."), self)
        tts_action.setShortcut(QKeySequence("Ctrl+T"))
        tts_action.triggered.connect(self._on_generate_tts)
        sub_menu.addAction(tts_action)

        play_tts_action = QAction(tr("&Play TTS Audio"), self)
        play_tts_action.setShortcut(QKeySequence("Ctrl+P"))
        play_tts_action.triggered.connect(self._on_play_tts_audio)
        sub_menu.addAction(play_tts_action)

        regen_audio_action = QAction(tr("&Regenerate Audio from Timeline"), self)
        regen_audio_action.setShortcut(QKeySequence("Ctrl+R"))
        regen_audio_action.triggered.connect(self._on_regenerate_audio)
        sub_menu.addAction(regen_audio_action)

        clear_action = QAction(tr("&Clear Subtitles"), self)
        clear_action.triggered.connect(self._on_clear_subtitles)
        sub_menu.addAction(clear_action)

        sub_menu.addSeparator()

        translate_action = QAction(tr("&Translate Track..."), self)
        translate_action.triggered.connect(self._on_translate_track)
        sub_menu.addAction(translate_action)

        sub_menu.addSeparator()

        style_action = QAction(tr("Default &Style..."), self)
        style_action.triggered.connect(self._on_edit_default_style)
        sub_menu.addAction(style_action)

        sub_menu.addSeparator()

        edit_position_action = QAction(tr("Edit Subtitle &Position"), self)
        edit_position_action.setCheckable(True)
        edit_position_action.setShortcut(QKeySequence("Ctrl+E"))
        edit_position_action.triggered.connect(self._on_toggle_position_edit)
        sub_menu.addAction(edit_position_action)
        self._edit_position_action = edit_position_action  # Store reference

        # Help menu
        help_menu = menubar.addMenu(tr("&Help"))

        screenshot_action = QAction(tr("Take &Screenshot"), self)
        screenshot_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        screenshot_action.triggered.connect(self._on_take_screenshot)
        help_menu.addAction(screenshot_action)

        help_menu.addSeparator()

        about_action = QAction(tr("&About"), self)
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

        # Delete → delete selected clip/subtitle
        sc_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        sc_del.activated.connect(self._on_delete_selected)

        # Ctrl+B → split clip at playhead
        sc_split = QShortcut(QKeySequence("Ctrl+B"), self)
        sc_split.activated.connect(lambda: self._on_split_clip(self._timeline._playhead_ms))

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

        # S → Toggle Magnetic Snap
        sc_snap = QShortcut(QKeySequence(Qt.Key.Key_S), self)
        sc_snap.activated.connect(self._toggle_magnetic_snap)

    def _toggle_play_pause(self) -> None:
        # Check if we're currently playing
        is_playing = (
            self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState or
            self._tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )

        if is_playing:
            # Pause both players (video state change handler will also pause TTS)
            self._player.pause()
            self._tts_player.pause()
            # If source is loading, cancel pending auto-play
            if self._pending_seek_ms is not None:
                self._pending_auto_play = False
            self._play_intent = False
        else:
            # Play
            self._play_intent = True
            if self._project.has_video:
                # If source is still loading after a switch, just flag
                # auto_play so _on_media_status_changed will call play()
                # instead of play+pause when LoadedMedia fires.
                if self._pending_seek_ms is not None:
                    self._pending_auto_play = True
                    return

                # Ensure player source/position matches timeline playhead
                clip_track = self._project.video_clip_track
                if clip_track:
                    timeline_ms = self._timeline.get_playhead()
                    result = clip_track.clip_at_timeline(timeline_ms)
                    if result is not None:
                        idx, clip = result
                        self._current_clip_index = idx
                        clip_start = clip_track.clip_timeline_start(idx)
                        local_offset = timeline_ms - clip_start
                        source_ms = clip.source_in_ms + local_offset
                        target_source_raw = clip.source_path or str(self._project.video_path)
                        target_source = self._resolve_playback_path(target_source_raw)

                        # If player source doesn't match, switch first
                        if target_source != self._current_playback_source:
                            self._switch_player_source(target_source, source_ms, auto_play=True)
                            return
                        # If position is off or player is at end, seek first
                        # Reduced threshold to 10ms to prevent "jump back" visual glitches
                        # Also force seek if at EndOfMedia to reset state
                        at_end = self._player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia
                        if at_end or abs(self._player.position() - source_ms) > 10:
                            self._player.setPosition(source_ms)

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

    def _on_stop_all(self) -> None:
        """Stop both video and TTS players."""
        self._player.stop()
        self._tts_player.stop()
        self._play_intent = False

    def _sync_tts_playback(self) -> None:
        """Synchronize TTS audio playback with video position.

        Only starts TTS audio if the video player is actually playing.
        When video is paused (e.g. seek), TTS position is updated but not played.
        """
        try:
            track = self._project.subtitle_track

            # Check if track has TTS audio
            if not track or not track.audio_path or track.audio_duration_ms <= 0:
                return

            # Check if audio file exists
            audio_path = Path(track.audio_path)
            if not audio_path.exists():
                return

            video_is_playing = (
                self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )

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

                # Set position
                self._tts_player.setPosition(tts_pos_ms)

                # Only play TTS if video is actually playing
                if video_is_playing:
                    if self._tts_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                        self._tts_player.play()
                else:
                    # Video is paused — don't start TTS
                    if self._tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                        self._tts_player.pause()
            else:
                # Outside TTS audio range, stop TTS playback
                if self._tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    self._tts_player.pause()

        except Exception as e:
            pass

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

    def _apply_frame_fps(self) -> None:
        """Apply FPS setting to timeline snap and playback controls frame display."""
        from src.services.settings_manager import SettingsManager
        fps = SettingsManager().get_frame_seek_fps()
        self._timeline.set_snap_fps(fps)
        self._controls.set_display_fps(fps)

    def _on_jump_to_frame(self) -> None:
        """Open Jump to Frame dialog and seek to the specified position."""
        from src.services.settings_manager import SettingsManager
        from src.ui.dialogs.jump_to_frame_dialog import JumpToFrameDialog

        fps = SettingsManager().get_frame_seek_fps()
        current_ms = self._player.position() if self._project.has_video else 0
        duration_ms = (
            self._player.duration()
            if self._project.has_video
            else self._timeline._duration_ms
        )

        dialog = JumpToFrameDialog(current_ms, fps, duration_ms, parent=self)
        if dialog.exec() == JumpToFrameDialog.DialogCode.Accepted:
            target = dialog.target_ms()
            if target is not None:
                self._on_timeline_seek(target)

    def _on_delete_selected(self) -> None:
        # Check if a video clip is selected in timeline
        sel_track = self._timeline._selected_clip_track_index
        sel_clip = self._timeline._selected_clip_index
        if sel_track >= 0 and sel_clip >= 0:
            self._on_delete_clip(sel_track, sel_clip)
            self._timeline.select_clip(-1, -1)
            return

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
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.errorOccurred.connect(self._on_player_error)
        self._controls.play_toggled.connect(self._toggle_play_pause)
        self._controls.stop_requested.connect(self._on_stop_all)
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
        self._timeline.insert_text_requested.connect(self._on_add_text_overlay)
        self._timeline.image_overlay_moved.connect(self._on_image_overlay_moved)
        self._timeline.image_overlay_selected.connect(self._on_image_overlay_selected)
        self._timeline.image_overlay_resize.connect(self._on_image_overlay_resize)

        # Text overlay signals
        self._timeline.text_overlay_selected.connect(self._on_text_overlay_selected)
        self._timeline.text_overlay_moved.connect(self._on_text_overlay_moved)
        self._timeline.text_overlay_edit_requested.connect(self._on_text_overlay_edit_requested)
        self._timeline.text_overlay_delete_requested.connect(self._on_text_overlay_delete_requested)

        # Video clip signals
        self._timeline.clip_selected.connect(self._on_clip_selected)
        self._timeline.clip_split_requested.connect(self._on_split_clip)
        self._timeline.clip_deleted.connect(self._on_delete_clip)
        self._timeline.clip_trimmed.connect(self._on_clip_trimmed)
        self._timeline.clip_speed_requested.connect(self._on_edit_clip_speed)
        self._timeline.transition_requested.connect(self._on_transition_requested)
        self._timeline.clip_volume_requested.connect(self._on_clip_volume_requested)

        # PIP drag on video player
        self._video_widget.pip_position_changed.connect(self._on_pip_position_changed)
        self._video_widget.text_overlay_position_changed.connect(self._on_text_overlay_position_changed)

        # Track selector signals
        self._track_selector.track_changed.connect(self._on_track_changed)
        self._track_selector.track_added.connect(self._on_track_added)
        self._track_selector.track_removed.connect(self._on_track_removed)
        self._track_selector.track_renamed.connect(self._on_track_renamed)

        # Media library panel connections
        self._media_panel.video_open_requested.connect(
            lambda path: self._load_video(Path(path))
        )
        self._media_panel.image_insert_to_timeline.connect(
            self._on_media_image_insert_to_timeline
        )
        self._media_panel.subtitle_imported.connect(self._on_import_subtitle)

        # Timeline drag-and-drop signals
        self._timeline.image_file_dropped.connect(self._on_image_file_dropped)
        self._timeline.video_file_dropped.connect(self._on_video_file_dropped)

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

        # Sync text overlay track
        text_track = self._project.text_overlay_track
        self._video_widget.set_text_overlay_track(text_track if len(text_track) > 0 else None)
        self._timeline.set_text_overlay_track(text_track if len(text_track) > 0 else None)

        # Sync video clip tracks
        v_idx = getattr(self, "_current_track_index", 0)
        if 0 <= v_idx < len(self._project.video_tracks):
            clip_track = self._project.video_tracks[v_idx]
            self._timeline.set_clip_track(clip_track)
            output_dur = clip_track.output_duration_ms
            self._timeline.set_duration(self._project.duration_ms, has_video=self._project.has_video)
            self._controls.set_output_duration(self._project.duration_ms)
        
        # Ensure timeline holds the project reference
        self._timeline.set_project(self._project)
        # Notify autosave of edits
        self._autosave.notify_edit()

    def _ensure_timeline_duration(self) -> None:
        """Ensure the timeline has a non-zero duration even without a video.

        Calculates the required duration from all tracks (subtitles, TTS audio,
        image overlays) and updates both the project and timeline if needed.
        """
        if self._project.has_video and self._project.duration_ms > 0:
            return  # Video provides the duration

        needed_ms = 0

        # From subtitle/TTS tracks
        for t in self._project.subtitle_tracks:
            if t.audio_duration_ms > 0:
                needed_ms = max(needed_ms, t.audio_duration_ms)
            if len(t) > 0:
                needed_ms = max(needed_ms, t[-1].end_ms)

        # From image overlays
        for ov in self._project.image_overlay_track:
            needed_ms = max(needed_ms, ov.end_ms)

        if needed_ms > 0:
            self._project.duration_ms = max(self._project.duration_ms, needed_ms)
            self._timeline.set_duration(self._project.duration_ms)

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
            self.statusBar().showMessage(f"{tr('Text updated')} ({tr('segment')} {index + 1})")

    def _on_time_edited(self, index: int, start_ms: int, end_ms: int) -> None:
        track = self._project.subtitle_track
        if 0 <= index < len(track):
            seg = track[index]
            cmd = EditTimeCommand(track, index, seg.start_ms, seg.end_ms, start_ms, end_ms)
            self._undo_stack.push(cmd)
            self.statusBar().showMessage(f"{tr('Time updated')} ({tr('segment')} {index + 1})")

    def _on_segment_volume_edited(self, index: int, volume: float) -> None:
        track = self._project.subtitle_track
        if 0 <= index < len(track):
            old_volume = track[index].volume
            cmd = EditVolumeCommand(track, index, old_volume, volume)
            self._undo_stack.push(cmd)
            self.statusBar().showMessage(f"{tr('Volume updated')}: {int(volume * 100)}% ({tr('segment')} {index + 1})")

    def _on_segment_add(self, start_ms: int, end_ms: int) -> None:
        seg = SubtitleSegment(start_ms, end_ms, "New subtitle")
        cmd = AddSegmentCommand(self._project.subtitle_track, seg)
        self._undo_stack.push(cmd)
        self.statusBar().showMessage(tr("Subtitle added"))

    def _on_segment_delete(self, index: int) -> None:
        track = self._project.subtitle_track
        if 0 <= index < len(track):
            seg = track[index]
            cmd = DeleteSegmentCommand(track, index, seg)
            self._undo_stack.push(cmd)
            self.statusBar().showMessage(tr("Subtitle deleted"))

    def _on_timeline_segment_selected(self, index: int) -> None:
        if self._project.has_subtitles and 0 <= index < len(self._project.subtitle_track):
            self._subtitle_panel._table.selectRow(index)
            # Play only this segment's individual audio
            seg = self._project.subtitle_track[index]
            if seg.audio_file and Path(seg.audio_file).exists():
                self._tts_player.setSource(QUrl.fromLocalFile(seg.audio_file))
                self._tts_player.play()

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

            self.statusBar().showMessage(f"{tr('segment')} {index + 1} {tr('moved')}")

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
        self._ensure_timeline_duration()
        self._timeline.set_image_overlay_track(io_track)
        self._video_widget.set_image_overlay_track(io_track)
        self._autosave.notify_edit()
        self.statusBar().showMessage(f"Image overlay inserted: {Path(path).name}")

    def _on_add_text_overlay(self, position_ms: int = -1) -> None:
        """Handle request to add a text overlay."""
        if not self._project.has_video:
            QMessageBox.warning(self, tr("No Video"), tr("Please open a video file first."))
            return
        
        # Use playhead position if not specified
        if position_ms < 0:
            position_ms = self._playhead_ms
        
        # Open text overlay dialog
        from src.ui.dialogs.text_overlay_dialog import TextOverlayDialog
        from src.models.text_overlay import TextOverlay
        
        # Open dialog for editing
        dialog = TextOverlayDialog(parent=self, text="New Text", style=None)
        dialog.set_position(50.0, 50.0)
        dialog.set_opacity(1.0)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        # Get values from dialog
        text = dialog.get_text()
        style = dialog.get_style()
        x_percent, y_percent = dialog.get_position()
        opacity = dialog.get_opacity()
        
        # Create text overlay
        duration = 5000  # 5 seconds default
        end_ms = position_ms + duration
        if self._project.duration_ms > 0:
            end_ms = min(end_ms, self._project.duration_ms)
        
        overlay = TextOverlay(
            start_ms=position_ms,
            end_ms=end_ms,
            text=text,
            x_percent=x_percent,
            y_percent=y_percent,
            opacity=opacity,
            style=style,
        )
        
        # Add to project
        from src.ui.commands import AddTextOverlayCommand
        cmd = AddTextOverlayCommand(self._project.text_overlay_track, overlay)
        self._undo_stack.push(cmd)
        
        self._ensure_timeline_duration()
        self._timeline.set_text_overlay_track(self._project.text_overlay_track)
        self._video_widget.set_text_overlay_track(self._project.text_overlay_track)
        self._autosave.notify_edit()
        self.statusBar().showMessage(f"Text overlay added: {overlay.text[:20]}...")

    def _on_image_overlay_moved(self, index: int, new_start: int, new_end: int) -> None:
        """Handle image overlay drag/resize in timeline."""
        io_track = self._project.image_overlay_track
        if 0 <= index < len(io_track):
            ov = io_track[index]
            ov.start_ms = new_start
            ov.end_ms = new_end
            self._ensure_timeline_duration()
            self._timeline.update()
            self._autosave.notify_edit()
            self.statusBar().showMessage(f"Image overlay {index + 1} moved")

    def _on_image_overlay_selected(self, index: int) -> None:
        """Handle image overlay selection in timeline."""
        self._video_widget.select_pip(index)
        self.statusBar().showMessage(f"Image overlay {index + 1} selected")

    def _on_text_overlay_moved(self, index: int, new_start: int, new_end: int) -> None:
        """Handle text overlay drag/resize in timeline."""
        text_track = self._project.text_overlay_track
        if 0 <= index < len(text_track.overlays):
            ov = text_track.overlays[index]
            old_start = ov.start_ms
            old_end = ov.end_ms
            # Create undo command
            from src.ui.commands import MoveTextOverlayCommand
            cmd = MoveTextOverlayCommand(ov, old_start, old_end, new_start, new_end)
            self._undo_stack.push(cmd)
            self._ensure_timeline_duration()
            self._timeline.update()
            self._video_widget.update()
            self._autosave.notify_edit()
            self.statusBar().showMessage(f"Text overlay {index + 1} moved")

    def _on_text_overlay_selected(self, index: int) -> None:
        """Handle text overlay selection in timeline."""
        self._video_widget.select_text(index)
        self.statusBar().showMessage(f"Text overlay {index + 1} selected")

    def _on_text_overlay_edit_requested(self, index: int) -> None:
        """Handle text overlay double-click or edit request in timeline."""
        text_track = self._project.text_overlay_track
        if not (text_track and 0 <= index < len(text_track.overlays)):
            return
        
        ov = text_track.overlays[index]
        
        # Open text overlay dialog
        from src.ui.dialogs.text_overlay_dialog import TextOverlayDialog
        dialog = TextOverlayDialog(parent=self, text=ov.text, style=ov.style)
        dialog.set_position(ov.x_percent, ov.y_percent)
        dialog.set_alignment(ov.alignment, ov.v_alignment)
        dialog.set_opacity(ov.opacity)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
            
        old_data = {
            "text": ov.text,
            "style": ov.style,
            "x_percent": ov.x_percent,
            "y_percent": ov.y_percent,
            "alignment": ov.alignment,
            "v_alignment": ov.v_alignment,
            "opacity": ov.opacity
        }
        
        h_align, v_align = dialog.get_alignment()
        new_data = {
            "text": dialog.get_text(),
            "style": dialog.get_style(),
            "x_percent": dialog.get_position()[0],
            "y_percent": dialog.get_position()[1],
            "alignment": h_align,
            "v_alignment": v_align,
            "opacity": dialog.get_opacity()
        }
        
        from src.ui.commands import UpdateTextOverlayCommand
        cmd = UpdateTextOverlayCommand(ov, old_data, new_data)
        self._undo_stack.push(cmd)
        
        self._timeline.update()
        self._video_widget.update()
        self._autosave.notify_edit()
        self.statusBar().showMessage(f"Text overlay {index + 1} updated")

    def _on_text_overlay_delete_requested(self, index: int) -> None:
        """Handle text overlay deletion request from timeline context menu."""
        text_track = self._project.text_overlay_track
        if not (text_track and 0 <= index < len(text_track.overlays)):
            return
            
        from src.ui.commands import DeleteTextOverlayCommand
        cmd = DeleteTextOverlayCommand(text_track, index)
        self._undo_stack.push(cmd)
        
        self._timeline.update()
        self._video_widget.update()
        self._autosave.notify_edit()
        self.statusBar().showMessage(f"Text overlay {index + 1} deleted")

    def _on_image_overlay_resize(self, index: int, mode: str) -> None:
        """Resize an image overlay to a preset (fit_width, full, 16:9, 9:16)."""
        io_track = self._project.image_overlay_track
        if not (0 <= index < len(io_track)):
            return
        ov = io_track[index]

        # Get video dimensions (fallback to 16:9 default)
        vw = self._video_widget.viewport().width() or 1920
        vh = self._video_widget.viewport().height() or 1080

        # Get image dimensions
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap(ov.image_path)
        if pixmap.isNull():
            return
        iw, ih = pixmap.width(), pixmap.height()

        if mode == "fit":
            # Fit within video (contain), no cropping, centered
            scale_w = vw / iw
            scale_h = vh / ih
            scale = min(scale_w, scale_h)
            ov.scale_percent = scale * iw / vw * 100
            scaled_w = iw * scale
            scaled_h = ih * scale
            ov.x_percent = (vw - scaled_w) / 2 / vw * 100
            ov.y_percent = (vh - scaled_h) / 2 / vh * 100
        elif mode == "fit_width":
            # Image fills video width, centered vertically
            ov.scale_percent = 100.0
            ov.x_percent = 0.0
            scaled_h = ih * vw / iw
            ov.y_percent = (vh - scaled_h) / 2 / vh * 100
        elif mode == "fit_height":
            # Image fills video height, centered horizontally
            scale = vh / ih
            ov.scale_percent = scale * iw / vw * 100
            scaled_w = iw * scale
            ov.x_percent = (vw - scaled_w) / 2 / vw * 100
            ov.y_percent = 0.0
        elif mode == "full":
            # Image covers entire video (may crop)
            scale_w = vw / iw
            scale_h = vh / ih
            scale = max(scale_w, scale_h)
            ov.scale_percent = scale * iw / vw * 100
            scaled_w = iw * scale
            scaled_h = ih * scale
            ov.x_percent = -(scaled_w - vw) / 2 / vw * 100
            ov.y_percent = -(scaled_h - vh) / 2 / vh * 100
        elif mode == "16:9":
            # Fit image into a 16:9 box (full width, height = width*9/16)
            box_w = vw
            box_h = vw * 9 / 16
            scale_w = box_w / iw
            scale_h = box_h / ih
            scale = min(scale_w, scale_h)
            ov.scale_percent = scale * iw / vw * 100
            scaled_w = iw * scale
            scaled_h = ih * scale
            ov.x_percent = (vw - scaled_w) / 2 / vw * 100
            ov.y_percent = (vh - scaled_h) / 2 / vh * 100
        elif mode == "9:16":
            # Fit image into a 9:16 box (centered portrait)
            box_w = vh * 9 / 16
            box_h = vh
            scale_w = box_w / iw
            scale_h = box_h / ih
            scale = min(scale_w, scale_h)
            ov.scale_percent = scale * iw / vw * 100
            scaled_w = iw * scale
            scaled_h = ih * scale
            ov.x_percent = (vw - scaled_w) / 2 / vw * 100
            ov.y_percent = (vh - scaled_h) / 2 / vh * 100

        # Refresh display
        self._video_widget.set_image_overlay_track(io_track)
        self._timeline.update()
        self._autosave.notify_edit()
        self.statusBar().showMessage(f"Image overlay {index + 1}: {mode}")

    def _on_image_file_dropped(self, file_path: str, position_ms: int) -> None:
        """Handle image file dropped onto the timeline from media library."""
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
        self._ensure_timeline_duration()
        self._timeline.set_image_overlay_track(io_track)
        self._video_widget.set_image_overlay_track(io_track)
        self._autosave.notify_edit()
        self.statusBar().showMessage(f"Image overlay dropped: {Path(file_path).name}")

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
        self._ensure_timeline_duration()
        self._timeline.set_image_overlay_track(io_track)
        self._video_widget.set_image_overlay_track(io_track)
        self._autosave.notify_edit()
        self.statusBar().showMessage(f"Image overlay inserted from library: {Path(file_path).name}")

    def _on_video_file_dropped(self, path_str: str, position_ms: int) -> None:
        """Handle video file dropped onto the timeline."""
        path = Path(path_str)
        if not self._project.has_video:
            # No video loaded yet → load as primary
            self._load_video(path)
        else:
            # Already have a video → add as new clip
            self._add_video_to_timeline(path, position_ms)

    def _add_video_to_timeline(self, path: Path, position_ms: int) -> None:
        """Add an external video file as a new clip on the timeline."""
        from src.services.video_probe import probe_video
        from src.models.video_clip import VideoClip

        info = probe_video(path)
        if info.duration_ms <= 0:
            QMessageBox.warning(
                self, tr("Error"),
                tr("Could not read video duration.") + f"\n{path.name}",
            )
            return

        clip = VideoClip(
            source_in_ms=0,
            source_out_ms=info.duration_ms,
            source_path=str(path.resolve()),
        )

        clip_track = self._project.video_clip_track
        if clip_track is None:
            # Legacy project: initialize clip track from primary video
            from src.models.video_clip import VideoClipTrack
            if self._project.video_path and self._project.duration_ms > 0:
                clip_track = VideoClipTrack.from_full_video(self._project.duration_ms)
                self._project.video_clip_track = clip_track
            else:
                return

        # Determine insert position: find which clip the drop position falls in
        result = clip_track.clip_at_timeline(position_ms)
        if result is not None:
            idx, existing_clip = result
            clip_start = clip_track.clip_timeline_start(idx)
            local_offset = position_ms - clip_start

            # If dropping near the end of a clip (>80% into it), insert after
            if local_offset > existing_clip.duration_ms * 0.8:
                insert_index = idx + 1
            # If dropping near the start (<20%), insert before
            elif local_offset < existing_clip.duration_ms * 0.2:
                insert_index = idx
            else:
                # Split the existing clip and insert between the halves
                source_split = existing_clip.source_in_ms + local_offset
                first = VideoClip(existing_clip.source_in_ms, source_split,
                                  source_path=existing_clip.source_path)
                second = VideoClip(source_split, existing_clip.source_out_ms,
                                   source_path=existing_clip.source_path)
                clip_track.clips[idx] = first
                clip_track.clips.insert(idx + 1, second)
                insert_index = idx + 1
        else:
            # Beyond end → append
            insert_index = len(clip_track.clips)

        sub_track = self._project.subtitle_track
        overlay_track = self._project.image_overlay_track
        v_idx = self._current_track_index
        cmd = AddVideoClipCommand(
            self._project, v_idx, clip, sub_track, overlay_track, insert_index,
            ripple=self._timeline.is_ripple_mode()
        )
        self._undo_stack.push(cmd)

        # Update duration and refresh
        self._project.duration_ms = self._project.video_tracks[v_idx].output_duration_ms
        self._timeline.set_duration(self._project.duration_ms, has_video=True)
        self._timeline.set_clip_track(self._project.video_tracks[v_idx])
        self._timeline.refresh()
        self._controls.set_output_duration(self._project.duration_ms)
        self._autosave.notify_edit()
        self.statusBar().showMessage(
            f"{tr('Added video clip')}: {path.name} ({info.duration_ms // 1000}s)"
        )

        # Cache frames for the newly added source
        self._start_frame_cache_generation()

    def _on_delete_image_overlay(self, index: int) -> None:
        """Delete an image overlay by index."""
        io_track = self._project.image_overlay_track
        if 0 <= index < len(io_track):
            io_track.remove_overlay(index)
            self._timeline.set_image_overlay_track(io_track if len(io_track) > 0 else None)
            self._video_widget.set_image_overlay_track(io_track if len(io_track) > 0 else None)
            self._autosave.notify_edit()
            self.statusBar().showMessage(tr("Image overlay deleted"))

    def _on_pip_position_changed(self, index: int, x_pct: float, y_pct: float, scale_pct: float) -> None:
        """Handle PIP image dragged/scaled on video player."""
        io_track = self._project.image_overlay_track
        if 0 <= index < len(io_track):
            ov = io_track[index]
            ov.x_percent = round(x_pct, 2)
            ov.y_percent = round(y_pct, 2)
            ov.scale_percent = round(scale_pct, 2)
            self._autosave.notify_edit()

    def _on_text_overlay_position_changed(self, index: int, x_pct: float, y_pct: float) -> None:
        """Handle text overlay dragged on video player."""
        track = self._project.text_overlay_track
        if track and 0 <= index < len(track.overlays):
            ov = track.overlays[index]
            ov.x_percent = round(x_pct, 2)
            ov.y_percent = round(y_pct, 2)
            self._autosave.notify_edit()

    # --------------------------------------------- Split / Merge / Batch Shift

    def _on_split_subtitle(self) -> None:
        if not self._project.has_subtitles:
            QMessageBox.warning(self, tr("No Subtitles"), tr("No subtitles to split."))
            return

        rows = self._subtitle_panel._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, tr("No Selection"), tr("Select a subtitle to split."))
            return

        index = rows[0].row()
        track = self._project.subtitle_track
        if index < 0 or index >= len(track):
            return

        seg = track[index]
        split_ms = self._player.position()

        if split_ms <= seg.start_ms or split_ms >= seg.end_ms:
            QMessageBox.warning(
                self, tr("Invalid Position"),
                tr("Move the playhead inside the selected subtitle to split it.")
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
        self.statusBar().showMessage(f"{tr('segment')} {index + 1} {tr('split at')} {split_ms}ms")

    def _on_merge_subtitles(self) -> None:
        if not self._project.has_subtitles:
            QMessageBox.warning(self, tr("No Subtitles"), tr("No subtitles to merge."))
            return

        rows = self._subtitle_panel._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, tr("No Selection"), tr("Select a subtitle to merge with the next one."))
            return

        index = rows[0].row()
        track = self._project.subtitle_track
        if index < 0 or index + 1 >= len(track):
            QMessageBox.warning(self, tr("Cannot Merge"), tr("Select a subtitle that has a following subtitle."))
            return

        first = track[index]
        second = track[index + 1]
        merged_text = first.text + " " + second.text
        merged = SubtitleSegment(first.start_ms, second.end_ms, merged_text, style=first.style)

        cmd = MergeCommand(track, index, first, second, merged)
        self._undo_stack.push(cmd)
        self.statusBar().showMessage(f"{tr('Segments')} {index + 1}-{index + 2} {tr('merged')}")

    def _on_batch_shift(self) -> None:
        if not self._project.has_subtitles:
            QMessageBox.warning(self, tr("No Subtitles"), tr("No subtitles to shift."))
            return

        offset, ok = QInputDialog.getInt(
            self, tr("Batch Shift"), tr("Offset (ms, negative=earlier):"), 0, -60000, 60000, 100
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
            self.statusBar().showMessage(tr("Preferences updated"))
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
            QMessageBox.warning(self, tr("Cannot Remove"), tr("At least one track must remain."))
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
            self, tr("Open Video"), last_dir, VIDEO_FILTER
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
        """Start async video loading and conversion."""
        self._cleanup_temp_video()

        # Create worker and thread
        self._video_thread = QThread()
        self._video_worker = VideoLoadWorker(path)
        self._video_worker.moveToThread(self._video_thread)

        # Create progress dialog
        progress = QProgressDialog(f"{tr('Loading')} {path.name}...", tr("Cancel"), 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        # Connect signals
        self._video_worker.progress.connect(progress.setLabelText)
        self._video_worker.finished.connect(self._on_video_prepared)
        self._video_worker.finished.connect(progress.accept)
        self._video_worker.finished.connect(self._video_thread.quit)
        self._video_worker.finished.connect(self._video_worker.deleteLater)
        self._video_worker.finished.connect(self._video_thread.deleteLater)
        
        self._video_worker.error.connect(lambda e: QMessageBox.critical(self, tr("Error"), e))
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
        
        # We don't block here; execution continues, but progress dialog is modal
        progress.exec()

    def _on_video_prepared(self, playback_path: Path, has_audio: bool, source_path: Path) -> None:
        """Finalize video loading after worker completes."""
        # Preserve existing tracks when loading video
        existing_tracks = [t for t in self._project.subtitle_tracks if len(t) > 0]
        existing_overlays = self._project.image_overlay_track

        self._project.reset()
        self._undo_stack.clear()
        
        self._project.video_path = source_path
        
        # If playback path is different (temp file), store it
        if playback_path != source_path:
            self._temp_video_path = playback_path

        # Restore non-empty tracks
        if existing_tracks:
            self._project.subtitle_tracks = existing_tracks
            self._project.active_track_index = 0
        if len(existing_overlays) > 0:
            self._project.image_overlay_track = existing_overlays

        self._project.video_has_audio = has_audio

        self._current_playback_source = str(playback_path)
        self._current_clip_index = 0
        self._player.setSource(QUrl.fromLocalFile(str(playback_path)))
        
        # Set primary video path for timeline thumbnails
        self._timeline.set_primary_video_path(str(source_path))
        self._player.play()

        self._refresh_all_widgets()
        self._refresh_track_selector()

        # Start waveform generation in background
        if self._project.video_has_audio:
            self._start_waveform_generation(source_path)
        else:
            self._timeline.clear_waveform()

        self.setWindowTitle(f"{source_path.name} – {APP_NAME}")
        self.statusBar().showMessage(f"{tr('Loaded')}: {source_path.name}")

        # Start frame cache generation
        self._start_frame_cache_generation()

    def _cleanup_temp_video(self) -> None:
        """Remove previously created temp video file."""
        if self._temp_video_path is not None and self._temp_video_path.is_file():
            self._temp_video_path.unlink(missing_ok=True)
        self._temp_video_path = None

    def _toggle_magnetic_snap(self) -> None:
        """Toggle magnetic snap mode."""
        enabled = self._snap_toggle_btn.isChecked()
        self._timeline.set_magnetic_snap(enabled)
        
    def _toggle_ripple_mode(self) -> None:
        """Toggle ripple edit mode."""
        enabled = self._ripple_toggle_btn.isChecked()
        self._timeline.set_ripple_mode(enabled)

    def _on_track_state_changed(self) -> None:
        """Handle Mute/Lock/Hide state changes from TrackHeaderPanel."""
        # Update timeline appearance
        self._timeline.update()
        
        # Sync player mute and visibility states
        if self._project.video_clip_track:
            self._audio_output.setMuted(self._project.video_clip_track.muted)
            self._video_widget.set_video_hidden(self._project.video_clip_track.hidden)
            
        track = self._project.subtitle_track
        if track:
            self._tts_audio_output.setMuted(track.muted)
            # Force update of subtitle overlay visibility
            pos = self._player.position()
            self._video_widget._update_subtitle(pos)
            self._video_widget._update_image_overlays(pos)
        
        self.statusBar().showMessage(tr("Track states updated"), 2000)

    def _on_duration_changed(self, duration_ms: int) -> None:
        # Skip during source switching — don't overwrite project duration
        # with an external video's duration
        if self._pending_seek_ms is not None:
            return

        # If we already have a multi-source clip track, ignore source duration changes
        # (otherwise switching between A/B sources would keep changing the slider range)
        if self._project.video_clip_track is not None:
            return

        self._project.duration_ms = duration_ms
        # Only update timeline if duration > 0; ignore durationChanged(0)
        # which would overwrite a TTS-derived timeline duration.
        if duration_ms > 0:
            # Initialize clip track for the first video
            self._project.video_clip_track = VideoClipTrack.from_full_video(duration_ms)
            output_dur = self._project.video_clip_track.output_duration_ms
            self._timeline.set_duration(output_dur, has_video=True)
            self._timeline.set_clip_track(self._project.video_clip_track)
            # Enable output time mode on controls
            self._controls.enable_output_time_mode()
            self._controls.set_output_duration(output_dur)

    def _on_generate_subtitles(self) -> None:
        if not self._project.has_video:
            QMessageBox.warning(self, tr("No Video"), tr("Please open a video file first."))
            return

        if not find_ffmpeg():
            QMessageBox.critical(
                self, tr("FFmpeg Missing"),
                tr("FFmpeg is required for subtitle generation but was not found.")
            )
            return

        dialog = WhisperDialog(self._project.video_path, parent=self)
        dialog.segment_ready.connect(self._on_whisper_segment_ready)
        if dialog.exec():
            # If finished successfully, we might want to replace the track or just let the real-time updates stand.
            # However, the dialog only returns the track on finish.
            # Real-time updates push directly to the track.
            # To avoid duplication if we re-apply the full track at the end:
            # We should probably clear the track at start or rely on real-time only?
            # Actually, `dialog.result_track()` returns the full track.
            # If we appended real-time, `self._project.subtitle_track` is already populated.
            # Let's ensure we don't duplicate. We can just use the final result to be safe/atomic,
            # OR rely solely on real-time.
            # Better approach: Real-time adds to the LIVE track. The final result is just a confirmation.
            # But `WhisperDialog` builds its own track locally. It doesn't modify the project track.
            # So `_on_whisper_segment_ready` should take the segment and append it to `self._project.subtitle_track`.
            # And at the end, we might not need to do anything if real-time covered it all.
            # BUT: If user cancels, we might want to keep partials?
            # Let's see: `_on_whisper_segment_ready` will append.
            # If `dialog.exec()` returns Accepted, it means it finished.
            pass
        
        # After dialog closes (finished or cancelled), refresh one last time
        self._refresh_all_widgets()

    def _on_whisper_segment_ready(self, segment: SubtitleSegment) -> None:
        """Handle real-time subtitle segment generation."""
        # Ensure we have a track
        if self._project.subtitle_track is None:
            self._project.subtitle_track = SubtitleTrack()
            self._timeline.set_subtitle_track(self._project.subtitle_track)
        
        # Add segment
        self._project.subtitle_track.add_segment(segment)
        
        # Refresh UI
        # We don't want to do a full expensive refresh every segment if possible,
        # but for now `_refresh_all_widgets` is safe.
        # Maybe just repaint timeline and update subtitle panel?
        self._timeline.update()
        if self._subtitle_panel:
            self._subtitle_panel.refresh()

    def _on_generate_tts(self) -> None:
        """Open TTS dialog to generate speech from script."""
        # Check FFmpeg
        if not find_ffmpeg():
            QMessageBox.critical(
                self,
                tr("FFmpeg Missing"),
                tr("FFmpeg is required for TTS generation but was not found.")
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
                track.name = f"{tr('TTS Track')} {len(self._project.subtitle_tracks)}"
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

                # Set timeline duration BEFORE refreshing widgets so timeline
                # can render segments on the first paint.
                self._ensure_timeline_duration()

                # Refresh UI to show the new track
                self._refresh_all_widgets()

                self.statusBar().showMessage(
                    f"{tr('TTS generated')}: {len(track)} {tr('segments')}"
                )

    def _on_play_tts_audio(self) -> None:
        """Play TTS audio for the current track."""
        # Get current track
        current_track = self._project.subtitle_track

        # Check if track has audio
        if not current_track or not current_track.audio_path:
            QMessageBox.information(
                self,
                tr("No TTS Audio"),
                tr("The current track doesn't have TTS audio.") + "\n\n"
                + tr("Generate TTS audio first (Ctrl+T).")
            )
            return

        # Check if audio file exists
        audio_path = Path(current_track.audio_path)
        if not audio_path.exists():
            QMessageBox.warning(
                self,
                tr("Audio File Not Found"),
                f"{tr('TTS audio file not found')}:\n{audio_path}\n\n"
                f"{tr('It may have been deleted.')}"
            )
            return

        # Stop current TTS playback if any
        if self._tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._tts_player.stop()

        # Play TTS audio
        self._tts_player.setSource(QUrl.fromLocalFile(str(audio_path)))
        self._tts_player.play()

        self.statusBar().showMessage(
            f"{tr('Playing TTS audio')}: {current_track.name}"
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
                tr("No Audio Segments"),
                tr("The current track doesn't have audio segments.") + "\n\n"
                + tr("Generate TTS audio first (Ctrl+T).")
            )
            return

        # Confirm regeneration
        reply = QMessageBox.question(
            self,
            tr("Regenerate Audio?"),
            f"{tr('Regenerate merged audio based on current timeline positions?')}\n\n"
            f"{tr('This will create a new audio file with segments positioned according to the timeline.')}\n\n"
            f"{tr('Segments')}: {len(audio_segments)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # Show progress
            self.statusBar().showMessage(tr("Regenerating audio from timeline..."))
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
            self._ensure_timeline_duration()

            self._refresh_all_widgets()

            # Stop current playback and load new audio
            self._player.pause()
            self._tts_player.stop()

            # Refresh subtitle display with updated timeline positions
            self._video_widget.set_subtitle_track(current_track)
            current_pos = self._player.position()
            self._on_player_position_changed(current_pos)

            self.statusBar().showMessage(
                f"{tr('Audio regenerated')}: {len(audio_segments)} {tr('segments')}, "
                f"{total_duration_ms/1000:.1f}s",
                5000
            )

            QMessageBox.information(
                self,
                tr("Audio Regenerated"),
                f"{tr('Audio has been regenerated successfully!')}\n\n"
                f"{tr('Segments')}: {len(audio_segments)}\n"
                f"{tr('Duration')}: {total_duration_ms/1000:.1f}s\n\n"
                f"{tr('Play to hear the updated audio.')}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                tr("Regeneration Failed"),
                f"{tr('Failed to regenerate audio')}:\n\n{e}"
            )
            self.statusBar().showMessage(tr("Audio regeneration failed"), 5000)

    def _on_toggle_position_edit(self, checked: bool) -> None:
        """Toggle subtitle position editing mode."""
        self._video_widget.set_subtitle_edit_mode(checked)

        if checked:
            self.statusBar().showMessage(
                tr("Edit Mode: Drag subtitle to reposition. Press Ctrl+E again to save.")
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
                        f"{tr('Subtitle position saved')}: ({x}, {y})"
                    )
                    # Mark as edited for autosave
                    self._on_document_edited()
            else:
                self.statusBar().showMessage(tr("Edit Mode OFF"))

    def _apply_subtitle_track(self, track: SubtitleTrack) -> None:
        self._project.subtitle_track = track
        self._undo_stack.clear()
        self._video_widget.set_subtitle_track(track)
        self._subtitle_panel.set_track(track)
        self._timeline.set_track(track)
        self._refresh_track_selector()
        self.statusBar().showMessage(
            f"{tr('Subtitles loaded')}: {len(track)} {tr('segments')}"
        )

    def _on_clear_subtitles(self) -> None:
        self._project.subtitle_track = SubtitleTrack(name=self._project.subtitle_track.name)
        self._undo_stack.clear()
        self._video_widget.set_subtitle_track(None)
        self._subtitle_panel.set_track(None)
        self._timeline.set_track(None)
        self.statusBar().showMessage(tr("Subtitles cleared"))

    def _on_translate_track(self) -> None:
        """Open the translate dialog and process the translation."""
        if not self._project.has_subtitles:
            QMessageBox.warning(self, tr("No Subtitles"), tr("There are no subtitles to translate."))
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
                    self.statusBar().showMessage(f"{tr('Added translated track')}: {translated_track.name}")
                else:
                    # Replace current track
                    self._project.subtitle_track = translated_track
                    self._refresh_all_widgets()
                    self.statusBar().showMessage(tr("Track translated"))

                # Notify autosave
                self._autosave.notify_edit()

    def _on_edit_default_style(self) -> None:
        from src.ui.dialogs.style_dialog import StyleDialog
        dialog = StyleDialog(self._project.default_style, parent=self, title=tr("Default Subtitle Style"))
        if dialog.exec():
            self._project.default_style = dialog.result_style()
            self._video_widget.set_default_style(self._project.default_style)
            self.statusBar().showMessage(tr("Default style updated"))

    def _on_edit_segment_style(self, index: int) -> None:
        if not self._project.has_subtitles or index < 0 or index >= len(self._project.subtitle_track):
            return
        from src.ui.dialogs.style_dialog import StyleDialog
        seg = self._project.subtitle_track[index]
        current_style = seg.style if seg.style is not None else self._project.default_style
        dialog = StyleDialog(current_style, parent=self, title=f"{tr('Style')} - {tr('Segment')} {index + 1}")
        if dialog.exec():
            old_style = seg.style
            new_style = dialog.result_style()
            cmd = EditStyleCommand(self._project.subtitle_track, index, old_style, new_style)
            self._undo_stack.push(cmd)
            self._video_widget.set_default_style(self._project.default_style)
            self.statusBar().showMessage(f"{tr('Style updated')} ({tr('segment')} {index + 1})")

    def _on_import_srt(self, path=None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Import SRT"), "", "SRT Files (*.srt);;All Files (*)"
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
            QMessageBox.critical(self, tr("Import Error"), str(e))

    def _on_import_srt_new_track(self, path: Path) -> None:
        """Import SRT as a new track."""
        try:
            track = import_srt(path)
            self._project.subtitle_tracks.append(track)
            self._refresh_track_selector()
            # Select the new track
            self._track_selector.blockSignals(True)
            self._track_selector.setCurrentIndex(len(self._project.subtitle_tracks) - 1)
            self._track_selector.blockSignals(False)
            self._project.active_track_index = len(self._project.subtitle_tracks) - 1
            self._on_track_changed(self._project.active_track_index)
            
            QMessageBox.information(self, tr("Import Complete"), tr("Subtitle track imported successfully."))
        except Exception as e:
            QMessageBox.critical(self, tr("Import Error"), f"{tr('Failed to import SRT')}: {e}")

    def _on_import_subtitle(self, file_path: str) -> None:
        """Handle subtitle import request from media library."""
        path = Path(file_path)
        if path.suffix.lower() == ".srt":
            self._on_import_srt_new_track(path)
        elif path.suffix.lower() == ".smi":
            self._on_import_smi(path)

    def _on_import_smi(self, path: Path) -> None:
        """Import SMI file as a new track."""
        try:
            track = import_smi(path)
            if not track:
                QMessageBox.warning(self, tr("Import Empty"), tr("No subtitles found in SMI file."))
                return

            self._project.subtitle_tracks.append(track)
            self._refresh_track_selector()
            
            # Select the new track
            new_idx = len(self._project.subtitle_tracks) - 1
            self._track_selector.blockSignals(True)
            self._track_selector.setCurrentIndex(new_idx)
            self._track_selector.blockSignals(False)
            self._project.active_track_index = new_idx
            self._on_track_changed(new_idx)
            
            QMessageBox.information(self, tr("Import Complete"), tr("SMI subtitle track imported successfully."))
        except Exception as e:
            QMessageBox.critical(self, tr("Import Error"), f"{tr('Failed to import SMI')}: {e}")

    def _on_export_srt(self) -> None:
        if not self._project.has_subtitles:
            QMessageBox.warning(self, tr("No Subtitles"), tr("There are no subtitles to export."))
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("Export SRT"), "", "SRT Files (*.srt);;All Files (*)"
        )
        if not path:
            return

        try:
            export_srt(self._project.subtitle_track, Path(path))
            self.statusBar().showMessage(f"{tr('Exported')}: {path}")
        except OSError as e:
            QMessageBox.critical(self, tr("Export Error"), str(e))

    def _on_export_video(self) -> None:
        if not self._project.has_video:
            QMessageBox.warning(self, tr("No Video"), tr("Please open a video file first."))
            return
        if not find_ffmpeg():
            QMessageBox.critical(self, tr("FFmpeg Missing"), tr("FFmpeg is required for video export."))
            return

        from src.ui.dialogs.export_dialog import ExportDialog
        overlay_path = None
        if self._overlay_template:
            overlay_path = Path(self._overlay_template.image_path)
        io_track = self._project.image_overlay_track
        img_overlays = list(io_track.overlays) if len(io_track) > 0 else None
        # Pass video tracks for multi-track export
        video_tracks = list(self._project.video_tracks)
        # Pass text overlays
        text_overlays = list(self._project.text_overlay_track.overlays) if len(self._project.text_overlay_track) > 0 else None

        dialog = ExportDialog(
            self._project.video_path,
            self._project.subtitle_track,
            parent=self,
            video_has_audio=self._project.video_has_audio,
            overlay_path=overlay_path,
            image_overlays=img_overlays,
            video_tracks=video_tracks,
            text_overlays=text_overlays,
        )
        dialog.exec()

    def _on_batch_export(self) -> None:
        if not self._project.has_video:
            QMessageBox.warning(self, tr("No Video"), tr("Please open a video file first."))
            return
        if not find_ffmpeg():
            QMessageBox.critical(self, tr("FFmpeg Missing"), tr("FFmpeg is required for video export."))
            return

        overlay_path = None
        if self._overlay_template:
            overlay_path = Path(self._overlay_template.image_path)
        io_track = self._project.image_overlay_track
        img_overlays = list(io_track.overlays) if len(io_track) > 0 else None
        # Pass text overlays
        text_overlays = list(self._project.text_overlay_track.overlays) if len(self._project.text_overlay_track) > 0 else None

        from src.ui.dialogs.batch_export_dialog import BatchExportDialog
        dialog = BatchExportDialog(
            self._project.video_path,
            self._project.subtitle_track,
            parent=self,
            video_has_audio=self._project.video_has_audio,
            overlay_path=overlay_path,
            image_overlays=img_overlays,
            text_overlays=text_overlays,
        )
        dialog.exec()

    # ------------------------------------------------------------ Templates

    def _on_template_applied(self, template) -> None:
        """Apply an overlay template to the video player."""
        self._overlay_template = template
        self._video_widget.set_overlay(template=template)
        self.statusBar().showMessage(f"{tr('Template applied')}: {template.name}")

    def _on_template_cleared(self) -> None:
        """Remove the overlay template from the video player."""
        self._overlay_template = None
        self._video_widget.clear_overlay()
        self.statusBar().showMessage(tr("Template cleared"))

    def _on_save_project(self) -> None:
        if not self._project.has_video:
            QMessageBox.warning(self, tr("No Video"), tr("Please open a video file first."))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Save Project"), "", "FastMovieMaker Project (*.fmm.json);;All Files (*)"
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
            self.statusBar().showMessage(f"{tr('Project saved')}: {path}")
        except Exception as e:
            QMessageBox.critical(self, tr("Save Error"), str(e))

    def _on_load_project(self, path=None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Load Project"), "", "FastMovieMaker Project (*.fmm.json);;All Files (*)"
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
            self._timeline.set_project(project)
            self._track_headers.set_project(project)

            # Load video if it exists
            if project.video_path and project.video_path.is_file():
                self._current_playback_source = str(project.video_path)
                self._current_clip_index = 0
                self._player.setSource(QUrl.fromLocalFile(str(project.video_path)))
                self._player.play()
                self.setWindowTitle(f"{project.video_path.name} – {APP_NAME}")

            # Refresh UI components
            self._refresh_all_widgets()
            
            # Additional setup for video playback
            if project.video_path and project.video_path.is_file():
                self._current_playback_source = str(project.video_path)
                self._current_clip_index = 0
                self._player.setSource(QUrl.fromLocalFile(str(project.video_path)))
                # Auto-play on load if possible
                self._player.play()
                self.setWindowTitle(f"{project.video_path.name} – {APP_NAME}")

            # Refresh timeline to update display
            self._timeline.refresh()

            # Start frame cache generation
            self._start_frame_cache_generation()

            self._update_recent_menu()
            self.statusBar().showMessage(f"{tr('Project loaded')}: {path}")
        except Exception as e:
            QMessageBox.critical(self, tr("Load Error"), str(e))

    def _on_timeline_seek(self, position_ms: int) -> None:
        if self._project.has_video:
            clip_track = self._project.video_clip_track
            if clip_track:
                result = clip_track.clip_at_timeline(position_ms)
                if result is not None:
                    idx, clip = result
                    self._current_clip_index = idx
                    local_offset = position_ms - clip_track.clip_timeline_start(idx)
                    source_ms = clip.source_in_ms + local_offset
                    target_source_raw = clip.source_path or str(self._project.video_path)
                    target_source = self._resolve_playback_path(target_source_raw)

                    if target_source != self._current_playback_source:
                        self._switch_player_source(target_source, source_ms,
                                                   auto_play=self._play_intent)
                    elif self._pending_seek_ms is not None:
                        # Source is still loading — update pending position
                        self._pending_seek_ms = source_ms
                    else:
                        self._player.setPosition(source_ms)
                        if self._play_intent:
                            self._player.play()
                    # Update timeline playhead and slider
                    self._timeline.set_playhead(position_ms)
                    self._controls.set_output_position(position_ms)
                else:
                    self._player.setPosition(position_ms)
                    self._timeline.set_playhead(position_ms)
                    self._controls.set_output_position(position_ms)
            else:
                self._player.setPosition(position_ms)
                self._timeline.set_playhead(position_ms)
                self._controls.set_output_position(position_ms)
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
        """Handle position change from playback controls slider (output time)."""
        clip_track = self._project.video_clip_track
        if clip_track:
            result = clip_track.clip_at_timeline(position_ms)
            if result is not None:
                idx, clip = result
                self._current_clip_index = idx
                local_offset = position_ms - clip_track.clip_timeline_start(idx)
                source_ms = clip.source_in_ms + local_offset
                target_source_raw = clip.source_path or str(self._project.video_path)
                target_source = self._resolve_playback_path(target_source_raw)
                if target_source != self._current_playback_source:
                    self._switch_player_source(target_source, source_ms,
                                               auto_play=self._play_intent)
                elif self._pending_seek_ms is not None:
                    # Source is still loading — update pending position
                    self._pending_seek_ms = source_ms
                else:
                    self._player.setPosition(source_ms)
                    if self._play_intent:
                        self._player.play()
            self._timeline.set_playhead(position_ms)
            self._controls.set_output_position(position_ms)
        else:
            self._player.setPosition(position_ms)
            self._timeline.set_playhead(position_ms)
        self._sync_tts_playback()

    def _sync_clip_index_from_position(self) -> None:
        """Recalculate current track and clip index from timeline position."""
        res = self._get_top_clip_at(self._timeline.get_playhead())
        if res:
            self._current_track_index, self._current_clip_index, _ = res

    def _get_top_clip_at(self, timeline_ms: int) -> tuple[int, int, VideoClip] | None:
        """Find the clip on the highest visible track at the given timeline position."""
        if not self._project:
            return None
        # From top to bottom (highest track index usually rendered on top)
        for v_idx in reversed(range(len(self._project.video_tracks))):
            vt = self._project.video_tracks[v_idx]
            if vt.hidden:
                continue
            res = vt.clip_at_timeline(timeline_ms)
            if res:
                return v_idx, res[0], res[1]
        return None

    def _on_player_position_changed(self, position_ms: int) -> None:
        """Handle video player position change (source_ms from QMediaPlayer)."""
        if not self._project.has_video:
            return

        if self._pending_seek_ms is not None:
            return

        # Use current track/clip
        if not self._project.video_tracks:
            return
            
        t_idx = self._current_track_index
        if t_idx >= len(self._project.video_tracks):
            t_idx = 0
            self._current_track_index = 0
            
        vt = self._project.video_tracks[t_idx]
        clips = vt.clips
        idx = self._current_clip_index

        if not (0 <= idx < len(clips)):
            self._sync_clip_index_from_position()
            return

        current_clip = clips[idx]

        # Sync timeline playhead if position is within current clip
        # Using tolerance for boundary timing
        if current_clip.source_in_ms - 100 <= position_ms <= current_clip.source_out_ms + 100:
            clip_start = vt.clip_timeline_start(idx)
            # Duration in timeline is (source_out - source_in) / speed
            # So local timeline offset is (source_pos - source_in) / speed
            local_offset = (position_ms - current_clip.source_in_ms) / current_clip.speed
            timeline_ms = int(clip_start + local_offset)
            
            self._timeline.set_playhead(timeline_ms)
            self._controls.set_output_position(timeline_ms)
            self._video_widget._update_subtitle(timeline_ms)
            self._sync_tts_playback()
        
        # Check transition to next clip or another track
        if position_ms >= current_clip.source_out_ms - 30:
            # Re-sync to find what should be playing next according to z-order
            self._sync_clip_index_from_position()
            new_v_idx = self._current_track_index
            new_c_idx = self._current_clip_index
            
            new_vt = self._project.video_tracks[new_v_idx]
            new_clip = new_vt.clips[new_c_idx]
            
            next_start = new_vt.clip_timeline_start(new_c_idx)
            self._timeline.set_playhead(next_start)
            
            target_source = new_clip.source_path or str(self._project.video_path)
            playback_path = self._resolve_playback_path(target_source)
            
            if playback_path != self._current_playback_source:
                self._switch_player_source(playback_path, new_clip.source_in_ms, auto_play=self._play_intent)
            else:
                self._player.setPosition(new_clip.source_in_ms)
                if self._play_intent:
                    self._player.play()

    def _resolve_playback_path(self, source_path: str | None) -> str:
        """Resolve playback path, using temp converted file if available.

        If source_path is None or matches project video path, returns
        temp playback path (e.g. converted MP4) if it exists.
        """
        # 1. Handle main video (source_path is None or matches project path)
        is_main_video = False
        if source_path is None:
            is_main_video = True
        elif self._project.video_path:
            # Check string equality first, then resolve if needed
            if source_path == str(self._project.video_path):
                is_main_video = True
            elif Path(source_path).resolve() == self._project.video_path.resolve():
                is_main_video = True

        if is_main_video:
            if self._temp_video_path and self._temp_video_path.is_file():
                return str(self._temp_video_path)
            return str(self._project.video_path) if self._project.video_path else ""

        # 2. Return original path for external videos (conversion not yet supported for external items)
        return source_path or ""

    def _switch_player_source(self, source_path: str, seek_ms: int,
                              auto_play: bool = False) -> None:
        """Switch QMediaPlayer to a different source video file."""
        # Check if we need to resolve the path (though caller should have resolved it,
        # it's safe to check/resolve again or trust caller. Better trust caller to avoid redundant checks,
        # but let's ensure we use the resolved path).
        # Actually, let's assume raw path is passed and we resolve it here?
        # No, logic in _on_timeline_seek calculates offsets based on clip.
        # Let's rely on caller to pass the correct playback path?
        # Wait, if we pass resolved path here, it works.

        # Show cached frame immediately while QMediaPlayer loads
        if self._frame_cache_service:
            from PySide6.QtGui import QPixmap
            # Use threshold to avoid showing a frame from a completely different scene
            frame_path = self._frame_cache_service.get_nearest_frame(
                source_path, seek_ms, threshold_ms=2000
            )
            if frame_path:
                pixmap = QPixmap(str(frame_path))
                if not pixmap.isNull():
                    self._video_widget.show_cached_frame(pixmap)
                    self._showing_cached_frame = True

        # Cancel any pending render-pause timer from a previous source switch
        self._render_pause_timer.stop()

        self._current_playback_source = source_path
        self._pending_seek_ms = seek_ms
        # 누적된 auto_play 요청이 있으면 유지 (연속 스크럽 중 재생 재개 보장)
        self._pending_auto_play = self._pending_auto_play or auto_play or self._play_intent
        # Watchdog: clear pending seek if backend never emits Loaded/Buffered
        self._pending_seek_timer.start()
        self._player.setSource(QUrl.fromLocalFile(source_path))
        # 일부 백엔드는 setSource 후 play를 호출해야 로딩/재생이 진행됨
        if self._pending_auto_play:
            self._player.play()

    def _on_media_status_changed(self, status) -> None:
        """Handle media status change — seek to pending position after source switch.

        일부 환경(특히 여러 영상 소스를 빠르게 전환할 때)에서는 상태가
        `BufferedMedia`로만 올라오고 `LoadedMedia`를 건너뛰는 경우가 있어
        `_pending_seek_ms`가 해제되지 않아 재생이 멈출 수 있다. 두 상태 모두에서
        펜딩 시크를 처리하도록 한다.
        """
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        ready_status = (_QMP.MediaStatus.LoadedMedia, _QMP.MediaStatus.BufferedMedia)
        if status in ready_status and self._pending_seek_ms is not None:
            seek_ms = self._pending_seek_ms
            auto_play = self._pending_auto_play or self._play_intent
            self._pending_seek_ms = None
            self._pending_auto_play = False
            self._pending_seek_timer.stop()
            self._player.setPosition(seek_ms)
            if auto_play:
                self._player.play()
            else:
                # play+pause to force video frame render in StoppedState
                self._player.play()
                self._render_pause_timer.start()
            # Hide cached frame now that live video is ready
            if self._showing_cached_frame:
                self._video_widget.hide_cached_frame()
                self._showing_cached_frame = False
        elif status == _QMP.MediaStatus.EndOfMedia and self._pending_seek_ms is None:
            # Some backends stop at clip boundary without a final position update.
            # Advance to next clip explicitly to keep playback continuous.
            clip_track = self._project.video_clip_track
            if not clip_track:
                return
            idx = self._current_clip_index
            if idx + 1 >= len(clip_track.clips):
                return
            next_clip = clip_track.clips[idx + 1]
            self._current_clip_index = idx + 1
            next_source = next_clip.source_path or str(self._project.video_path)
            if next_source != self._current_playback_source:
                self._switch_player_source(
                    next_source, next_clip.source_in_ms,
                    auto_play=self._play_intent,
                )
            else:
                self._player.setPosition(next_clip.source_in_ms)
                if self._play_intent:
                    self._player.play()
        elif status == _QMP.MediaStatus.InvalidMedia and self._pending_seek_ms is not None:
            # Source failed to load — clear pending state so playback isn't blocked
            self._pending_seek_ms = None
            self._pending_auto_play = False
            self._pending_seek_timer.stop()

    def _on_tts_position_changed(self, position_ms: int) -> None:
        """Handle TTS player position change."""
        track = self._project.subtitle_track
        if track and track.audio_path:
            timeline_pos = track.audio_start_ms + position_ms

            # Apply per-segment volume multiplied by slider volume
            slider_vol = self._controls.get_tts_volume()
            seg = track.segment_at(timeline_pos)
            if seg:
                self._tts_audio_output.setVolume(seg.volume * slider_vol)
            else:
                self._tts_audio_output.setVolume(slider_vol)

            # If no video, use TTS position for timeline
            if not self._project.has_video:
                self._timeline.set_playhead(timeline_pos)
                # Update subtitle display based on timeline position
                self._video_widget._update_subtitle(timeline_pos)

    def _on_player_error(self, error, error_string: str) -> None:
        # Clear pending seek state so position updates are not blocked forever
        self._pending_seek_ms = None
        self._pending_auto_play = False
        self.statusBar().showMessage(f"{tr('Player error')}: {error_string}")

    # ------------------------------------------------------------------ Snap
    def _toggle_magnetic_snap(self) -> None:
        """Toggle magnetic snap state."""
        enabled = self._timeline.toggle_magnetic_snap()
        self._snap_toggle_btn.setChecked(enabled)
        state = tr("Enabled") if enabled else tr("Disabled")
        self.statusBar().showMessage(f"{tr('Magnetic Snap')}: {state}", 2000)

    # -------------------------------------------------------- Video clip editing

    def _on_clip_selected(self, track_index: int, clip_index: int) -> None:
        """Handle clip selection from timeline."""
        self._timeline.select_clip(track_index, clip_index)

    def _on_split_clip(self, timeline_ms: int) -> None:
        """Split clip at the given timeline position."""
        res = self._get_top_clip_at(timeline_ms)
        if not res:
            self.statusBar().showMessage(tr("No video clips to split"), 3000)
            return

        v_idx, clip_idx, clip = res
        vt = self._project.video_tracks[v_idx]

        # Calculate split point in source time
        offset = sum(c.duration_ms for c in vt.clips[:clip_idx])
        local_ms = timeline_ms - offset
        split_source = clip.source_in_ms + int(local_ms * clip.speed)

        # Don't split at very edges (100ms margin for safety)
        if split_source <= clip.source_in_ms + 100 or split_source >= clip.source_out_ms - 100:
            self.statusBar().showMessage(tr("Cannot split: too close to clip edge"), 3000)
            return

        # Pause playback during structural change
        was_playing = (self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        if was_playing:
            self._player.pause()

        from src.models.video_clip import VideoClip
        original = clip
        first = VideoClip(clip.source_in_ms, split_source, source_path=clip.source_path, speed=clip.speed)
        second = VideoClip(split_source, clip.source_out_ms, source_path=clip.source_path, speed=clip.speed)

        cmd = SplitClipCommand(self._project, v_idx, clip_idx, original, first, second)
        self._undo_stack.push(cmd)
        
        self._refresh_all_widgets()
        self._sync_clip_index_from_position()
        self._timeline.select_clip(v_idx, clip_idx + 1)
        
        if was_playing:
            self._player.play()
        
        self.statusBar().showMessage(f"{tr('Split clip')} {clip_idx + 1} at {timeline_ms}ms", 3000)

    def _on_delete_clip(self, track_index: int, clip_index: int) -> None:
        """Delete a video clip with subtitle ripple."""
        if not self._project or track_index >= len(self._project.video_tracks):
            return
        vt = self._project.video_tracks[track_index]
        if clip_index < 0 or clip_index >= len(vt.clips):
            return
            
        if len(vt.clips) <= 1 and len(self._project.video_tracks) == 1:
            self.statusBar().showMessage(tr("Cannot delete the last clip"), 3000)
            return

        clip = vt.clips[clip_index]
        clip_start_tl = sum(c.duration_ms for c in vt.clips[:clip_index])
        clip_end_tl = clip_start_tl + clip.duration_ms

        # Stop playback before deleting
        self._player.pause()

        sub_track = self._project.subtitle_track
        overlay_track = self._project.image_overlay_track
        
        cmd = DeleteClipCommand(
            self._project, track_index, clip_index, clip, sub_track, overlay_track, 
            clip_start_tl, clip_end_tl,
            ripple=self._timeline.is_ripple_mode()
        )
        self._undo_stack.push(cmd)
        self._timeline.select_clip(-1, -1)

        # Reset player state after deletion
        self._current_clip_index = -1
        self._current_playback_source = None

        # Move playhead to safe position (start of first remaining clip or 0)
        safe_pos = 0
        if len(vt.clips) > 0:
            # If deleted clip was before current position, stay at adjusted position
            # Otherwise move to start of next clip or beginning
            if clip_index == 0:
                safe_pos = 0
            elif clip_index < len(vt.clips):
                safe_pos = sum(c.duration_ms for c in vt.clips[:clip_index])
            else:
                safe_pos = sum(c.duration_ms for c in vt.clips[:clip_index-1])

        self._timeline.set_playhead(safe_pos)
        self._controls.set_output_position(safe_pos)

        # Seek to first remaining clip
        if len(vt.clips) > 0:
            first_clip = vt.clips[0]
            first_source = first_clip.source_path or str(self._project.video_path)
            if first_source != self._current_playback_source:
                self._switch_player_source(first_source, first_clip.source_in_ms, auto_play=False)
            else:
                self._player.setPosition(first_clip.source_in_ms)
            self._current_clip_index = 0

        self._refresh_all_widgets()
        self.statusBar().showMessage(f"{tr('Deleted clip')} {clip_index + 1}", 3000)

    def _on_clip_trimmed(self, track_index: int, clip_index: int, new_source_in: int, new_source_out: int) -> None:
        """Handle clip trim from timeline drag."""
        if not self._project or track_index >= len(self._project.video_tracks):
            return
        vt = self._project.video_tracks[track_index]
        if clip_index < 0 or clip_index >= len(vt.clips):
            return

        clip = vt.clips[clip_index]
        old_in = clip.source_in_ms
        old_out = clip.source_out_ms

        sub_track = self._project.subtitle_track
        overlay_track = self._project.image_overlay_track
        cmd = TrimClipCommand(
            self._project, track_index, clip_index, old_in, old_out, new_source_in, new_source_out,
            sub_track, overlay_track,
            ripple=self._timeline.is_ripple_mode()
        )
        self._undo_stack.push(cmd)
        self._refresh_all_widgets()

    def _on_edit_clip_speed(self, track_index: int, clip_index: int) -> None:
        """클립 재생 속도 변경 다이얼로그 표시 및 명령 실행."""
        if not self._project or track_index >= len(self._project.video_tracks):
            return
        vt = self._project.video_tracks[track_index]
        if clip_index < 0 or clip_index >= len(vt.clips):
            return

        clip = vt.clips[clip_index]
        old_speed = clip.speed

        speed, ok = QInputDialog.getDouble(
            self, tr("Clip Speed"), tr("Speed (0.25x - 4.0x):"),
            old_speed, 0.25, 4.0, 2
        )
        if ok and speed != old_speed:
            sub_track = self._project.subtitle_track
            overlay_track = self._project.image_overlay_track
            cmd = EditSpeedCommand(
                self._project, track_index, clip_index, old_speed, speed,
                sub_track, overlay_track,
                ripple=self._timeline.is_ripple_mode()
            )
            self._undo_stack.push(cmd)
            self._refresh_all_widgets()

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
                tr("Screenshot Failed"),
                f"{tr('Failed to capture screenshot')}:\n{e}"
            )
            print(f"❌ Screenshot error: {e}")

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            f"{tr('About')} {APP_NAME}",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            f"{tr('Video subtitle editor with Whisper-based automatic subtitle generation.')}",
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

                    self.statusBar().showMessage(tr("Project recovered successfully"))
                except Exception as e:
                    QMessageBox.critical(self, tr("Recovery Error"), str(e))

            # Clean up recovery files whether restored or discarded
            self._autosave.cleanup_recovery_files()

    def _update_recent_menu(self) -> None:
        """Update the Recent Projects menu with latest entries."""
        self._recent_menu.clear()

        recent_files = self._autosave.get_recent_files()
        if not recent_files:
            no_recent = QAction(tr("No Recent Projects"), self)
            no_recent.setEnabled(False)
            self._recent_menu.addAction(no_recent)
            return

        for i, path in enumerate(recent_files):
            action = QAction(f"{i+1}. {path.name}", self)
            action.setData(str(path))
            action.triggered.connect(self._on_open_recent)
            self._recent_menu.addAction(action)

        self._recent_menu.addSeparator()
        clear_action = QAction(tr("Clear Recent Projects"), self)
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
                    self, tr("File Not Found"),
                    f"{tr('The file')} {path} {tr('no longer exists.')}"
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
        self.statusBar().showMessage(f"{tr('Autosaved')}: {path.name}", 2000)

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
                    self, tr("Import SRT"),
                    tr("Do you want to import this SRT file as a new track?"),
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
        self._stop_frame_cache_generation()
        if self._frame_cache_service:
            self._frame_cache_service.cleanup()
        self._cleanup_temp_video()
        # Final save before closing
        self._autosave.save_now()
        super().closeEvent(event)

    # ------------------------------------------------ Waveform generation

    def _on_render_pause(self) -> None:
        """Pause player after play+pause render trick (cancellable timer callback)."""
        if self._pending_seek_ms is None:
            self._player.pause()

    def _on_pending_seek_timeout(self) -> None:
        """Fallback when backend never emits Loaded/Buffered after setSource.

        Observed during rapid scrubs across multiple sources; ensures playback
        isn't left stuck waiting for _pending_seek_ms to clear.
        """
        if self._pending_seek_ms is None:
            return
        seek_ms = self._pending_seek_ms
        auto_play = self._pending_auto_play or self._play_intent
        self._pending_seek_ms = None
        self._pending_auto_play = False
        self._player.setPosition(seek_ms)
        if auto_play:
            self._player.play()
        else:
            self._player.play()
            self._render_pause_timer.start()

    @Slot(str)
    def _on_worker_status(self, msg: str) -> None:
        """Show worker status message on status bar (thread-safe slot)."""
        self.statusBar().showMessage(msg, 3000)

    def _start_waveform_generation(self, video_path: Path) -> None:
        """Start background waveform peak computation."""
        self._stop_waveform_generation()
        self._timeline.clear_waveform()

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
        """Handle completed waveform computation."""
        self._timeline.set_waveform(waveform_data)
        self.statusBar().showMessage(tr("Waveform loaded"), 3000)

    def _on_waveform_error(self, message: str) -> None:
        """Handle waveform computation error (non-fatal)."""
        print(f"Warning: Waveform generation failed: {message}")
        self.statusBar().showMessage(tr("Waveform unavailable"), 3000)

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

    # ------------------------------------------------ Frame cache generation

    def _start_frame_cache_generation(self) -> None:
        """Start background frame cache extraction for all video sources."""
        self._stop_frame_cache_generation()

        # Collect all unique source paths and durations
        source_paths: list[str] = []
        durations: dict[str, int] = {}

        if self._project.video_path:
            primary = str(self._project.video_path)
            source_paths.append(primary)
            durations[primary] = self._project.duration_ms

        clip_track = self._project.video_clip_track
        if clip_track:
            for sp in clip_track.unique_source_paths():
                if sp not in source_paths:
                    source_paths.append(sp)
                    from src.services.video_probe import probe_video
                    info = probe_video(sp)
                    durations[sp] = info.duration_ms

        if not source_paths:
            return

        # Create or reuse cache service
        if self._frame_cache_service is None:
            self._frame_cache_service = FrameCacheService()
        self._frame_cache_service.initialize()

        # Skip already-cached sources
        uncached = [
            sp for sp in source_paths
            if not self._frame_cache_service.is_cached(sp)
        ]
        if not uncached:
            return

        self._frame_cache_thread = QThread()
        self._frame_cache_worker = FrameCacheWorker(
            uncached, durations, self._frame_cache_service,
        )
        self._frame_cache_worker.moveToThread(self._frame_cache_thread)

        self._frame_cache_thread.started.connect(self._frame_cache_worker.run)
        self._frame_cache_worker.status_update.connect(self._on_worker_status)
        self._frame_cache_worker.finished.connect(self._on_frame_cache_finished)
        self._frame_cache_worker.error.connect(self._on_frame_cache_error)
        self._frame_cache_worker.finished.connect(self._cleanup_frame_cache_thread)
        self._frame_cache_worker.error.connect(self._cleanup_frame_cache_thread)

        self._frame_cache_thread.start()

    def _on_frame_cache_finished(self, cache_service) -> None:
        self.statusBar().showMessage(tr("Frame cache ready"), 3000)

    def _on_frame_cache_error(self, message: str) -> None:
        print(f"Warning: Frame cache generation failed: {message}")
        self.statusBar().showMessage(tr("Frame cache unavailable"), 3000)

    def _stop_frame_cache_generation(self) -> None:
        if self._frame_cache_worker:
            self._frame_cache_worker.cancel()
        self._cleanup_frame_cache_thread()

    def _cleanup_frame_cache_thread(self) -> None:
        if self._frame_cache_thread and self._frame_cache_thread.isRunning():
            self._frame_cache_thread.quit()
            self._frame_cache_thread.wait(5000)
        self._frame_cache_thread = None
        self._frame_cache_worker = None

    def _on_transition_requested(self, track_idx: int, clip_idx: int) -> None:
        """Show transition dialog and apply effect."""
        if not self._project:
            return
        vt = self._project.video_tracks[track_idx]
        if clip_idx < 0 or clip_idx >= len(vt.clips):
            return
        clip = vt.clips[clip_idx]

        from src.models.video_clip import TransitionInfo

        initial_type = clip.transition_out.type if clip.transition_out else "fade"
        initial_dur = clip.transition_out.duration_ms if clip.transition_out else 500

        dialog = TransitionDialog(self, initial_type, initial_dur)
        if dialog.exec():
            trans_type, trans_dur = dialog.get_data()
            new_info = TransitionInfo(type=trans_type, duration_ms=trans_dur)

            # Ripple mode from toolbar button
            ripple = self._ripple_toggle_btn.isChecked()

            command = EditTransitionCommand(self._project, track_idx, clip_idx, new_info, ripple=ripple)
            self._undo_stack.push(command)

            # Update project duration (if rippled)
            self._project.duration_ms = self._project.video_clip_track.output_duration_ms
            self._timeline.set_duration(self._project.duration_ms)
            self._refresh_all_widgets()

    def _on_clip_volume_requested(self, track_idx: int, clip_idx: int) -> None:
        """Show volume adjustment dialog for a video clip."""
        if not self._project:
            return
        from src.ui.dialogs.clip_volume_dialog import ClipVolumeDialog
        from src.ui.commands import EditClipVolumeCommand
        
        vt = self._project.video_tracks[track_idx]
        clip = vt.clips[clip_idx]
        
        dialog = ClipVolumeDialog(self, clip.volume)
        if dialog.exec():
            new_vol = dialog.get_volume()
            if new_vol != clip.volume:
                cmd = EditClipVolumeCommand(clip, clip.volume, new_vol)
                self._undo_stack.push(cmd)
                self._on_document_edited()
                # 썸네일이나 타임라인 레이아웃에 영향은 없으므로 refresh만 호출
                self._refresh_all_widgets()
