"""Playback controls: play/stop, seek bar, time display, volume."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

from src.utils.time_utils import ms_to_display


class PlaybackControls(QWidget):
    """Transport bar: play/stop, seek slider, time labels, volume."""

    position_changed_by_user = Signal(int)  # ms

    def __init__(self, player: QMediaPlayer, audio_output: QAudioOutput, parent=None):
        super().__init__(parent)
        self._player = player
        self._audio_output = audio_output
        self._is_seeking = False

        # --- Widgets ---
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedWidth(36)
        self._stop_btn = QPushButton("■")
        self._stop_btn.setFixedWidth(36)

        self._time_label = QLabel("00:00.000")
        self._time_label.setFixedWidth(90)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 0)

        self._duration_label = QLabel("00:00.000")
        self._duration_label.setFixedWidth(90)
        self._duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._volume_label = QLabel("\U0001f50a")
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(70)
        self._volume_slider.setFixedWidth(80)
        self._audio_output.setVolume(0.7)

        # --- Layout ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._play_btn)
        layout.addWidget(self._stop_btn)
        layout.addWidget(self._time_label)
        layout.addWidget(self._seek_slider, 1)
        layout.addWidget(self._duration_label)
        layout.addWidget(self._volume_label)
        layout.addWidget(self._volume_slider)

        # --- Connections ---
        self._play_btn.clicked.connect(self._on_play)
        self._stop_btn.clicked.connect(self._on_stop)

        self._seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self._seek_slider.sliderReleased.connect(self._on_seek_released)
        self._seek_slider.sliderMoved.connect(self._on_seek_moved)

        self._volume_slider.valueChanged.connect(self._on_volume_changed)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

    # --- Slots ---

    def _on_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_stop(self) -> None:
        self._player.stop()

    def _on_seek_pressed(self) -> None:
        self._is_seeking = True

    def _on_seek_released(self) -> None:
        self._is_seeking = False
        pos = self._seek_slider.value()
        self._player.setPosition(pos)
        self.position_changed_by_user.emit(pos)

    def _on_seek_moved(self, value: int) -> None:
        self._time_label.setText(ms_to_display(value))

    def _on_volume_changed(self, value: int) -> None:
        self._audio_output.setVolume(value / 100.0)

    def _on_position_changed(self, position: int) -> None:
        if not self._is_seeking:
            self._seek_slider.setValue(position)
            self._time_label.setText(ms_to_display(position))

    def _on_duration_changed(self, duration: int) -> None:
        self._seek_slider.setRange(0, duration)
        self._duration_label.setText(ms_to_display(duration))

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("⏸")
        else:
            self._play_btn.setText("▶")

    def seek_to(self, position_ms: int) -> None:
        """Programmatic seek (used by timeline/panel clicks)."""
        self._player.setPosition(position_ms)
