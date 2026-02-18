from PySide6.QtCore import QObject, QTimer, QElapsedTimer, Signal, Qt
from PySide6.QtGui import QImage
import logging

# src/utils/time_utils.py가 존재한다고 가정 (PROGRESS.md 기반)
try:
    from src.utils.time_utils import ms_to_frame
except ImportError:
    # 폴백: time_utils가 없을 경우 간단한 구현
    def ms_to_frame(ms: int, fps: float) -> int:
        return int(ms * fps / 1000.0)

logger = logging.getLogger(__name__)

class VideoFramePlayer(QObject):
    """
    프레임 기반 비디오 재생 서비스.
    
    QMediaPlayer의 비디오 렌더링을 대체하여, 타이머 기반으로 
    FrameCacheService에서 프레임 이미지를 가져와 송출합니다.
    이를 통해 소스 전환 지연 없는 즉각적인 재생과 스크럽을 지원합니다.
    """
    
    # UI 업데이트를 위한 시그널
    frame_ready = Signal(QImage)           # 렌더링할 프레임 이미지 방출
    position_changed = Signal(int)         # 현재 재생 위치 변경 (ms)
    playback_state_changed = Signal(bool)  # 재생 상태 변경 (True=Playing, False=Paused/Stopped)
    
    def __init__(self, frame_cache_service, fps: float = 30.0):
        super().__init__()
        self._frame_cache = frame_cache_service
        self._fps = fps
        self._target_interval = int(1000 / fps) if fps > 0 else 33
        
        # 재생 상태
        self._is_playing = False
        self._current_ms = 0
        self._duration_ms = 0
        self._source_path = ""
        self._playback_rate = 1.0
        
        # 정밀 타이머 설정
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._on_tick)
        
        # 델타 타임 측정을 위한 경과 시간 타이머
        self._elapsed_timer = QElapsedTimer()
        self._last_tick_time = 0

    def set_fps(self, fps: float):
        """재생 FPS를 설정하고 타이머 간격을 조정합니다."""
        if fps <= 0:
            logger.warning(f"Invalid FPS: {fps}")
            return
            
        self._fps = fps
        self._target_interval = int(1000 / fps)
        
        # 재생 중이라면 타이머 간격 즉시 업데이트
        if self._is_playing:
            self._timer.setInterval(self._target_interval)
            
    def load_video(self, source_path: str, duration_ms: int):
        """비디오 메타데이터 로드 (길이 설정)"""
        self.stop()
        self._source_path = source_path
        self._duration_ms = duration_ms
        self._current_ms = 0
        self._update_frame()
        logger.info(f"VideoFramePlayer loaded: {source_path}, duration={duration_ms}ms, fps={self._fps}")

    def play(self):
        """재생 시작"""
        if self._is_playing:
            return
            
        self._is_playing = True
        self._elapsed_timer.start()
        self._last_tick_time = self._elapsed_timer.elapsed()
        self._timer.start(self._target_interval)
        self.playback_state_changed.emit(True)

    def pause(self):
        """일시 정지"""
        if not self._is_playing:
            return
            
        self._is_playing = False
        self._timer.stop()
        self.playback_state_changed.emit(False)

    def stop(self):
        """정지 및 위치 초기화"""
        self.pause()
        self.seek(0)

    def seek(self, position_ms: int):
        """특정 위치로 이동 (스크럽)"""
        # 범위 제한
        target_ms = max(0, min(position_ms, self._duration_ms))
        self._current_ms = target_ms
        
        self.position_changed.emit(self._current_ms)
        self._update_frame()
        
        # 재생 중이었다면 델타 타임 기준점 재설정 (튀는 현상 방지)
        if self._is_playing:
            self._last_tick_time = self._elapsed_timer.elapsed()

    @property
    def playback_rate(self) -> float:
        return self._playback_rate

    def set_playback_rate(self, rate: float):
        """재생 속도 설정 (예: 1.0 = 1배속, 2.0 = 2배속)"""
        if rate <= 0 or self._playback_rate == rate:
            return
        self._playback_rate = rate

    def _on_tick(self):
        """타이머 틱 핸들러: 시간 업데이트 및 프레임 요청"""
        now = self._elapsed_timer.elapsed()
        delta = now - self._last_tick_time
        self._last_tick_time = now
        
        # 경과 시간 계산 (재생 속도 반영)
        advance_ms = int(delta * self._playback_rate)
        next_ms = self._current_ms + advance_ms
        
        if next_ms >= self._duration_ms:
            # 영상 끝 도달
            self._current_ms = self._duration_ms
            self.pause()
            self.position_changed.emit(self._current_ms)
            self._update_frame()
        else:
            # 정상 진행
            self._current_ms = next_ms
            self.position_changed.emit(self._current_ms)
            self._update_frame()

    def _update_frame(self):
        """현재 시간에 해당하는 프레임을 캐시에서 가져와 방출"""
        if not self._source_path:
            return

        # ms -> frame index 변환
        frame_idx = ms_to_frame(self._current_ms, self._fps)
        
        # FrameCacheService에 이미지 요청
        image = self._frame_cache.get_frame(self._source_path, frame_idx, self._fps)
        
        if image and not image.isNull():
            self.frame_ready.emit(image)
        else:
            # 캐시 미스 시 처리 (추후 구현: 로딩 인디케이터 또는 이전 프레임 유지)
            # 현재는 아무것도 하지 않음 (UI가 이전 프레임을 유지하도록)
            pass

    def sync_with_audio(self, audio_position_ms: int, threshold_ms: int = 50):
        """
        외부 오디오 플레이어와 동기화 (Phase 3).
        오디오 위치와 비디오 위치가 threshold 이상 차이나면 비디오 위치를 강제 조정합니다.
        """
        if self._duration_ms <= 0:
            return

        # 오디오 위치를 비디오 길이 내로 클램핑
        target_ms = max(0, min(audio_position_ms, self._duration_ms))
        
        diff = abs(self._current_ms - target_ms)
        if diff > threshold_ms:
            self._current_ms = target_ms
            self._update_frame()
            
            # 재생 중이었다면 델타 타임 기준점 재설정 (튀는 현상 방지)
            if self._is_playing:
                self._last_tick_time = self._elapsed_timer.elapsed()