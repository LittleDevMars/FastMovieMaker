"""Main application window."""

import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QUrl, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QUndoStack
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

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
    MergeCommand,
    MoveSegmentCommand,
    SplitCommand,
)
from src.ui.playback_controls import PlaybackControls
from src.ui.subtitle_panel import SubtitlePanel
from src.ui.timeline_widget import TimelineWidget
from src.ui.track_selector import TrackSelector
from src.ui.video_player_widget import VideoPlayerWidget
from src.ui.dialogs.whisper_dialog import WhisperDialog
from src.ui.dialogs.tts_dialog import TTSDialog
from src.utils.config import APP_NAME, APP_VERSION, VIDEO_FILTER, find_ffmpeg


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)

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

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._track_selector)
        right_layout.addWidget(self._subtitle_panel, 1)

        # Top splitter: video | subtitle panel
        self._top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._top_splitter.addWidget(self._video_widget)
        self._top_splitter.addWidget(right_widget)
        self._top_splitter.setStretchFactor(0, 3)
        self._top_splitter.setStretchFactor(1, 1)
        self._top_splitter.setSizes([1050, 390])

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

    def _toggle_play_pause(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _seek_relative(self, delta_ms: int) -> None:
        pos = max(0, self._player.position() + delta_ms)
        self._player.setPosition(pos)

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

    def _on_delete_selected_subtitle(self) -> None:
        rows = self._subtitle_panel._table.selectionModel().selectedRows()
        if rows and self._project.has_subtitles:
            index = rows[0].row()
            self._on_segment_delete(index)

    def _connect_signals(self) -> None:
        # Player signals
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._timeline.set_playhead)
        self._player.errorOccurred.connect(self._on_player_error)
        self._controls.position_changed_by_user.connect(self._timeline.set_playhead)

        # Seek signals
        self._timeline.seek_requested.connect(self._on_timeline_seek)
        self._subtitle_panel.seek_requested.connect(self._on_timeline_seek)

        # Subtitle editing signals (SubtitlePanel)
        self._subtitle_panel.text_edited.connect(self._on_text_edited)
        self._subtitle_panel.time_edited.connect(self._on_time_edited)
        self._subtitle_panel.segment_add_requested.connect(self._on_segment_add)
        self._subtitle_panel.segment_delete_requested.connect(self._on_segment_delete)
        self._subtitle_panel.style_edit_requested.connect(self._on_edit_segment_style)

        # Timeline editing signals
        self._timeline.segment_selected.connect(self._on_timeline_segment_selected)
        self._timeline.segment_moved.connect(self._on_timeline_segment_moved)
        self._timeline.audio_moved.connect(self._on_timeline_audio_moved)

        # Track selector signals
        self._track_selector.track_changed.connect(self._on_track_changed)
        self._track_selector.track_added.connect(self._on_track_added)
        self._track_selector.track_removed.connect(self._on_track_removed)
        self._track_selector.track_renamed.connect(self._on_track_renamed)

        # Undo stack
        self._undo_stack.indexChanged.connect(lambda _: self._refresh_all_widgets())

    # ------------------------------------------------------------ Refresh

    def _refresh_all_widgets(self) -> None:
        """Push current model state to all widgets."""
        track = self._project.subtitle_track
        self._video_widget.set_subtitle_track(track if len(track) > 0 else None)
        self._subtitle_panel.set_track(track if len(track) > 0 else None)
        self._timeline.set_track(track if len(track) > 0 else None)
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

        self._player.setSource(QUrl.fromLocalFile(str(playback_path)))
        self._player.play()

        self._video_widget.set_subtitle_track(None)
        self._subtitle_panel.set_track(None)
        self._timeline.set_track(None)
        self._refresh_track_selector()

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
        dialog = ExportDialog(self._project.video_path, self._project.subtitle_track, parent=self)
        dialog.exec()

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

            self._update_recent_menu()
            self.statusBar().showMessage(f"Project loaded: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", str(e))

    def _on_timeline_seek(self, position_ms: int) -> None:
        self._player.setPosition(position_ms)

    def _on_player_error(self, error, error_string: str) -> None:
        self.statusBar().showMessage(f"Player error: {error_string}")

    def _on_take_screenshot(self) -> None:
        """Capture a screenshot of the main window for debugging."""
        try:
            # Generate timestamp filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = Path(f"/tmp/fastmoviemaker_screenshot_{timestamp}.png")

            # Capture the window
            pixmap = self.grab()
            pixmap.save(str(screenshot_path))

            # Show status message with path
            self.statusBar().showMessage(
                f"Screenshot saved: {screenshot_path}", 5000
            )
            print(f"✅ Screenshot saved to: {screenshot_path}")

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
        self._cleanup_temp_video()
        # Final save before closing
        self._autosave.save_now()
        super().closeEvent(event)
