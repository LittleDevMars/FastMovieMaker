"""재생 컨트롤: 재생/정지, 시크 바, 시간 표시, 볼륨."""

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
    """트랜스포트 바: 재생/정지, 시크 슬라이더, 현재/총 시간 라벨, 볼륨."""

    # 사용자가 슬라이더로 시크했을 때 발생 (밀리초)
    position_changed_by_user = Signal(int)  # ms
    play_toggled = Signal()   # 재생/일시정지 토글 요청
    stop_requested = Signal()  # 정지 요청

    def __init__(self, player: QMediaPlayer, audio_output: QAudioOutput, parent=None):
        super().__init__(parent)
        self._player = player
        self._audio_output = audio_output
        self._tts_audio_output: QAudioOutput | None = None
        self._is_seeking = False

        # --- 위젯 구성 ---
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

        # Video volume
        self._video_vol_label = QLabel("🎬")
        self._video_vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._video_vol_slider.setRange(0, 100)
        self._video_vol_slider.setValue(70)
        self._video_vol_slider.setFixedWidth(80)
        self._video_vol_slider.setToolTip("Video volume")
        self._audio_output.setVolume(0.7)

        # TTS volume
        self._tts_vol_label = QLabel("🎤")
        self._tts_vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._tts_vol_slider.setRange(0, 100)
        self._tts_vol_slider.setValue(100)
        self._tts_vol_slider.setFixedWidth(80)
        self._tts_vol_slider.setToolTip("TTS volume")

        # --- 레이아웃 ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._play_btn)
        layout.addWidget(self._stop_btn)
        layout.addWidget(self._time_label)
        layout.addWidget(self._seek_slider, 1)
        layout.addWidget(self._duration_label)
        layout.addWidget(self._video_vol_label)
        layout.addWidget(self._video_vol_slider)
        layout.addWidget(self._tts_vol_label)
        layout.addWidget(self._tts_vol_slider)

        # --- 시그널 연결 ---
        self._play_btn.clicked.connect(self._on_play)
        self._stop_btn.clicked.connect(self._on_stop)

        self._seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self._seek_slider.sliderReleased.connect(self._on_seek_released)
        self._seek_slider.sliderMoved.connect(self._on_seek_moved)

        self._video_vol_slider.valueChanged.connect(self._on_video_volume_changed)
        self._tts_vol_slider.valueChanged.connect(self._on_tts_volume_changed)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

    # --- 슬롯 ---

    def _on_play(self) -> None:
        self.play_toggled.emit()

    def _on_stop(self) -> None:
        self.stop_requested.emit()

    def _on_seek_pressed(self) -> None:
        self._is_seeking = True

    def _on_seek_released(self) -> None:
        self._is_seeking = False
        pos = self._seek_slider.value()
        self._player.setPosition(pos)
        self.position_changed_by_user.emit(pos)

    def _on_seek_moved(self, value: int) -> None:
        self._time_label.setText(ms_to_display(value))

    def set_tts_audio_output(self, tts_audio_output: QAudioOutput) -> None:
        self._tts_audio_output = tts_audio_output
        tts_audio_output.setVolume(self._tts_vol_slider.value() / 100.0)

    def get_tts_volume(self) -> float:
        """Return current TTS volume from slider (0.0 to 1.0)."""
        return self._tts_vol_slider.value() / 100.0

    def _on_video_volume_changed(self, value: int) -> None:
        self._audio_output.setVolume(value / 100.0)

    def _on_tts_volume_changed(self, value: int) -> None:
        if self._tts_audio_output:
            self._tts_audio_output.setVolume(value / 100.0)

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
        self._player.setPosition(position_ms)
