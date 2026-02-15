"""Main application window.

Controller 패턴으로 리팩토링됨.
실제 비즈니스 로직은 src/ui/controllers/ 에 분리되어 있고,
MainWindow는 초기화 + 시그널 배선 + UI 구성만 담당한다.
"""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut, QUndoStack
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.models.project import ProjectState
from src.services.autosave import AutoSaveManager
from src.ui.controllers.app_context import AppContext
from src.ui.controllers.clip_controller import ClipController
from src.ui.controllers.media_controller import MediaController
from src.ui.controllers.overlay_controller import OverlayController
from src.ui.controllers.playback_controller import PlaybackController
from src.ui.controllers.project_controller import ProjectController
from src.ui.controllers.subtitle_controller import SubtitleController
from src.ui.dialogs.preferences_dialog import PreferencesDialog
from src.ui.media_library_panel import MediaLibraryPanel
from src.ui.templates_panel import TemplatesPanel
from src.ui.playback_controls import PlaybackControls
from src.ui.subtitle_panel import SubtitlePanel
from src.ui.timeline_widget import TimelineWidget
from src.ui.track_header_panel import TrackHeaderPanel
from src.ui.track_selector import TrackSelector
from src.ui.video_player_widget import VideoPlayerWidget
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
        self._timeline.set_waveform_service(self._waveform_service)
        self._track_headers = TrackHeaderPanel()
        self._track_headers.state_changed.connect(self._on_track_state_changed)

        # Timeline container
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
        self._snap_toggle_btn.setChecked(True)
        self._snap_toggle_btn.setFixedWidth(50)
        self._snap_toggle_btn.setStyleSheet(btn_style)
        self._snap_toggle_btn.setToolTip(tr("Toggle Magnetic Snap (S)"))
        self._snap_toggle_btn.clicked.connect(self._toggle_magnetic_snap)

        self._zoom_fit_btn = QPushButton(tr("Fit"))
        self._zoom_fit_btn.setFixedWidth(36)
        self._zoom_fit_btn.setStyleSheet(btn_style)
        self._zoom_fit_btn.setToolTip(tr("Fit entire timeline (Ctrl+0)"))
        self._zoom_fit_btn.clicked.connect(self._timeline.zoom_fit)

        self._ripple_toggle_btn = QPushButton("Ripple")
        self._ripple_toggle_btn.setCheckable(True)
        self._ripple_toggle_btn.setChecked(False)
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

    # ------------------------------------------------------------------ Menu

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu(tr("&File"))

        open_action = QAction(tr("&Open Video..."), self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._media.on_open_video)
        file_menu.addAction(open_action)

        import_srt_action = QAction(tr("&Import SRT..."), self)
        import_srt_action.setShortcut(QKeySequence("Ctrl+I"))
        import_srt_action.triggered.connect(self._subtitle_ctrl.on_import_srt)
        file_menu.addAction(import_srt_action)

        import_srt_track_action = QAction(tr("Import SRT to &New Track..."), self)
        import_srt_track_action.triggered.connect(self._subtitle_ctrl.on_import_srt_new_track)
        file_menu.addAction(import_srt_track_action)

        file_menu.addSeparator()

        export_action = QAction(tr("&Export SRT..."), self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._subtitle_ctrl.on_export_srt)
        file_menu.addAction(export_action)

        export_video_action = QAction(tr("Export &Video..."), self)
        export_video_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        export_video_action.triggered.connect(self._project_ctrl.on_export_video)
        file_menu.addAction(export_video_action)

        batch_export_action = QAction(tr("&Batch Export..."), self)
        batch_export_action.triggered.connect(self._project_ctrl.on_batch_export)
        file_menu.addAction(batch_export_action)

        file_menu.addSeparator()

        save_action = QAction(tr("&Save Project..."), self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._project_ctrl.on_save_project)
        file_menu.addAction(save_action)

        load_action = QAction(tr("&Load Project..."), self)
        load_action.setShortcut(QKeySequence("Ctrl+L"))
        load_action.triggered.connect(self._project_ctrl.on_load_project)
        file_menu.addAction(load_action)

        self._recent_menu = QMenu(tr("Recent &Projects"), self)
        file_menu.addMenu(self._recent_menu)
        self._project_ctrl.update_recent_menu()

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
        split_action.triggered.connect(self._subtitle_ctrl.on_split_subtitle)
        edit_menu.addAction(split_action)
        merge_action = QAction(tr("&Merge Subtitles"), self)
        merge_action.triggered.connect(self._subtitle_ctrl.on_merge_subtitles)
        edit_menu.addAction(merge_action)
        edit_menu.addSeparator()

        add_text_overlay_action = QAction(tr("Add &Text Overlay"), self)
        add_text_overlay_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        add_text_overlay_action.triggered.connect(self._overlay.on_add_text_overlay)
        edit_menu.addAction(add_text_overlay_action)
        edit_menu.addSeparator()

        batch_shift_action = QAction(tr("&Batch Shift Timing..."), self)
        batch_shift_action.triggered.connect(self._subtitle_ctrl.on_batch_shift)
        edit_menu.addAction(batch_shift_action)
        edit_menu.addSeparator()

        jump_frame_action = QAction(tr("&Jump to Frame..."), self)
        jump_frame_action.setShortcut(QKeySequence("Ctrl+J"))
        jump_frame_action.triggered.connect(self._playback.on_jump_to_frame)
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
        gen_action.triggered.connect(self._subtitle_ctrl.on_generate_subtitles)
        sub_menu.addAction(gen_action)

        gen_timeline_action = QAction(tr("Generate from &Edited Timeline..."), self)
        gen_timeline_action.setShortcut(QKeySequence("Ctrl+Shift+G"))
        gen_timeline_action.triggered.connect(self._subtitle_ctrl.on_generate_subtitles_from_timeline)
        sub_menu.addAction(gen_timeline_action)

        tts_action = QAction(tr("Generate &Speech (TTS)..."), self)
        tts_action.setShortcut(QKeySequence("Ctrl+T"))
        tts_action.triggered.connect(self._subtitle_ctrl.on_generate_tts)
        sub_menu.addAction(tts_action)

        play_tts_action = QAction(tr("&Play TTS Audio"), self)
        play_tts_action.setShortcut(QKeySequence("Ctrl+P"))
        play_tts_action.triggered.connect(self._subtitle_ctrl.on_play_tts_audio)
        sub_menu.addAction(play_tts_action)

        regen_audio_action = QAction(tr("&Regenerate Audio from Timeline"), self)
        regen_audio_action.setShortcut(QKeySequence("Ctrl+R"))
        regen_audio_action.triggered.connect(self._subtitle_ctrl.on_regenerate_audio)
        sub_menu.addAction(regen_audio_action)

        clear_action = QAction(tr("&Clear Subtitles"), self)
        clear_action.triggered.connect(self._subtitle_ctrl.on_clear_subtitles)
        sub_menu.addAction(clear_action)
        sub_menu.addSeparator()

        translate_action = QAction(tr("&Translate Track..."), self)
        translate_action.triggered.connect(self._subtitle_ctrl.on_translate_track)
        sub_menu.addAction(translate_action)
        sub_menu.addSeparator()

        style_action = QAction(tr("Default &Style..."), self)
        style_action.triggered.connect(self._subtitle_ctrl.on_edit_default_style)
        sub_menu.addAction(style_action)
        sub_menu.addSeparator()

        edit_position_action = QAction(tr("Edit Subtitle &Position"), self)
        edit_position_action.setCheckable(True)
        edit_position_action.setShortcut(QKeySequence("Ctrl+E"))
        edit_position_action.triggered.connect(self._subtitle_ctrl.on_toggle_position_edit)
        sub_menu.addAction(edit_position_action)
        self._edit_position_action = edit_position_action

        # View menu
        view_menu = menubar.addMenu(tr("&View"))
        self._proxy_action = QAction(tr("Use &Proxy Media"), self)
        self._proxy_action.setCheckable(True)
        self._proxy_action.setChecked(False)
        self._proxy_action.triggered.connect(self._media.toggle_proxies)
        view_menu.addAction(self._proxy_action)

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

    # ---------------------------------------------------------------- Shortcuts

    def _setup_shortcuts(self) -> None:
        sc_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        sc_space.activated.connect(self._playback.toggle_play_pause)

        sc_left = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        sc_left.activated.connect(lambda: self._playback.seek_relative(-5000))
        sc_right = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        sc_right.activated.connect(lambda: self._playback.seek_relative(5000))

        sc_frame_left = QShortcut(QKeySequence("Shift+Left"), self)
        sc_frame_left.activated.connect(lambda: self._playback.seek_frame_relative(-1))
        sc_frame_right = QShortcut(QKeySequence("Shift+Right"), self)
        sc_frame_right.activated.connect(lambda: self._playback.seek_frame_relative(1))

        sc_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        sc_del.activated.connect(self._subtitle_ctrl.on_delete_selected)

        sc_split = QShortcut(QKeySequence("Ctrl+B"), self)
        sc_split.activated.connect(lambda: self._clip.on_split_clip(self._timeline._playhead_ms))

        sc_zoom_in = QShortcut(QKeySequence("Ctrl+="), self)
        sc_zoom_in.activated.connect(self._timeline.zoom_in)
        sc_zoom_in2 = QShortcut(QKeySequence("Ctrl++"), self)
        sc_zoom_in2.activated.connect(self._timeline.zoom_in)
        sc_zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        sc_zoom_out.activated.connect(self._timeline.zoom_out)
        sc_zoom_fit = QShortcut(QKeySequence("Ctrl+0"), self)
        sc_zoom_fit.activated.connect(self._timeline.zoom_fit)

        sc_snap = QShortcut(QKeySequence(Qt.Key.Key_S), self)
        sc_snap.activated.connect(self._toggle_magnetic_snap)

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
        self._timeline.transition_requested.connect(self._clip.on_transition_requested)
        self._timeline.clip_volume_requested.connect(self._clip.on_clip_volume_requested)

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

        # Timeline drag-and-drop
        self._timeline.image_file_dropped.connect(self._overlay.on_image_file_dropped)
        self._timeline.video_file_dropped.connect(self._clip.on_video_file_dropped)
        self._timeline.audio_file_dropped.connect(self._media.on_audio_file_dropped)
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
        self._video_widget.set_subtitle_track(track if len(track) > 0 else None)
        self._subtitle_panel.set_track(track if len(track) > 0 else None)
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

    def _on_preferences(self) -> None:
        dialog = PreferencesDialog(self)
        if dialog.exec():
            self.statusBar().showMessage(tr("Preferences updated"))

    def _toggle_magnetic_snap(self) -> None:
        enabled = self._snap_toggle_btn.isChecked()
        self._timeline.set_magnetic_snap(enabled)

    def _toggle_ripple_mode(self) -> None:
        enabled = self._ripple_toggle_btn.isChecked()
        self._timeline.set_ripple_mode(enabled)

    def _on_track_state_changed(self) -> None:
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
        self.statusBar().showMessage(tr("Track states updated"), 2000)

    def _on_template_applied(self, template) -> None:
        self._overlay_template = template
        self._video_widget.set_overlay(template=template)
        self.statusBar().showMessage(f"{tr('Template applied')}: {template.name}")

    def _on_template_cleared(self) -> None:
        self._overlay_template = None
        self._video_widget.clear_overlay()
        self.statusBar().showMessage(tr("Template cleared"))

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
        settings = QSettings()
        settings.setValue("window_geometry", self.saveGeometry())
        settings.setValue("window_state", self.saveState())
        self._player.stop()
        self._media.cleanup()
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
