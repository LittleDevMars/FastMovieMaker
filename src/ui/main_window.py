"""Main application window."""

from pathlib import Path

from PySide6.QtCore import QSettings, QUrl, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.models.project import ProjectState
from src.models.subtitle import SubtitleTrack
from src.services.subtitle_exporter import export_srt
from src.ui.playback_controls import PlaybackControls
from src.ui.subtitle_panel import SubtitlePanel
from src.ui.timeline_widget import TimelineWidget
from src.ui.video_player_widget import VideoPlayerWidget
from src.ui.dialogs.whisper_dialog import WhisperDialog
from src.utils.config import APP_NAME, APP_VERSION, VIDEO_FILTER, find_ffmpeg


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1100, 700)

        self._project = ProjectState()

        # Media stack
        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)

        self._build_ui()
        self._build_menu()
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

        # Subtitle panel (right side)
        self._subtitle_panel = SubtitlePanel()

        # Top splitter: video | subtitle panel
        self._top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._top_splitter.addWidget(self._video_widget)
        self._top_splitter.addWidget(self._subtitle_panel)
        self._top_splitter.setStretchFactor(0, 3)
        self._top_splitter.setStretchFactor(1, 1)

        # Playback controls
        self._controls = PlaybackControls(self._player, self._audio_output)

        # Timeline
        self._timeline = TimelineWidget()

        # Main layout
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._top_splitter, 1)
        main_layout.addWidget(self._controls)
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

        file_menu.addSeparator()

        export_action = QAction("&Export SRT...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export_srt)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Subtitles menu
        sub_menu = menubar.addMenu("&Subtitles")

        gen_action = QAction("&Generate (Whisper)...", self)
        gen_action.setShortcut(QKeySequence("Ctrl+G"))
        gen_action.triggered.connect(self._on_generate_subtitles)
        sub_menu.addAction(gen_action)

        clear_action = QAction("&Clear Subtitles", self)
        clear_action.triggered.connect(self._on_clear_subtitles)
        sub_menu.addAction(clear_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _connect_signals(self) -> None:
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._timeline.set_playhead)
        self._player.errorOccurred.connect(self._on_player_error)
        self._controls.position_changed_by_user.connect(self._timeline.set_playhead)
        self._timeline.seek_requested.connect(self._on_timeline_seek)
        self._subtitle_panel.seek_requested.connect(self._on_timeline_seek)

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

    def _load_video(self, path: Path) -> None:
        self._project.reset()
        self._project.video_path = path

        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()

        self._video_widget.set_subtitle_track(None)
        self._subtitle_panel.set_track(None)
        self._timeline.set_track(None)

        self.setWindowTitle(f"{path.name} – {APP_NAME}")
        self.statusBar().showMessage(f"Loaded: {path.name}")

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

    def _apply_subtitle_track(self, track: SubtitleTrack) -> None:
        self._project.subtitle_track = track
        self._video_widget.set_subtitle_track(track)
        self._subtitle_panel.set_track(track)
        self._timeline.set_track(track)
        self.statusBar().showMessage(
            f"Subtitles generated: {len(track)} segments"
        )

    def _on_clear_subtitles(self) -> None:
        self._project.subtitle_track = SubtitleTrack()
        self._video_widget.set_subtitle_track(None)
        self._subtitle_panel.set_track(None)
        self._timeline.set_track(None)
        self.statusBar().showMessage("Subtitles cleared")

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

    def _on_timeline_seek(self, position_ms: int) -> None:
        self._player.setPosition(position_ms)

    def _on_player_error(self, error, error_string: str) -> None:
        self.statusBar().showMessage(f"Player error: {error_string}")

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

    def closeEvent(self, event) -> None:
        settings = QSettings()
        settings.setValue("window_geometry", self.saveGeometry())
        settings.setValue("window_state", self.saveState())
        self._player.stop()
        super().closeEvent(event)
