"""커스텀 페인팅 타임라인 위젯: 자막 블록, 플레이헤드, 오디오/이미지 오버레이 표시."""

from __future__ import annotations

from enum import Enum, auto

from src.utils.i18n import tr

from PySide6.QtCore import Qt, Signal, QPoint, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QPolygon,
    QWheelEvent,
)

import numpy as np
from PySide6.QtWidgets import QMenu, QWidget, QApplication

from src.models.image_overlay import ImageOverlayTrack
from src.models.subtitle import SubtitleTrack
from src.models.video_clip import VideoClipTrack
from src.utils.config import TIMELINE_HEIGHT
from src.utils.time_utils import ms_to_display


class _DragMode(Enum):
    """드래그 종류: 없음, 시크, 자막 이동/리사이즈, 오디오, 플레이헤드, 뷰 팬, 이미지 오버레이."""
    NONE = auto()
    SEEK = auto()           # 빈 공간 클릭·드래그 → 시크
    MOVE = auto()           # 자막 블록 본문 드래그
    RESIZE_LEFT = auto()    # 자막 왼쪽 가장자리
    RESIZE_RIGHT = auto()   # 자막 오른쪽 가장자리
    AUDIO_MOVE = auto()
    AUDIO_RESIZE_LEFT = auto()
    AUDIO_RESIZE_RIGHT = auto()
    PLAYHEAD_DRAG = auto()  # 플레이헤드 드래그
    PAN_VIEW = auto()       # 중단/Shift+드래그로 타임라인 스크롤
    IMAGE_MOVE = auto()
    IMAGE_RESIZE_LEFT = auto()
    IMAGE_RESIZE_RIGHT = auto()
    CLIP_TRIM_LEFT = auto()
    CLIP_TRIM_RIGHT = auto()


# 세그먼트 가장자리에서 리사이즈로 인식하는 픽셀 거리
_EDGE_PX = 6
# 플레이헤드 드래그로 인식하는 픽셀 거리 (클릭 쉽게 넓게)
_PLAYHEAD_HIT_PX = 20

# ---- Track Y-positions ----
_RULER_H = 14
_CLIP_Y = 16
_CLIP_H = 32
_SEG_Y = 52
_SEG_H = 40
_AUDIO_Y = 96
_AUDIO_H = 34
_WAVEFORM_Y = 134
_WAVEFORM_H = 45
_IMG_BASE_Y_NO_VIDEO = 134
_IMG_BASE_Y_WITH_VIDEO = 184


class TimelineWidget(QWidget):
    """타임라인 바: 자막/오디오/이미지 오버레이 세그먼트, 줌·스크롤, 클릭 시크, 드래그 이동·리사이즈."""

    seek_requested = Signal(int)  # ms
    segment_selected = Signal(int)  # 세그먼트 인덱스
    segment_moved = Signal(int, int, int)  # (index, new_start_ms, new_end_ms)
    audio_moved = Signal(int, int)  # (new_start_ms, new_duration_ms)
    image_overlay_selected = Signal(int)  # 오버레이 인덱스
    image_overlay_moved = Signal(int, int, int)  # (index, new_start_ms, new_end_ms)
    image_overlay_resize = Signal(int, str)  # (index, mode: "fit_width"/"full"/"16:9"/"9:16")
    insert_image_requested = Signal(int)  # 이미지 삽입 위치(ms)
    image_file_dropped = Signal(str, int)  # (file_path, position_ms)
    video_file_dropped = Signal(str, int)  # (file_path, position_ms)
    clip_selected = Signal(int)            # 클립 인덱스
    clip_split_requested = Signal(int)     # 분할 위치(timeline_ms)
    clip_deleted = Signal(int)             # 클립 인덱스
    clip_trimmed = Signal(int, int, int)   # (index, new_source_in, new_source_out)

    # 색상 상수
    # Modern Dark Theme Colors
    _BG_COLOR = QColor(18, 18, 18)            # Deep dark background
    _RULER_BG_COLOR = QColor(25, 25, 25)      # Slightly lighter for ruler
    _RULER_COLOR = QColor(60, 60, 60)         # Subtle ticks
    _RULER_TEXT_COLOR = QColor(140, 140, 140) # Readable text
    
    # Subtitle Segments (Blue Gradient)
    _SEGMENT_COLOR_TOP = QColor(60, 140, 220)
    _SEGMENT_COLOR_BOT = QColor(40, 100, 180)
    _SEGMENT_BORDER = QColor(80, 170, 255)
    
    # Selection (Glowy Cyan/Blue)
    _SELECTED_BORDER = QColor(100, 220, 255)
    _SELECTED_GLOW = QColor(100, 220, 255, 60)

    # Snap
    _SNAP_THRESHOLD_PX = 10
    _SNAP_GUIDE_COLOR = QColor(255, 255, 0, 200)

    # Playhead (Red accent)
    _PLAYHEAD_COLOR = QColor(255, 60, 80)
    _PLAYHEAD_LINE_COLOR = QColor(255, 60, 80, 200)

    # Audio (Green Gradient)
    _AUDIO_COLOR_TOP = QColor(80, 180, 100)
    _AUDIO_COLOR_BOT = QColor(50, 140, 70)
    _AUDIO_BORDER = QColor(100, 200, 120)
    _AUDIO_SELECTED_BORDER = QColor(100, 220, 255)
    _AUDIO_SELECTED_COLOR = QColor(0, 100, 140)

    # Video Audio / Waveform (Orange)
    _WAVEFORM_FILL = QColor(255, 140, 40, 120)
    _WAVEFORM_EDGE = QColor(255, 180, 80, 200)
    _WAVEFORM_CENTER = QColor(255, 220, 150) # Bright center line
    _VIDEO_AUDIO_BORDER = QColor(255, 160, 60)
    _VIDEO_AUDIO_COLOR = QColor(255, 140, 40, 50) # Fallback background
    
    # Image Overlays (Purple Gradient)
    _IMG_OVERLAY_COLOR_TOP = QColor(160, 90, 220)
    _IMG_OVERLAY_COLOR_BOT = QColor(120, 60, 180)
    _IMG_OVERLAY_BORDER = QColor(190, 120, 240)
    _IMG_OVERLAY_SELECTED_BORDER = QColor(100, 220, 255)
    _IMG_OVERLAY_SELECTED_COLOR = QColor(0, 100, 140)

    # Image Overlay Layout
    _IMG_ROW_H = 40
    _IMG_ROW_GAP = 4

    # Video Clips (Teal/Varied Gradient)
    # Default clip colors
    _CLIP_COLOR_TOP = QColor(0, 160, 160)
    _CLIP_COLOR_BOT = QColor(0, 120, 120)
    _CLIP_BORDER = QColor(0, 200, 200)
    _CLIP_SPLIT_LINE = QColor(255, 255, 255, 180) # Solid, visible split line
    
    # Selected Clip Colors
    _CLIP_SELECTED_BORDER = QColor(100, 220, 255)     # Cyan
    _CLIP_SELECTED_COLOR = QColor(0, 100, 140)        # Dark Cyan Body

    # Thumbnail Layout
    _THUMBNAIL_INTERVAL_PX = 100  # Distance between thumbnails

    # Multi-source clip color palette (Gradient Tops/Bots)
    # List of (Top, Bot, Border)
    _SOURCE_COLORS = [
        (QColor(0, 160, 160), QColor(0, 120, 120), QColor(0, 200, 200)),     # Teal
        (QColor(200, 120, 40), QColor(160, 90, 20), QColor(230, 150, 60)),   # Orange
        (QColor(140, 70, 190), QColor(100, 40, 150), QColor(170, 100, 220)), # Purple
        (QColor(60, 160, 80), QColor(40, 120, 50), QColor(90, 190, 110)),    # Green
        (QColor(200, 60, 80), QColor(150, 40, 60), QColor(230, 90, 110)),    # Red
        (QColor(70, 110, 200), QColor(40, 80, 160), QColor(100, 140, 230)),  # Blue
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TIMELINE_HEIGHT)
        self.setMouseTracking(True)  # 마우스 무버 without 버튼으로도 hover 처리
        self.setAcceptDrops(True)  # 미디어 라이브러리에서 드래그 앤 드롭

        # 배경·테두리 명시 (가독성)
        self.setStyleSheet("""
            TimelineWidget {
                background-color: rgb(30, 30, 30);
                border-top: 1px solid rgb(50, 50, 50);
            }
        """)

        self._track: SubtitleTrack | None = None
        self._duration_ms: int = 0   # 비디오 총 길이(ms)
        self._has_video: bool = False  # 비디오 로드 여부
        self._playhead_ms: int = 0   # 현재 재생 위치(ms)

        # 줌/스크롤: 화면에 보이는 시간 범위
        self._visible_start_ms: float = 0.0
        self._px_per_ms: float = 0.0  # 픽셀당 밀리초 (줌 레벨)

        # 선택 상태
        self._selected_index: int = -1
        self._audio_selected: bool = False

        # 드래그 상태
        self._drag_mode = _DragMode.NONE
        self._drag_seg_index: int = -1
        self._drag_start_x: float = 0.0
        self._drag_orig_start_ms: int = 0
        self._drag_orig_end_ms: int = 0
        self._drag_orig_audio_start_ms: int = 0
        self._drag_orig_audio_duration_ms: int = 0

        # 이미지 오버레이 트랙
        self._image_overlay_track: ImageOverlayTrack | None = None
        self._selected_overlay_index: int = -1

        # 비디오 클립 트랙
        self._clip_track: VideoClipTrack | None = None
        self._selected_clip_index: int = -1
        self._drag_clip_index: int = -1
        self._drag_orig_source_in: int = 0
        self._drag_orig_source_out: int = 0

        # 프레임 스냅 FPS (0 = 비활성화)
        self._snap_fps: int = 0
        
        # 자석 스냅 상태
        self._snap_enabled: bool = True
        self._snap_guide_x: float | None = None

        # 웨이브폼: 비디오 오디오 파형 (캐시로 그리기 부담 감소)
        self._waveform_data = None  # WaveformData or None
        self._waveform_image_cache: QImage | None = None
        self._waveform_cache_key: tuple | None = None

        # 썸네일 서비스
        from src.services.timeline_thumbnail_service import TimelineThumbnailService
        self._thumbnail_service = TimelineThumbnailService(self)
        self._thumbnail_service.thumbnail_ready.connect(self.update)

        # 정적 레이어 캐시 (눈금자+세그먼트+오디오+이미지+웨이브폼)
        self._static_cache: QPixmap | None = None
        self._static_cache_key: tuple | None = None

        # 드롭 표시
        self._drop_indicator_x: float = -1

    # -------------------------------------------------------- 공개 API

    def set_snap_fps(self, fps: int) -> None:
        """Set FPS for frame snapping during drag. 0 = disabled."""
        self._snap_fps = fps

    def _snap_ms(self, ms: int) -> int:
        """Snap milliseconds to nearest frame boundary if snap is enabled."""
        if self._snap_fps > 0:
            from src.utils.time_utils import snap_to_frame
            return snap_to_frame(ms, self._snap_fps)
        return ms

    def _invalidate_static_cache(self) -> None:
        """정적 레이어 캐시 무효화 — 데이터/줌/스크롤 변경 시 호출."""
        self._static_cache = None
        self._static_cache_key = None

    def set_track(self, track: SubtitleTrack | None) -> None:
        self._track = track
        self._selected_index = -1
        self._invalidate_static_cache()
        self.update()

    def set_duration(self, duration_ms: int, has_video: bool | None = None) -> None:
        self._duration_ms = duration_ms
        if has_video is not None:
            self._has_video = has_video
        self._visible_start_ms = 0
        # _px_per_ms 즉시 초기화 (paintEvent 전에도 set_playhead 등이 올바로 작동하도록)
        if duration_ms > 0 and self.width() > 0:
            self._px_per_ms = self.width() / float(duration_ms)
        self._invalidate_static_cache()
        self.update()

    def get_playhead(self) -> int:
        """Return current playhead position in milliseconds."""
        return self._playhead_ms

    def set_playhead(self, position_ms: int) -> None:
        # 플레이헤드 드래그 중에는 외부 갱신 무시 (충돌 방지)
        if self._drag_mode == _DragMode.PLAYHEAD_DRAG:
            return

        self._playhead_ms = position_ms
        visible_range = self._visible_range_ms()
        if visible_range > 0:
            if position_ms > self._visible_start_ms + visible_range * 0.8:
                self._visible_start_ms = position_ms - visible_range * 0.2
            elif position_ms < self._visible_start_ms:
                self._visible_start_ms = max(0, position_ms - visible_range * 0.1)
        self.update()

    def refresh(self) -> None:
        """외부에서 모델 변경 후 다시 그리기."""
        self._invalidate_static_cache()
        self.update()

    def select_segment(self, index: int) -> None:
        self._selected_index = index
        self._invalidate_static_cache()
        self.update()

    def set_image_overlay_track(self, track: ImageOverlayTrack | None) -> None:
        self._image_overlay_track = track
        self._selected_overlay_index = -1
        self._invalidate_static_cache()
        self.update()

    def select_image_overlay(self, index: int) -> None:
        self._selected_overlay_index = index
        self._invalidate_static_cache()
        self.update()

    def set_clip_track(self, track: VideoClipTrack | None) -> None:
        self._clip_track = track
        self._selected_clip_index = -1
        self._invalidate_static_cache()
        self.update()

    def select_clip(self, index: int) -> None:
        self._selected_clip_index = index
        self._invalidate_static_cache()
        self.update()

    # -------------------------------------------------------- 줌 API

    zoom_changed = Signal(int)  # 줌 퍼센트 (100 = 전체 맞춤)

    def zoom_in(self) -> None:
        """타임라인 확대 (더 짧은 시간 범위 표시)."""
        if self._duration_ms <= 0:
            return
        self._apply_zoom(0.6)

    def zoom_out(self) -> None:
        """타임라인 축소 (더 긴 시간 범위 표시)."""
        if self._duration_ms <= 0:
            return
        self._apply_zoom(1.6)

    def zoom_fit(self) -> None:
        """줌 초기화: 전체 길이에 맞춤."""
        if self._duration_ms <= 0:
            return
        self._visible_start_ms = 0
        self._px_per_ms = self.width() / float(self._duration_ms)
        self._invalidate_static_cache()
        self.zoom_changed.emit(self.get_zoom_percent())
        self.update()

    def _apply_zoom(self, factor: float) -> None:
        """현재 플레이헤드 위치를 중심으로 줌 배율 적용."""
        old_range = self._visible_range_ms()
        new_range = max(1000.0, min(float(self._duration_ms), old_range * factor))
        # Center zoom on playhead
        center_ms = self._playhead_ms
        self._visible_start_ms = max(0.0, center_ms - new_range / 2.0)
        self._px_per_ms = self.width() / new_range
        self._clamp_visible_start(new_range)
        self._invalidate_static_cache()
        self.zoom_changed.emit(self.get_zoom_percent())
        self.update()

    def get_zoom_percent(self) -> int:
        """현재 줌 레벨을 퍼센트로 반환 (100% = 전체 맞춤)."""
        if self._duration_ms <= 0:
            return 100
        fit_range = float(self._duration_ms)
        visible = self._visible_range_ms()
        if visible <= 0:
            return 100
        return max(1, int(fit_range / visible * 100))

    def set_waveform(self, waveform_data) -> None:
        """미리 계산된 웨이브폼 데이터 설정 후 표시."""
        self._waveform_data = waveform_data
        self._waveform_image_cache = None
        self._waveform_cache_key = None
        self._invalidate_static_cache()
        self.update()

    def clear_waveform(self) -> None:
        """웨이브폼 제거."""
        self._waveform_data = None
        self._waveform_image_cache = None
        self._waveform_cache_key = None
        self._invalidate_static_cache()
        self.update()

    # ----------------------------------------------------------- 그리기

    def resizeEvent(self, event) -> None:
        """위젯 크기 변경 시 _px_per_ms를 비례 스케일링하여 동일 시간 범위 유지."""
        super().resizeEvent(event)
        old_w = event.oldSize().width()
        new_w = event.size().width()
        if old_w > 0 and new_w > 0 and self._px_per_ms > 0:
            self._px_per_ms = self._px_per_ms * new_w / old_w
            self._invalidate_static_cache()

    def paintEvent(self, event: QPaintEvent) -> None:
        w = self.width()
        h = self.height()

        if self._duration_ms <= 0:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(0, 0, w, h, self._BG_COLOR)
            painter.setPen(self._RULER_TEXT_COLOR)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No video loaded")
            painter.end()
            return

        visible_ms = self._visible_range_ms()
        if visible_ms <= 0:
            visible_ms = self._duration_ms
        self._px_per_ms = w / visible_ms

        # 정적 레이어 캐시 키: 크기·줌·스크롤·선택 상태·트랙 길이
        seg_count = len(self._track) if self._track else 0
        ovl_count = len(self._image_overlay_track) if self._image_overlay_track else 0
        clip_count = len(self._clip_track) if self._clip_track else 0
        cache_key = (
            w, h, self._visible_start_ms, visible_ms,
            self._selected_index, self._selected_overlay_index,
            self._selected_clip_index, clip_count,
            seg_count, ovl_count, self._has_video,
            id(self._waveform_data),
        )

        if self._static_cache_key != cache_key or self._static_cache is None:
            # 정적 레이어를 QPixmap에 렌더링
            pixmap = QPixmap(w, h)
            pp = QPainter(pixmap)
            pp.setRenderHint(QPainter.RenderHint.Antialiasing)
            pp.fillRect(0, 0, w, h, self._BG_COLOR)

            self._draw_ruler(pp, w, h, visible_ms)
            self._draw_clips(pp, w)
            self._draw_video_audio(pp, w, h)
            if self._track:
                self._draw_audio_track(pp, h)
                self._draw_segments(pp, h)
            self._draw_image_overlays(pp, h)
            pp.end()

            self._static_cache = pixmap
            self._static_cache_key = cache_key

        # 캐시된 정적 레이어 블릿 + 동적 요소(플레이헤드, 드롭 표시)
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._static_cache)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_playhead(painter, h)
        self._draw_snap_indicator(painter, h)
        self._draw_drop_indicator(painter, h)
        painter.end()

    def _draw_snap_indicator(self, painter: QPainter, h: int) -> None:
        """자석 스냅 가이드라인 그리기."""
        if self._snap_guide_x is None:
            return
        
        x = float(self._snap_guide_x)
        painter.setPen(QPen(self._SNAP_GUIDE_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(x), 0, int(x), h)

    def _handle_clip_drag(self, x: float) -> None:
        """비디오 클립 트림 처리."""
        if not self._clip_track or self._drag_clip_index < 0:
            return
        if self._drag_clip_index >= len(self._clip_track.clips):
            return

        dx_ms = int((x - self._drag_start_x) / self._px_per_ms) if self._px_per_ms > 0 else 0
        clip = self._clip_track.clips[self._drag_clip_index]
        
        # Clip start time on timeline (visual start)
        # Note: In gapless sequence, start depends on prev clips.
        # But during drag, we assume prev clips are static (we are trimming current).
        boundaries = self._clip_track.clip_boundaries_ms()
        if self._drag_clip_index >= len(boundaries):
             return
        clip_start_ms = boundaries[self._drag_clip_index]

        candidates = self._get_magnetic_snap_candidates(skip_clip_index=self._drag_clip_index)

        if self._drag_mode == _DragMode.CLIP_TRIM_LEFT:
            # Changing Source In -> Changes Duration -> Changes End Time
            # We snap the End Time
            
            new_in = max(0, self._drag_orig_source_in + dx_ms)
            new_in = min(new_in, clip.source_out_ms - 100)
            
            new_duration = clip.source_out_ms - new_in
            new_end = clip_start_ms + new_duration
            
            snapped_end = self._apply_magnetic_snap(new_end, candidates)
            if self._snap_guide_x is None:
                 snapped_end = self._snap_ms(new_end)
            
            # Recalculate new_in based on snapped end
            final_duration = snapped_end - clip_start_ms
            # Ensure min duration
            if final_duration < 100:
                final_duration = 100
                
            clip.source_in_ms = clip.source_out_ms - final_duration

        elif self._drag_mode == _DragMode.CLIP_TRIM_RIGHT:
            # Changing Source Out -> Changes Duration -> Changes End Time
            
            new_out = max(clip.source_in_ms + 100, self._drag_orig_source_out + dx_ms)
            
            new_duration = new_out - clip.source_in_ms
            new_end = clip_start_ms + new_duration
            
            snapped_end = self._apply_magnetic_snap(new_end, candidates)
            if self._snap_guide_x is None:
                 snapped_end = self._snap_ms(new_end)
                 
            final_duration = snapped_end - clip_start_ms
            if final_duration < 100:
                final_duration = 100
                
            clip.source_out_ms = clip.source_in_ms + final_duration

        self._invalidate_static_cache()
        self.update()

    def _draw_ruler(self, painter: QPainter, w: int, h: int, visible_ms: float) -> None:
        """상단 눈금자: 보이는 범위에 맞춰 틱 간격 계산 후 시간 라벨 그리기."""
        # Ruler Background
        painter.fillRect(0, 0, w, _RULER_H, self._RULER_BG_COLOR)
        
        painter.setFont(QFont("Arial", 8))
        tick_ms = self._nice_tick_interval(visible_ms)
        if tick_ms <= 0:
            return
        start_tick = int(self._visible_start_ms / tick_ms) * tick_ms
        if start_tick < self._visible_start_ms:
            start_tick += tick_ms
        t = start_tick
        while t <= self._visible_start_ms + visible_ms:
            x = self._ms_to_x(t)
            
            # Major Tick
            painter.setPen(QPen(self._RULER_COLOR, 1))
            painter.drawLine(int(x), 0, int(x), _RULER_H)
            
            # Time Label
            painter.setPen(self._RULER_TEXT_COLOR)
            painter.drawText(int(x) + 4, 11, ms_to_display(int(t)))
            
            # Minor Ticks (optional, e.g. 4 sub-ticks)
            # sub_tick = tick_ms / 5
            # for k in range(1, 5):
            #     sub_t = t + sub_tick * k
            #     sub_x = self._ms_to_x(sub_t)
            #     if sub_x > w: break
            #     painter.drawLine(int(sub_x), 0, int(sub_x), 6)

            t += tick_ms

    def _draw_video_audio(self, painter: QPainter, w: int, h: int) -> None:
        """비디오 오디오 웨이브폼 또는 로딩 중일 때 대체 바 그리기."""
        if self._duration_ms <= 0 or not self._has_video:
            return
        # Hide waveform when multi-clip (T2에서 클립별 웨이브폼 구현 예정)
        if self._clip_track and len(self._clip_track.clips) > 1:
            return

        if self._waveform_data is not None and self._waveform_data.duration_ms > 0:
            self._draw_waveform(painter, w)
        else:
            self._draw_video_audio_fallback(painter, w)

    def _draw_waveform(self, painter: QPainter, w: int) -> None:
        """캐시된 QImage로 웨이브폼 그리기 (성능)."""
        wf = self._waveform_data
        if wf is None or wf.duration_ms <= 0:
            return

        waveform_y = _WAVEFORM_Y
        waveform_h = _WAVEFORM_H

        visible_ms = self._visible_range_ms()
        cache_key = (self._visible_start_ms, visible_ms, w)

        if self._waveform_cache_key != cache_key:
            self._waveform_image_cache = self._render_waveform_image(w, waveform_h)
            self._waveform_cache_key = cache_key

        if self._waveform_image_cache is not None:
            painter.drawImage(0, waveform_y, self._waveform_image_cache)

        # Draw label
        label_x = max(5, int(self._ms_to_x(0)) + 5)
        if 0 < label_x < w - 80:
            painter.setPen(QColor(255, 200, 100, 200))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(label_x, waveform_y + 10, "Video Audio")

    def _render_waveform_image(self, w: int, h: int) -> QImage:
        """웨이브폼을 QImage로 렌더링하여 빠르게 블릿."""
        wf = self._waveform_data
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0, 0))

        if wf is None or wf.duration_ms <= 0:
             return img
        
        # Help static analysis
        assert wf is not None
        assert wf.duration_ms > 0

        center_y = h // 2
        half_h = h / 2.0

        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        fill_color = self._WAVEFORM_FILL
        edge_color = self._WAVEFORM_EDGE

        for px in range(w):
            ms_start = self._x_to_ms(px)
            ms_end = self._x_to_ms(px + 1)
            ms_start_i = max(0, int(ms_start))
            ms_end_i = min(int(wf.duration_ms), int(ms_end))

            if ms_start_i >= ms_end_i or ms_start_i >= wf.duration_ms:
                continue

            # Ensure we have data in range
            if ms_end_i > len(wf.peaks_pos):
                ms_end_i = len(wf.peaks_pos)
            if ms_start_i >= ms_end_i:
                continue

            peak_max = float(np.max(wf.peaks_pos[ms_start_i:ms_end_i]))
            peak_min = float(np.min(wf.peaks_neg[ms_start_i:ms_end_i]))

            y_top = center_y - int(peak_max * half_h)
            y_bot = center_y - int(peak_min * half_h)
            if y_bot <= y_top:
                y_bot = y_top + 1

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(fill_color))
            p.drawRect(px, y_top, 1, y_bot - y_top)

            p.setBrush(QBrush(edge_color))
            p.drawRect(px, y_top, 1, 1)
            if y_bot - y_top > 2:
                p.drawRect(px, y_bot - 1, 1, 1)

        # Center line
        p.setPen(QPen(self._WAVEFORM_CENTER, 1))
        p.drawLine(0, center_y, w, center_y)

        p.end()
        return img

    def _draw_video_audio_fallback(self, painter: QPainter, w: int) -> None:
        """웨이브폼 데이터 없을 때 단순 바 + 'Loading waveform...' 표시."""
        video_audio_y = _WAVEFORM_Y
        video_audio_h = _WAVEFORM_H

        x1 = self._ms_to_x(0)
        x2 = self._ms_to_x(self._duration_ms)

        if x2 < 0 or x1 > w:
            return

        rect = QRectF(x1, video_audio_y, max(x2 - x1, 2), video_audio_h)
        painter.setPen(QPen(self._VIDEO_AUDIO_BORDER, 1))
        painter.setBrush(QBrush(self._VIDEO_AUDIO_COLOR))
        painter.drawRoundedRect(rect, 3, 3)

        if x2 - x1 > 100:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 9))
            label_rect = QRectF(x1 + 5, video_audio_y, x2 - x1 - 10, video_audio_h)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Loading waveform...")

    def _draw_audio_track(self, painter: QPainter, h: int) -> None:
        """세그먼트별 TTS 오디오 구간을 녹색 박스로 그림."""
        if not self._track:
            return

        audio_y = _AUDIO_Y
        audio_h = _AUDIO_H

        # Draw individual audio segments
        for i, seg in enumerate(self._track):
            # Only draw if this segment has audio
            if not seg.audio_file:
                continue

            x1 = self._ms_to_x(seg.start_ms)
            x2 = self._ms_to_x(seg.end_ms)

            if x2 < 0 or x1 > self.width():
                continue

            rect = QRectF(x1, audio_y, max(x2 - x1, 2), audio_h)

            # Highlight selected audio segment
            if i == self._selected_index:
                painter.setPen(QPen(self._AUDIO_SELECTED_BORDER, 2))
                painter.setBrush(QBrush(self._AUDIO_SELECTED_COLOR))
            else:
                painter.setPen(QPen(self._AUDIO_BORDER, 1))
                painter.setBrush(QBrush(self._AUDIO_COLOR))

            painter.drawRoundedRect(rect, 3, 3)

            # Draw label (segment number)
            if rect.width() > 30:
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                text_rect = rect.adjusted(4, 2, -4, -2)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                    f"🔊 {i+1}",
                )

    def _draw_segments(self, painter: QPainter, h: int) -> None:
        """자막 세그먼트를 파란 그라데이션 박스로 그리기."""
        seg_y = _SEG_Y
        seg_h = _SEG_H

        for i, seg in enumerate(self._track):
            x1 = self._ms_to_x(seg.start_ms)
            x2 = self._ms_to_x(seg.end_ms)
            if x2 < 0 or x1 > self.width():
                continue

            rect = QRectF(x1, seg_y, max(x2 - x1, 2), seg_h)

            if i == self._selected_index:
                painter.setPen(QPen(self._SELECTED_BORDER, 2))
                # Selection Glow
                glow = QLinearGradient(0, seg_y, 0, seg_y + seg_h)
                glow.setColorAt(0, self._SELECTED_COLOR)
                glow.setColorAt(1, self._SELECTED_COLOR.darker(130))
                painter.setBrush(QBrush(glow))
            else:
                painter.setPen(QPen(self._SEGMENT_BORDER, 1))
                # Standard Gradient
                grad = QLinearGradient(0, seg_y, 0, seg_y + seg_h)
                grad.setColorAt(0, self._SEGMENT_COLOR_TOP)
                grad.setColorAt(1, self._SEGMENT_COLOR_BOT)
                painter.setBrush(QBrush(grad))
            
            # Rounded Corners (6px)
            painter.drawRoundedRect(rect, 6, 6)

            if rect.width() > 30:
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Arial", 9))
                text_rect = rect.adjusted(6, 2, -6, -2)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    painter.fontMetrics().elidedText(
                        seg.text, Qt.TextElideMode.ElideRight, int(text_rect.width())
                    ),
                )

    # ---- 이미지 오버레이 레이아웃 상수 & 헬퍼 ----
    _IMG_ROW_H = 28
    _IMG_ROW_GAP = 2

    def _img_overlay_base_y(self) -> int:
        """이미지 오버레이 트랙의 기준 y 좌표."""
        return _IMG_BASE_Y_NO_VIDEO if not self._has_video else _IMG_BASE_Y_WITH_VIDEO

    def _compute_overlay_rows(self) -> list[int]:
        """각 오버레이의 row 인덱스를 계산 (시간 겹침 → 다음 row)."""
        if not self._image_overlay_track:
            return []
        rows: list[int] = []
        row_ends: list[float] = []
        for ov in self._image_overlay_track:
            placed = False
            for r, end_ms in enumerate(row_ends):
                if ov.start_ms >= end_ms:
                    rows.append(r)
                    row_ends[r] = ov.end_ms
                    placed = True
                    break
            if not placed:
                rows.append(len(row_ends))
                row_ends.append(ov.end_ms)
        return rows

    def _img_overlay_total_h(self, rows: list[int]) -> int:
        """이미지 오버레이 트랙의 총 높이."""
        if not rows:
            return self._IMG_ROW_H
        max_row = max(rows)
        return (max_row + 1) * (self._IMG_ROW_H + self._IMG_ROW_GAP)

    def _draw_image_overlays(self, painter: QPainter, h: int) -> None:
        """이미지 오버레이 세그먼트를 타임라인에 그림 (겹치면 세로로 쌓기)."""
        if not self._image_overlay_track or len(self._image_overlay_track) == 0:
            return

        img_base_y = self._img_overlay_base_y()
        img_h = self._IMG_ROW_H
        img_gap = self._IMG_ROW_GAP

        rows = self._compute_overlay_rows()

        # 색상 팔레트: 각 row별 다른 색상
        palette = [
            self._IMG_OVERLAY_COLOR,
            QColor(120, 80, 180, 180),   # 보라
            QColor(80, 160, 120, 180),   # 초록
            QColor(180, 120, 80, 180),   # 주황
        ]
        border_palette = [
            self._IMG_OVERLAY_BORDER,
            QColor(160, 120, 220),
            QColor(120, 200, 160),
            QColor(220, 160, 120),
        ]

        for i, ov in enumerate(self._image_overlay_track):
            x1 = self._ms_to_x(ov.start_ms)
            x2 = self._ms_to_x(ov.end_ms)
            if x2 < 0 or x1 > self.width():
                continue

            row = rows[i]
            y = img_base_y + row * (img_h + img_gap)
            rect = QRectF(x1, y, max(x2 - x1, 2), img_h)

            color_idx = row % len(palette)
            if i == self._selected_overlay_index:
                painter.setPen(QPen(self._IMG_OVERLAY_SELECTED_BORDER, 2))
                painter.setBrush(QBrush(self._IMG_OVERLAY_SELECTED_COLOR))
            else:
                painter.setPen(QPen(border_palette[color_idx], 1))
                painter.setBrush(QBrush(palette[color_idx]))
            painter.drawRoundedRect(rect, 3, 3)

            if rect.width() > 30:
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Arial", 8))
                text_rect = rect.adjusted(4, 2, -4, -2)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    painter.fontMetrics().elidedText(
                        ov.file_name, Qt.TextElideMode.ElideRight, int(text_rect.width())
                    ),
                )

    def _draw_playhead(self, painter: QPainter, h: int) -> None:
        """현재 재생 위치 세로선 + 상단 노브 (Pentagon)."""
        x = self._ms_to_x(self._playhead_ms)
        
        # Line
        painter.setPen(QPen(self._PLAYHEAD_LINE_COLOR, 1))
        painter.drawLine(int(x), 0, int(x), h)
        
        # Knob (Pentagon)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._PLAYHEAD_COLOR))
        
        # Shape:
        #   (x, 0) - Top Center
        #   (x+6, 5) - Top Right
        #   (x+6, 14) - Bottom Right
        #   (x-6, 14) - Bottom Left
        #   (x-6, 5) - Top Left
        painter.drawPolygon(QPolygon([
            QPoint(int(x), 0),
            QPoint(int(x) + 6, 5),
            QPoint(int(x) + 6, 14),
            QPoint(int(x) - 6, 14),
            QPoint(int(x) - 6, 5),
        ]))

    def _draw_clips(self, painter: QPainter, w: int) -> None:
        """비디오 클립들을 그라데이션 박스로 그림."""
        if not self._clip_track or not self._clip_track.clips:
            return

        # Assign colors to unique source paths
        source_paths = set(c.source_path for c in self._clip_track.clips)
        source_color_map = {}
        # Fix: source_path can be None, which breaks sorted() string comparison
        for i, path in enumerate(sorted(list(source_paths), key=lambda x: str(x) if x is not None else "")):
            source_color_map[path] = i

        # Calculate clip positions
        clip_starts = self._clip_track.clip_boundaries_ms()

        for i, clip in enumerate(self._clip_track.clips):
            start_ms = clip_starts[i]
            x1 = self._ms_to_x(start_ms)
            x2 = self._ms_to_x(start_ms + clip.duration_ms)

            if x2 < 0 or x1 > w:
                continue

            rect = QRectF(x1, _CLIP_Y, max(x2 - x1, 2), _CLIP_H)
            
            if i == self._selected_clip_index:
                painter.setPen(QPen(self._CLIP_SELECTED_BORDER, 2))
                
                # Selection Glow Effect
                glow_gradient = QLinearGradient(0, _CLIP_Y, 0, _CLIP_Y + _CLIP_H)
                glow_gradient.setColorAt(0, self._CLIP_SELECTED_COLOR)
                glow_gradient.setColorAt(1, self._CLIP_SELECTED_COLOR.darker(120))
                painter.setBrush(QBrush(glow_gradient))
            else:
                color_idx = source_color_map.get(clip.source_path, 0) % len(self._SOURCE_COLORS)
                c_top, c_bot, border_color = self._SOURCE_COLORS[color_idx]
                
                # Gradient Background
                gradient = QLinearGradient(0, _CLIP_Y, 0, _CLIP_Y + _CLIP_H)
                gradient.setColorAt(0, c_top)
                gradient.setColorAt(1, c_bot)
                
                painter.setPen(QPen(border_color, 1))
                painter.setBrush(QBrush(gradient))
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 6, 6)
            
            # --- Filmstrip Thumbnails ---
            if clip.source_path:  # Only for external video files
                # Calculate visible range for this clip
                vis_x1 = max(0, int(x1))
                vis_x2 = min(w, int(x2))
                
                if vis_x2 > vis_x1:
                    # Align to grid to prevent jitter
                    interval = self._THUMBNAIL_INTERVAL_PX
                    start_grid = (vis_x1 // interval) * interval
                    
                    # Save painter state for clipping
                    painter.save()
                    painter.setClipRect(rect)
                    
                    for tx in range(start_grid, vis_x2, interval):
                        # Skip if before clip start
                        if tx + interval < x1: 
                            continue
                            
                        # Calculate source timestamp
                        offset_ms = (tx - x1) / self._px_per_ms
                        source_ms = int(clip.source_in_ms + offset_ms)
                        
                        # Request thumbnail
                        thumb = self._thumbnail_service.request_thumbnail(
                            clip.source_path, source_ms, _CLIP_H
                        )
                        
                        if thumb:
                            # Draw thumbnail centered or stretched? 
                            # Stretched to interval width looks more like filmstrip
                            # But aspect ratio might be wrong. 
                            # Let's draw it "aspect fit" or "slice".
                            # Filmstrip usually fills the height.
                            target_rect = QRectF(float(tx), float(_CLIP_Y), float(interval), float(_CLIP_H))
                            
                            # Draw slice of image or repeat? 
                            # Simple approach: Draw entire thumbnail at position, properly clipped
                            # Actually, request_thumbnail returns an image of height _CLIP_H.
                            # We should just draw it.
                            t_w = thumb.width()
                            t_h = thumb.height()
                            
                            # Center the thumbnail in the interval slot?
                            # Or just place it.
                            # Better: Draw at tx.
                            painter.drawImage(tx, int(_CLIP_Y), thumb)
                            
                    painter.restore()

            # Rounded Corners (6px)
            # painter.drawRoundedRect(rect, 6, 6) # This line was moved up

            # Draw white split line at the start if not the first clip
            if i > 0:
                painter.setPen(QPen(self._CLIP_SPLIT_LINE, 2))
                painter.drawLine(int(x1), _CLIP_Y, int(x1), _CLIP_Y + _CLIP_H)

            # Draw labels only if wide enough
            if rect.width() > 40:
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Arial", 9))
                
                idx_rect = QRectF(x1 + 4, _CLIP_Y, 20, _CLIP_H)
                painter.drawText(idx_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(i + 1))
                
                name_rect = QRectF(x1 + 24, _CLIP_Y, rect.width() - 28, _CLIP_H)
                from pathlib import Path
                fname = Path(clip.source_path).name if clip.source_path else "Main Video"
                painter.drawText(
                    name_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    painter.fontMetrics().elidedText(fname, Qt.TextElideMode.ElideRight, int(name_rect.width()))
                )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._duration_ms <= 0 or self._px_per_ms <= 0:
            return

        x = event.position().x()
        y = event.position().y()

        # Shift + 클릭 드래그: 뷰 팬
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._drag_mode = _DragMode.PAN_VIEW
            self._drag_start_x = x
            self._drag_start_visible_ms = self._visible_start_ms
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            return

        seg_idx, hit = self._hit_test(x, y)

        # 플레이헤드 드래그
        if hit == "playhead":
            self._drag_mode = _DragMode.PLAYHEAD_DRAG
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            return

        # 오디오 트랙 영역
        if hit == "audio_body":
            self._audio_selected = True
            self._selected_index = seg_idx
            self._selected_overlay_index = -1
            self._start_audio_drag(_DragMode.AUDIO_MOVE, x)
            self.segment_selected.emit(seg_idx)
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            return
        elif hit == "audio_left_edge":
            self._audio_selected = True
            self._selected_index = seg_idx
            self._selected_overlay_index = -1
            self._start_audio_drag(_DragMode.AUDIO_RESIZE_LEFT, x)
            self.segment_selected.emit(seg_idx)
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            return
        elif hit == "audio_right_edge":
            self._audio_selected = True
            self._selected_index = seg_idx
            self._selected_overlay_index = -1
            self._start_audio_drag(_DragMode.AUDIO_RESIZE_RIGHT, x)
            self.segment_selected.emit(seg_idx)
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            return
        
        # 비디오 클립 영역
        elif hit == "clip_body":
            self._selected_clip_index = seg_idx
            self._selected_index = -1
            self._selected_overlay_index = -1
            self.clip_selected.emit(seg_idx)
        elif hit == "clip_left_edge":
            self._selected_clip_index = seg_idx
            self._selected_index = -1
            self._selected_overlay_index = -1
            self._start_clip_drag(_DragMode.CLIP_TRIM_LEFT, seg_idx, x)
            self.clip_selected.emit(seg_idx)
        elif hit == "clip_right_edge":
            self._selected_clip_index = seg_idx
            self._selected_index = -1
            self._selected_overlay_index = -1
            self._start_clip_drag(_DragMode.CLIP_TRIM_RIGHT, seg_idx, x)
            self.clip_selected.emit(seg_idx)
        # 이미지 오버레이 영역
        elif hit == "img_left_edge":
            self._selected_overlay_index = seg_idx
            self._selected_index = -1
            self._start_image_drag(_DragMode.IMAGE_RESIZE_LEFT, seg_idx, x)
            self.image_overlay_selected.emit(seg_idx)
        elif hit == "img_right_edge":
            self._selected_overlay_index = seg_idx
            self._selected_index = -1
            self._start_image_drag(_DragMode.IMAGE_RESIZE_RIGHT, seg_idx, x)
            self.image_overlay_selected.emit(seg_idx)
        elif hit == "img_body":
            self._selected_overlay_index = seg_idx
            self._selected_index = -1
            self._start_image_drag(_DragMode.IMAGE_MOVE, seg_idx, x)
            self.image_overlay_selected.emit(seg_idx)
        # 자막/오디오 세그먼트: 같은 hit 영역(연동 이동)
        elif hit == "left_edge":
            self._audio_selected = False
            self._selected_overlay_index = -1
            self._start_drag(_DragMode.RESIZE_LEFT, seg_idx, x)
        elif hit == "right_edge":
            self._audio_selected = False
            self._selected_overlay_index = -1
            self._start_drag(_DragMode.RESIZE_RIGHT, seg_idx, x)
        elif hit == "body":
            self._audio_selected = False
            self._selected_overlay_index = -1
            self._selected_index = seg_idx
            self.segment_selected.emit(seg_idx)
            self._start_drag(_DragMode.MOVE, seg_idx, x)
        else:
            self._audio_selected = False
            self._selected_index = -1
            self._selected_overlay_index = -1
            self._drag_mode = _DragMode.SEEK
            self._seek_to_x(x)

        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x = event.position().x()
        y = event.position().y()

        # 뷰 팬 드래그 처리
        if self._drag_mode == _DragMode.PAN_VIEW:
            self._handle_pan_view(x)
            return

        # 플레이헤드 드래그 처리
        if self._drag_mode == _DragMode.PLAYHEAD_DRAG:
            self._seek_to_x(x)
            return

        # 빈 공간 시크 드래그
        if self._drag_mode == _DragMode.SEEK:
            self._seek_to_x(x)
            return

        if self._drag_mode in (_DragMode.MOVE, _DragMode.RESIZE_LEFT, _DragMode.RESIZE_RIGHT):
            self._handle_drag(x)
            return

        if self._drag_mode in (_DragMode.AUDIO_MOVE, _DragMode.AUDIO_RESIZE_LEFT, _DragMode.AUDIO_RESIZE_RIGHT):
            self._handle_audio_drag(x)
            return

        if self._drag_mode in (_DragMode.IMAGE_MOVE, _DragMode.IMAGE_RESIZE_LEFT, _DragMode.IMAGE_RESIZE_RIGHT):
            self._handle_image_drag(x)
            return

        if self._drag_mode in (_DragMode.CLIP_TRIM_LEFT, _DragMode.CLIP_TRIM_RIGHT):
            self._handle_clip_drag(x)
            return

        # 호버 시 커서 변경 (플레이헤드·가장자리·본문)
        if self._drag_mode == _DragMode.NONE:
            seg_idx, hit = self._hit_test(x, y)
            if hit == "playhead":
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
                return
            elif hit in ("left_edge", "right_edge", "img_left_edge", "img_right_edge",
                         "clip_left_edge", "clip_right_edge", "audio_left_edge", "audio_right_edge"):
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif hit in ("body", "audio_body", "img_body", "clip_body"):
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode in (_DragMode.MOVE, _DragMode.RESIZE_LEFT, _DragMode.RESIZE_RIGHT):
            if self._track and 0 <= self._drag_seg_index < len(self._track):
                seg = self._track[self._drag_seg_index]
                if seg.start_ms != self._drag_orig_start_ms or seg.end_ms != self._drag_orig_end_ms:
                    self.segment_moved.emit(self._drag_seg_index, seg.start_ms, seg.end_ms)
        elif self._drag_mode in (_DragMode.AUDIO_MOVE, _DragMode.AUDIO_RESIZE_LEFT, _DragMode.AUDIO_RESIZE_RIGHT):
            if self._track and 0 <= self._drag_seg_index < len(self._track):
                seg = self._track[self._drag_seg_index]
                if seg.audio_file and (seg.audio_start_ms != self._drag_orig_audio_start_ms or seg.audio_duration_ms != self._drag_orig_audio_duration_ms):
                    self.audio_moved.emit(seg.audio_start_ms, seg.audio_duration_ms)
        elif self._drag_mode in (_DragMode.IMAGE_MOVE, _DragMode.IMAGE_RESIZE_LEFT, _DragMode.IMAGE_RESIZE_RIGHT):
            if self._image_overlay_track and 0 <= self._drag_seg_index < len(self._image_overlay_track):
                ov = self._image_overlay_track[self._drag_seg_index]
                if ov.start_ms != self._drag_orig_start_ms or ov.end_ms != self._drag_orig_end_ms:
                    self.image_overlay_moved.emit(self._drag_seg_index, ov.start_ms, ov.end_ms)
        elif self._drag_mode in (_DragMode.CLIP_TRIM_LEFT, _DragMode.CLIP_TRIM_RIGHT):
            if self._clip_track and 0 <= self._drag_clip_index < len(self._clip_track.clips):
                clip = self._clip_track.clips[self._drag_clip_index]
                new_in = clip.source_in_ms
                new_out = clip.source_out_ms
                if new_in != self._drag_orig_source_in or new_out != self._drag_orig_source_out:
                    # Revert to original so undo command's redo() applies the change
                    clip.source_in_ms = self._drag_orig_source_in
                    clip.source_out_ms = self._drag_orig_source_out
                    self.clip_trimmed.emit(self._drag_clip_index, new_in, new_out)
            self._drag_clip_index = -1
        self._drag_mode = _DragMode.NONE
        self._drag_seg_index = -1
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def contextMenuEvent(self, event) -> None:
        """우클릭: 클립 분할/삭제, 이미지 오버레이 삭제 또는 현재 위치에 삽입."""
        if self._duration_ms <= 0:
            return
        x = event.pos().x()
        y = event.pos().y()
        menu = QMenu(self)

        # 비디오 클립 트랙 영역 우클릭
        if self._clip_track and _CLIP_Y <= y <= _CLIP_Y + _CLIP_H:
            seg_idx, hit = self._hit_test(x, y)
            if hit.startswith("clip_"):
                split_act = menu.addAction(tr("Split at Playhead (Ctrl+B)"))
                delete_act = None
                if len(self._clip_track.clips) > 1:
                    delete_act = menu.addAction(tr("Delete Clip"))
                action = menu.exec(event.globalPos())
                if action == split_act:
                    self.clip_split_requested.emit(self._playhead_ms)
                elif delete_act and action == delete_act:
                    self.clip_deleted.emit(seg_idx)
                return

        img_base_y = self._img_overlay_base_y()
        rows = self._compute_overlay_rows()
        total_h = self._img_overlay_total_h(rows)
        if img_base_y <= y <= img_base_y + total_h:
            seg_idx, hit = self._hit_test(x, y)
            if hit.startswith("img_"):
                # Size presets submenu
                size_menu = menu.addMenu(tr("Resize"))
                fit_act = size_menu.addAction(tr("Fit to Screen (Keep Ratio)"))
                fit_width_act = size_menu.addAction(tr("Fit Width"))
                fit_height_act = size_menu.addAction(tr("Fit Height"))
                full_act = size_menu.addAction(tr("Fill Screen (May Crop)"))
                size_menu.addSeparator()
                ratio_16_9_act = size_menu.addAction(tr("16:9 (Landscape)"))
                ratio_9_16_act = size_menu.addAction(tr("9:16 (Portrait)"))
                menu.addSeparator()
                delete_action = menu.addAction(tr("Delete Image Overlay"))
                action = menu.exec(event.globalPos())
                if action == delete_action:
                    self._image_overlay_track.remove_overlay(seg_idx)
                    self._selected_overlay_index = -1
                    self.update()
                elif action == fit_act:
                    self.image_overlay_resize.emit(seg_idx, "fit")
                elif action == fit_width_act:
                    self.image_overlay_resize.emit(seg_idx, "fit_width")
                elif action == fit_height_act:
                    self.image_overlay_resize.emit(seg_idx, "fit_height")
                elif action == full_act:
                    self.image_overlay_resize.emit(seg_idx, "full")
                elif action == ratio_16_9_act:
                    self.image_overlay_resize.emit(seg_idx, "16:9")
                elif action == ratio_9_16_act:
                    self.image_overlay_resize.emit(seg_idx, "9:16")
                return

        insert_action = menu.addAction(tr("Insert Image Overlay"))
        action = menu.exec(event.globalPos())
        if action == insert_action:
            ms = int(max(0, min(int(self._duration_ms), int(self._x_to_ms(x)))))
            self.insert_image_requested.emit(ms)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """휠: 줌, Ctrl+휠: 스크롤."""
        if self._duration_ms <= 0 or self._px_per_ms <= 0:
            return
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+휠: 가로 스크롤
            shift = self._visible_range_ms() * 0.1 * (-1 if delta > 0 else 1)
            self._visible_start_ms += shift
            self._clamp_visible_start(self._visible_range_ms())
        else:
            # 휠: 마우스 위치 기준 줌
            factor = 0.8 if delta > 0 else 1.25
            mouse_ms = self._x_to_ms(event.position().x())
            old_range = self._visible_range_ms()
            new_range = max(1000.0, min(float(self._duration_ms), old_range * factor))
            mouse_frac = event.position().x() / max(float(self.width()), 1.0)
            self._visible_start_ms = max(0.0, mouse_ms - new_range * mouse_frac)
            self._clamp_visible_start(new_range)
            self.zoom_changed.emit(self.get_zoom_percent())
        self._invalidate_static_cache()
        self.update()

    # -------------------------------------------------------- 드래그 헬퍼

    def _get_magnetic_snap_candidates(
        self,
        skip_seg_index: int = -1,
        skip_clip_index: int = -1,
        skip_img_index: int = -1
    ) -> list[int]:
        """자석 스냅을 위한 후보 지점(ms) 수집 (대상 별 제외 인덱스 지정)."""
        candidates = set()
        candidates.add(0)
        if self._duration_ms > 0:
            candidates.add(self._duration_ms)
        
        # Playhead
        candidates.add(self._playhead_ms)

        # Video Clips - Use indices to skip
        if self._clip_track:
            offset = 0
            for i, clip in enumerate(self._clip_track.clips):
                start = offset
                end = offset + clip.duration_ms
                offset += clip.duration_ms
                if i != skip_clip_index:
                    candidates.add(start)
                    candidates.add(end)

        # Subtitle Segments
        if self._track:
            for i, seg in enumerate(self._track):
                if i != skip_seg_index:
                    candidates.add(seg.start_ms)
                    candidates.add(seg.end_ms)
                    if seg.audio_file:
                        candidates.add(seg.audio_start_ms)
                        candidates.add(seg.audio_start_ms + seg.audio_duration_ms)

        # Image Overlays
        if self._image_overlay_track:
            for i, ov in enumerate(self._image_overlay_track):
                if i != skip_img_index:
                    candidates.add(ov.start_ms)
                    candidates.add(ov.end_ms)

        return sorted(list(candidates))

    def _apply_magnetic_snap(self, ms: int, candidates: list[int]) -> int:
        """가장 가까운 후보로 스냅 적용 (기준: 픽셀 거리)."""
        # Shift 키 누르면 스냅 일시 해제
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            self._snap_guide_x = None
            return ms

        if not self._snap_enabled or self._px_per_ms <= 0:
            self._snap_guide_x = None
            return ms
        
        # Find closest candidate
        closest_ms = -1
        min_dist_px = float('inf')
        
        # Binary search could be better but linear is fine for < 100 items
        # Optimization: Only check candidates within visible range? No, candidates outside might matter if close to edge.
        # But candidates are in ms.
        
        target_px = self._ms_to_x(ms)
        threshold_px = self._SNAP_THRESHOLD_PX

        for cand_ms in candidates:
            dist_px = abs(self._ms_to_x(cand_ms) - target_px)
            if dist_px < min_dist_px:
                min_dist_px = dist_px
                closest_ms = cand_ms

        if min_dist_px <= threshold_px:
            self._snap_guide_x = self._ms_to_x(closest_ms)
            return closest_ms
        
        self._snap_guide_x = None
        return ms

    def _get_snapped_pos(self, x: float) -> int:
        """드래그 중 스냅핑 적용된 타임라인 위치 반환."""
        ms = self._x_to_ms(x)
        # 0 ~ duration 범위 제한
        ms = max(0, min(int(self._duration_ms), int(ms)))
        
        # 프레임 스냅
        return self._snap_ms(ms)

    def _update_drag(self, x: float) -> None:
        """드래그 중 위치 업데이트 및 UI 갱신."""
        current_ms = self._x_to_ms(x)

        if self._drag_mode == _DragMode.SEEK:
            self._seek_to_x(x)

        elif self._drag_mode == _DragMode.PLAYHEAD_DRAG:
            # 플레이헤드도 스냅 적용
            candidates = self._get_magnetic_snap_candidates()
            snapped_ms = self._apply_magnetic_snap(int(current_ms), candidates)
            # 프레임 스냅도 적용할까? 자석 스냅이 우선. 자석 없으면 프레임 스냅? 
            # _apply_magnetic_snap은 스냅 안되면 원본 리턴.
            if self._snap_guide_x is None:
                 snapped_ms = self._snap_ms(int(current_ms))
            
            self._playhead_ms = max(0, min(self._duration_ms, snapped_ms))
            self.update()
            self.seek_requested.emit(self._playhead_ms)
        
        elif self._drag_mode == _DragMode.PAN_VIEW:
            # 뷰 팬: (시작점 - 현재점) 만큼 visible_start 이동
            diff_gx = self._drag_start_x - x
            diff_ms = diff_gx / self._px_per_ms if self._px_per_ms > 0 else 0
            new_start = self._drag_start_visible_ms + diff_ms
            self._visible_start_ms = max(0.0, min(float(self._duration_ms), new_start))
            self._clamp_visible_start(self._visible_range_ms())
            self._invalidate_static_cache()
            self.update()

        elif self._drag_mode == _DragMode.MOVE:
            # 자막 이동
            if not self._track or self._drag_seg_index < 0:
                return
            seg = self._track[self._drag_seg_index]
            duration = self._drag_orig_end_ms - self._drag_orig_start_ms
            
            diff_ms = current_ms - self._x_to_ms(self._drag_start_x)
            new_start = self._drag_orig_start_ms + int(diff_ms)
            
            # Snap (Target: Start or End?)
            # Both start and end can snap. We pick the one that snaps "best" (closest).
            candidates = self._get_magnetic_snap_candidates(skip_seg_index=self._drag_seg_index)
            
            # 1. Try snapping start
            snapped_start = self._apply_magnetic_snap(new_start, candidates)
            guide_x_start = self._snap_guide_x
            
            # 2. Try snapping end
            new_end_tentative = new_start + duration
            snapped_end = self._apply_magnetic_snap(new_end_tentative, candidates)
            guide_x_end = self._snap_guide_x
            
            # Which snap is closer/active?
            # If both snap, usually start takes precedence or we check which displacement is smaller.
            # actually _apply_magnetic_snap returns snapped value.
            # We calculate delta.
            
            final_start = new_start
            
            snap_diff_start = abs(snapped_start - new_start)
            snap_diff_end = abs(snapped_end - new_end_tentative)
            
            # Check threshold again implicitly via _apply_magnetic_snap return value check
            # (if no snap, it returns input).
            is_start_snap = (snapped_start != new_start)
            is_end_snap = (snapped_end != new_end_tentative)
            
            if is_start_snap and is_end_snap:
                # Both snapped. Choose closest.
                if snap_diff_start <= snap_diff_end:
                     final_start = snapped_start
                     self._snap_guide_x = guide_x_start
                else:
                     final_start = snapped_end - duration
                     self._snap_guide_x = guide_x_end
            elif is_start_snap:
                final_start = snapped_start
                self._snap_guide_x = guide_x_start
            elif is_end_snap:
                final_start = snapped_end - duration
                self._snap_guide_x = guide_x_end
            else:
                self._snap_guide_x = None
                
            # If no magnetic snap, apply frame snap
            if not is_start_snap and not is_end_snap:
                final_start = self._snap_ms(final_start)
            
            # 범위 제한
            final_start = max(0, min(self._duration_ms - duration, final_start))
            new_end = final_start + duration
            
            # 오디오도 있다면 같이 이동
            audio_offset = 0
            if seg.audio_file:
                 audio_offset = self._drag_orig_audio_start_ms - self._drag_orig_start_ms

            seg.start_ms = final_start
            seg.end_ms = new_end
            
            if seg.audio_file:
                seg.audio_start_ms = final_start + audio_offset
                
            self.segment_moved.emit(self._drag_seg_index, final_start, new_end)
            if seg.audio_file:
                self.audio_moved.emit(seg.audio_start_ms, self._drag_orig_audio_duration_ms)
                
            self._invalidate_static_cache()
            self.update()

        elif self._drag_mode == _DragMode.RESIZE_LEFT:
            if not self._track or self._drag_seg_index < 0:
                return
            seg = self._track[self._drag_seg_index]
            
            limit_right = seg.end_ms - 100
            
            new_start = int(current_ms)
            
            candidates = self._get_magnetic_snap_candidates(skip_seg_index=self._drag_seg_index)
            new_start = self._apply_magnetic_snap(new_start, candidates)
            
            if self._snap_guide_x is None:
                new_start = self._snap_ms(new_start)
                
            new_start = max(0, min(limit_right, new_start))
            
            seg.start_ms = new_start
            self.segment_moved.emit(self._drag_seg_index, new_start, seg.end_ms)
            self._invalidate_static_cache()
            self.update()

        elif self._drag_mode == _DragMode.RESIZE_RIGHT:
            if not self._track or self._drag_seg_index < 0:
                return
            seg = self._track[self._drag_seg_index]
            
            limit_left = seg.start_ms + 100
            
            new_end = int(current_ms)
            
            candidates = self._get_magnetic_snap_candidates(skip_seg_index=self._drag_seg_index)
            new_end = self._apply_magnetic_snap(new_end, candidates)

            if self._snap_guide_x is None:
                 new_end = self._snap_ms(new_end)

            new_end = max(limit_left, min(self._duration_ms, new_end))
            
            seg.end_ms = new_end
            self.segment_moved.emit(self._drag_seg_index, seg.start_ms, new_end)
            self._invalidate_static_cache()
            self.update()
            
        elif self._drag_mode == _DragMode.AUDIO_MOVE:
             if not self._track or self._drag_seg_index < 0:
                return
             seg = self._track[self._drag_seg_index]
             if not seg.audio_file:
                 return
                 
             diff_ms = current_ms - self._x_to_ms(self._drag_start_x)
             new_audio_start = self._drag_orig_audio_start_ms + int(diff_ms)
             
             candidates = self._get_magnetic_snap_candidates(skip_seg_index=self._drag_seg_index)
             
             # Audio move snaps its start / end
             # Try snap start
             snapped_start = self._apply_magnetic_snap(new_audio_start, candidates)
             guide_x_start = self._snap_guide_x

             # Try snap end
             new_audio_end = new_audio_start + self._drag_orig_audio_duration_ms
             snapped_end = self._apply_magnetic_snap(new_audio_end, candidates)
             guide_x_end = self._snap_guide_x
             
             is_start_snap = (snapped_start != new_audio_start)
             is_end_snap = (snapped_end != new_audio_end)
             
             if is_start_snap and is_end_snap:
                 if abs(snapped_start - new_audio_start) <= abs(snapped_end - new_audio_end):
                     new_audio_start = snapped_start
                     self._snap_guide_x = guide_x_start
                 else:
                     new_audio_start = snapped_end - self._drag_orig_audio_duration_ms
                     self._snap_guide_x = guide_x_end
             elif is_start_snap:
                 new_audio_start = snapped_start
                 self._snap_guide_x = guide_x_start
             elif is_end_snap:
                 new_audio_start = snapped_end - self._drag_orig_audio_duration_ms
                 self._snap_guide_x = guide_x_end
             else:
                 self._snap_guide_x = None
                 new_audio_start = self._snap_ms(new_audio_start)
             
             new_audio_start = max(0, min(self._duration_ms - self._drag_orig_audio_duration_ms, new_audio_start))
             
             seg.audio_start_ms = new_audio_start
             self.audio_moved.emit(new_audio_start, self._drag_orig_audio_duration_ms)
             self._invalidate_static_cache()
             self.update()
        
        elif self._drag_mode == _DragMode.AUDIO_RESIZE_LEFT:
            if not self._track or self._drag_seg_index < 0:
                return
            
            candidates = self._get_magnetic_snap_candidates(skip_seg_index=self._drag_seg_index)
            
            diff_ms = int((x - self._drag_start_x) / self._px_per_ms) if self._px_per_ms > 0 else 0
            new_start = self._drag_orig_audio_start_ms + diff_ms
            
            new_start = self._apply_magnetic_snap(new_start, candidates)
            if self._snap_guide_x is None:
                new_start = self._snap_ms(new_start)
                
            new_start = max(0, min(new_start, self._track.audio_start_ms + self._track.audio_duration_ms - 100))
            
            duration_change = self._track.audio_start_ms - new_start
            self._track.audio_start_ms = new_start
            self._track.audio_duration_ms += duration_change
            self._invalidate_static_cache()
            self.update()

        elif self._drag_mode == _DragMode.AUDIO_RESIZE_RIGHT:
            if not self._track or self._drag_seg_index < 0:
                return
            
            candidates = self._get_magnetic_snap_candidates(skip_seg_index=self._drag_seg_index)
            
            # Calc new duration directly ? No use dx
            dx_ms = int((x - self._drag_start_x) / self._px_per_ms) if self._px_per_ms > 0 else 0
            new_duration = self._drag_orig_audio_duration_ms + dx_ms
            new_end = self._track.audio_start_ms + new_duration
            
            new_end = self._apply_magnetic_snap(new_end, candidates)
            if self._snap_guide_x is None:
                 new_end = self._snap_ms(new_end)
            
            new_duration = new_end - self._track.audio_start_ms
            new_duration = max(100, new_duration)
            max_duration = self._duration_ms - self._track.audio_start_ms
            self._track.audio_duration_ms = min(new_duration, max_duration)
            self._invalidate_static_cache()
            self.update()

        elif self._drag_mode == _DragMode.IMAGE_MOVE:
            if not self._image_overlay_track or self._drag_seg_index < 0:
                return
            ov = self._image_overlay_track[self._drag_seg_index]
            duration = self._drag_orig_end_ms - self._drag_orig_start_ms
            
            diff_ms = current_ms - self._x_to_ms(self._drag_start_x)
            new_start = self._drag_orig_start_ms + int(diff_ms)
            
            candidates = self._get_magnetic_snap_candidates(skip_img_index=self._drag_seg_index)
            
            snapped_start = self._apply_magnetic_snap(new_start, candidates)
            guide_x_start = self._snap_guide_x

            new_end_tentative = new_start + duration
            snapped_end = self._apply_magnetic_snap(new_end_tentative, candidates)
            guide_x_end = self._snap_guide_x
            
            is_start_snap = (snapped_start != new_start)
            is_end_snap = (snapped_end != new_end_tentative)
            
            final_start = new_start
            if is_start_snap and is_end_snap:
                if abs(snapped_start - new_start) <= abs(snapped_end - new_end_tentative):
                    final_start = snapped_start
                    self._snap_guide_x = guide_x_start
                else:
                    final_start = snapped_end - duration
                    self._snap_guide_x = guide_x_end
            elif is_start_snap:
                final_start = snapped_start
                self._snap_guide_x = guide_x_start
            elif is_end_snap:
                final_start = snapped_end - duration
                self._snap_guide_x = guide_x_end
            else:
                self._snap_guide_x = None
                final_start = self._snap_ms(final_start)
            
            final_start = max(0, min(self._duration_ms - duration, final_start))
            
            ov.start_ms = final_start
            ov.end_ms = final_start + duration
            
            self.image_overlay_moved.emit(self._drag_seg_index, ov.start_ms, ov.end_ms)
            self._invalidate_static_cache()
            self.update()

        elif self._drag_mode == _DragMode.IMAGE_RESIZE_LEFT:
            if not self._image_overlay_track or self._drag_seg_index < 0:
                return
            ov = self._image_overlay_track[self._drag_seg_index]
            
            limit_right = ov.end_ms - 100
            
            new_start = int(current_ms)
            
            candidates = self._get_magnetic_snap_candidates(skip_img_index=self._drag_seg_index)
            new_start = self._apply_magnetic_snap(new_start, candidates)
            
            if self._snap_guide_x is None:
                new_start = self._snap_ms(new_start)
                
            new_start = max(0, min(limit_right, new_start))
            
            ov.start_ms = new_start
            self.image_overlay_moved.emit(self._drag_seg_index, ov.start_ms, ov.end_ms)
            self._invalidate_static_cache()
            self.update()

        elif self._drag_mode == _DragMode.IMAGE_RESIZE_RIGHT:
            if not self._image_overlay_track or self._drag_seg_index < 0:
                return
            ov = self._image_overlay_track[self._drag_seg_index]
            
            limit_left = ov.start_ms + 100
            
            new_end = int(current_ms)
            
            candidates = self._get_magnetic_snap_candidates(skip_img_index=self._drag_seg_index)
            new_end = self._apply_magnetic_snap(new_end, candidates)
            
            if self._snap_guide_x is None:
                new_end = self._snap_ms(new_end)
                
            new_end = max(limit_left, min(self._duration_ms, new_end))
            
            ov.end_ms = new_end
            self.image_overlay_moved.emit(self._drag_seg_index, ov.start_ms, ov.end_ms)
            self._invalidate_static_cache()
            self.update()

    def _start_clip_drag(self, mode: _DragMode, clip_idx: int, x: float) -> None:
        """비디오 클립 트림 드래그 시작."""
        self._drag_mode = mode
        self._drag_clip_index = clip_idx
        self._drag_start_x = x
        if self._clip_track and 0 <= clip_idx < len(self._clip_track.clips):
            clip = self._clip_track.clips[clip_idx]
            self._drag_orig_source_in = clip.source_in_ms
            self._drag_orig_source_out = clip.source_out_ms
        self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def _handle_clip_drag(self, x: float) -> None:
        """비디오 클립 트림 처리."""
        if not self._clip_track or self._drag_clip_index < 0:
            return
        if self._drag_clip_index >= len(self._clip_track.clips):
            return

        dx_ms = int((x - self._drag_start_x) / self._px_per_ms) if self._px_per_ms > 0 else 0
        clip = self._clip_track.clips[self._drag_clip_index]

        if self._drag_mode == _DragMode.CLIP_TRIM_LEFT:
            new_in = max(0, self._drag_orig_source_in + dx_ms)
            new_in = min(new_in, clip.source_out_ms - 100)  # min 100ms
            clip.source_in_ms = new_in
        elif self._drag_mode == _DragMode.CLIP_TRIM_RIGHT:
            new_out = max(clip.source_in_ms + 100, self._drag_orig_source_out + dx_ms)
            clip.source_out_ms = new_out

        self._invalidate_static_cache()
        self.update()

    def _start_audio_drag(self, mode: _DragMode, x: float) -> None:
        """오디오 트랙 드래그 시작."""
        self._drag_mode = mode
        self._drag_start_x = x
        if self._track:
            self._drag_orig_audio_start_ms = self._track.audio_start_ms
            self._drag_orig_audio_duration_ms = self._track.audio_duration_ms

    def _handle_audio_drag(self, x: float) -> None:
        """오디오 트랙 이동/리사이즈 처리."""
        if not self._track:
            return

        dx_ms = int((x - self._drag_start_x) / self._px_per_ms) if self._px_per_ms > 0 else 0

        if self._drag_mode == _DragMode.AUDIO_MOVE:
            new_start = self._snap_ms(max(0, self._drag_orig_audio_start_ms + dx_ms))
            if new_start + self._drag_orig_audio_duration_ms > self._duration_ms:
                new_start = self._duration_ms - self._drag_orig_audio_duration_ms
            self._track.audio_start_ms = max(0, new_start)
        elif self._drag_mode == _DragMode.AUDIO_RESIZE_LEFT:
            new_start = self._snap_ms(max(0, self._drag_orig_audio_start_ms + dx_ms))
            new_start = min(new_start, self._track.audio_start_ms + self._track.audio_duration_ms - 100)
            duration_change = self._track.audio_start_ms - new_start
            self._track.audio_start_ms = new_start
            self._track.audio_duration_ms += duration_change
        elif self._drag_mode == _DragMode.AUDIO_RESIZE_RIGHT:
            new_duration = max(100, self._drag_orig_audio_duration_ms + dx_ms)
            max_duration = self._duration_ms - self._track.audio_start_ms
            self._track.audio_duration_ms = min(new_duration, max_duration)

        self._invalidate_static_cache()
        self.update()

    def _hit_test(self, x: float, y: float) -> tuple[int, str]:
        """(x,y)에 해당하는 (세그먼트 인덱스, 히트 영역) 반환. 없으면 (-1, '')."""
        # 플레이헤드 우선 (클릭 편하게 넓은 히트 영역)
        playhead_x = self._ms_to_x(self._playhead_ms)
        if abs(x - playhead_x) <= _PLAYHEAD_HIT_PX:
            return -3, "playhead"

        # 비디오 클립 트랙
        if self._clip_track and _CLIP_Y <= y <= _CLIP_Y + _CLIP_H:
            offset = 0
            for i, clip in enumerate(self._clip_track.clips):
                x1 = self._ms_to_x(offset)
                x2 = self._ms_to_x(offset + clip.duration_ms)
                offset += clip.duration_ms
                if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                    continue
                if abs(x - x1) <= _EDGE_PX and i > 0:
                    return i, "clip_left_edge"
                if abs(x - x2) <= _EDGE_PX and i < len(self._clip_track.clips) - 1:
                    return i, "clip_right_edge"
                if x1 <= x <= x2:
                    return i, "clip_body"

        # 이미지 오버레이 세그먼트 (row 별 y 좌표 계산)
        if self._image_overlay_track and len(self._image_overlay_track) > 0:
            img_base_y = self._img_overlay_base_y()
            rows = self._compute_overlay_rows()
            total_h = self._img_overlay_total_h(rows)
            if img_base_y <= y <= img_base_y + total_h:
                for i, ov in enumerate(self._image_overlay_track):
                    row = rows[i]
                    ov_y = img_base_y + row * (self._IMG_ROW_H + self._IMG_ROW_GAP)
                    if not (ov_y <= y <= ov_y + self._IMG_ROW_H):
                        continue
                    x1 = self._ms_to_x(ov.start_ms)
                    x2 = self._ms_to_x(ov.end_ms)
                    if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                        continue
                    if abs(x - x1) <= _EDGE_PX:
                        return i, "img_left_edge"
                    if abs(x - x2) <= _EDGE_PX:
                        return i, "img_right_edge"
                    if x1 <= x <= x2:
                        return i, "img_body"

        if not self._track:
            return -1, ""

        # 오디오 세그먼트 (자막과 동일 인덱스로 연동)
        audio_y = _AUDIO_Y
        audio_h = _AUDIO_H
        if audio_y <= y <= audio_y + audio_h:
            for i, seg in enumerate(self._track):
                if not seg.audio_file:
                    continue
                x1 = self._ms_to_x(seg.start_ms)
                x2 = self._ms_to_x(seg.end_ms)
                if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                    continue
                if abs(x - x1) <= _EDGE_PX:
                    return i, "left_edge"
                if abs(x - x2) <= _EDGE_PX:
                    return i, "right_edge"
                if x1 <= x <= x2:
                    return i, "body"

        # 자막 세그먼트
        seg_y = _SEG_Y
        seg_h = _SEG_H
        if seg_y <= y <= seg_y + seg_h:
            for i, seg in enumerate(self._track):
                x1 = self._ms_to_x(seg.start_ms)
                x2 = self._ms_to_x(seg.end_ms)
                if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                    continue
                if abs(x - x1) <= _EDGE_PX:
                    return i, "left_edge"
                if abs(x - x2) <= _EDGE_PX:
                    return i, "right_edge"
                if x1 <= x <= x2:
                    return i, "body"
        return -1, ""

    # ----------------------------------------------------------- 유틸

    def _visible_range_ms(self) -> float:
        if self._px_per_ms > 0:
            return self.width() / self._px_per_ms
        return float(self._duration_ms) if self._duration_ms > 0 else 1.0

    def _ms_to_x(self, ms: float) -> float:
        return (ms - self._visible_start_ms) * self._px_per_ms

    def _x_to_ms(self, x: float) -> float:
        if self._px_per_ms <= 0:
            # 0 반환 시 의도치 않은 시크 방지 → 현재 플레이헤드 반환
            return float(self._playhead_ms)
        return self._visible_start_ms + x / self._px_per_ms

    def _seek_to_x(self, x: float) -> None:
        ms = int(max(0, min(int(self._duration_ms), int(self._x_to_ms(x)))))
        self._playhead_ms = ms
        self.update()
        self.seek_requested.emit(ms)

    def _clamp_visible_start(self, visible_range: float) -> None:
        self._visible_start_ms = max(0.0, self._visible_start_ms)
        max_start = max(0.0, float(self._duration_ms) - visible_range)
        self._visible_start_ms = min(self._visible_start_ms, max_start)

    @staticmethod
    def _nice_tick_interval(visible_ms: float) -> int:
        target_ticks = 8
        raw = visible_ms / target_ticks
        candidates = [
            500, 1000, 2000, 5000, 10000, 15000, 30000,
            60000, 120000, 300000, 600000,
        ]
        for c in candidates:
            if c >= raw:
                return c
        return candidates[-1]

    # -------------------------------------------------------- 드래그 앤 드롭

    def _is_valid_media_drop(self, event) -> bool:
        """미디어 드롭 가능 여부 확인."""
        mime = event.mimeData()
        if not (mime.hasUrls() and mime.urls()):
            return False
        # Allow video drops even when no video loaded (will load as primary)
        if self._duration_ms <= 0:
            media_type = bytes(mime.data("application/x-fmm-media-type")).decode("utf-8", errors="ignore")
            if media_type == "video":
                return True
            # Also check file extension
            from pathlib import Path
            from src.utils.config import VIDEO_EXTENSIONS
            url = mime.urls()[0]
            suffix = Path(url.toLocalFile()).suffix.lower()
            return suffix in VIDEO_EXTENSIONS
        return True

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._is_valid_media_drop(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._is_valid_media_drop(event):
            self._drop_indicator_x = event.position().x()
            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._drop_indicator_x = -1
        self.update()

    def dropEvent(self, event: QDropEvent) -> None:
        self._drop_indicator_x = -1
        mime = event.mimeData()
        if not mime.hasUrls() or not mime.urls():
            event.ignore()
            return

        from pathlib import Path
        from src.utils.config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

        url = mime.urls()[0]
        file_path = url.toLocalFile()
        if not file_path:
            event.ignore()
            return

        suffix = Path(file_path).suffix.lower()
        if self._duration_ms > 0:
            position_ms = int(max(0, min(int(self._duration_ms), int(self._x_to_ms(event.position().x())))))
        else:
            position_ms = 0

        if suffix in IMAGE_EXTENSIONS:
            self.image_file_dropped.emit(file_path, position_ms)
            event.acceptProposedAction()
        elif suffix in VIDEO_EXTENSIONS:
            self.video_file_dropped.emit(file_path, position_ms)
            event.acceptProposedAction()
        else:
            event.ignore()

        self.update()

    def _draw_drop_indicator(self, painter: QPainter, h: int) -> None:
        """드롭 위치 표시 (세로 점선)."""
        if self._drop_indicator_x < 0:
            return
        pen = QPen(QColor(0, 188, 212), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        x = int(self._drop_indicator_x)
        painter.drawLine(x, 0, x, h)
