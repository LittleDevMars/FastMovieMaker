"""커스텀 페인팅 타임라인 위젯: 자막 블록, 플레이헤드, 오디오/이미지 오버레이 표시."""

from __future__ import annotations

from enum import Enum, auto

from src.utils.i18n import tr

from PySide6.QtCore import Qt, Signal, QPoint, QRectF, Slot
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
from src.models.video_clip import VideoClip, VideoClipTrack
from src.services.waveform_service import WaveformData
from src.services.timeline_waveform_service import TimelineWaveformService
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
    TEXT_MOVE = auto()
    TEXT_RESIZE_LEFT = auto()
    TEXT_RESIZE_RIGHT = auto()
    VOLUME_POINT_MOVE = auto()
    BGM_MOVE = auto()
    BGM_RESIZE_LEFT = auto()
    BGM_RESIZE_RIGHT = auto()


# 세그먼트 가장자리에서 리사이즈로 인식하는 픽셀 거리
_EDGE_PX = 6
# 플레이헤드 드래그로 인식하는 픽셀 거리 (클릭 쉽게 넓게)
_PLAYHEAD_HIT_PX = 20

# ---- Track Y-positions ----
_RULER_H = 14
_CLIP_Y = 16
_CLIP_H = 32
_SEG_H = 40
_AUDIO_H = 34
_WAVEFORM_H = 45
_BGM_H = 34

# Helper methods for dynamic Y (to be placed in TimelineWidget)


class TimelineWidget(QWidget):
    """타임라인 바: 자막/오디오/이미지 오버레이 세그먼트, 줌·스크롤, 클릭 시크, 드래그 이동·리사이즈."""

    seek_requested = Signal(int)  # ms
    segment_selected = Signal(int)  # 세그먼트 인덱스
    segment_moved = Signal(int, int, int)  # (index, new_start_ms, new_end_ms)
    audio_moved = Signal(int, int)  # (new_start_ms, new_duration_ms)
    image_overlay_selected = Signal(int)  # 오버레이 인덱스
    image_overlay_moved = Signal(int, int, int)  # (index, new_start_ms, new_end_ms)
    image_overlay_resize = Signal(int, str)  # (index, mode: "fit_width"/"full"/"16:9"/"9:16")
    text_overlay_selected = Signal(int)  # 텍스트 오버레이 인덱스
    text_overlay_moved = Signal(int, int, int)  # (index, new_start_ms, new_end_ms)
    insert_image_requested = Signal(int)  # 이미지 삽입 위치(ms)
    insert_text_requested = Signal(int)  # 텍스트 오버레이 삽입 위치(ms)
    image_file_dropped = Signal(str, int)  # (file_path, position_ms)
    video_file_dropped = Signal(str, int)  # (file_path, position_ms)
    audio_file_dropped = Signal(str, int)  # (file_path, position_ms)
    clip_selected = Signal(int, int)            # (track_index, clip_index)
    clip_split_requested = Signal(int)          # (timeline_ms) - No track index needed usually as it splits all or current? 
                                                # Actually better to track-specific: 
                                                # self.clip_split_requested.emit(track_idx, timeline_ms)
    clip_deleted = Signal(int, int)             # (track_index, clip_index)
    clip_speed_requested = Signal(int, int)     # (track_index, clip_index)
    clip_trimmed = Signal(int, int, int, int)   # (track_index, clip_index, new_source_in, new_source_out)
    transition_requested = Signal(int, int)     # (track_index, clip_index)
    bgm_clip_selected = Signal(int, int)        # (track_index, clip_index)
    bgm_clip_moved = Signal(int, int, int)      # (track_index, clip_index, new_start_ms)
    bgm_clip_trimmed = Signal(int, int, int, int) # (track_index, clip_index, new_start_ms, new_dur_ms)
    bgm_clip_delete_requested = Signal(int, int) # (track_index, clip_index)
    
    # Text overlay signals
    text_overlay_selected = Signal(int)  # overlay index
    text_overlay_edit_requested = Signal(int)  # overlay index
    text_overlay_delete_requested = Signal(int)  # overlay index
    text_overlay_moved = Signal(int, int, int)  # (index, old_start_ms, new_start_ms)

    clip_volume_requested = Signal(int, int)   # (track_index, clip_index)

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
    
    # BGM Tracks (Deep Purple/Blue Gradient)
    _BGM_COLOR_TOP = QColor(100, 80, 200)
    _BGM_COLOR_BOT = QColor(60, 40, 160)
    _BGM_BORDER = QColor(130, 100, 240)
    _BGM_SELECTED_BORDER = QColor(100, 220, 255)
    _BGM_SELECTED_COLOR = QColor(40, 20, 100)

    # Video Audio / Waveform (Orange)
    _WAVEFORM_FILL = QColor(255, 140, 40, 120)
    _WAVEFORM_EDGE = QColor(255, 180, 80, 200)
    _WAVEFORM_CENTER = QColor(255, 220, 150) # Bright center line
    _VIDEO_AUDIO_BORDER = QColor(255, 160, 60)
    _VIDEO_AUDIO_COLOR = QColor(255, 140, 40, 50) # Fallback background
    
    # Audio Envelope (Rubber Banding)
    _VOLUME_LINE_COLOR = QColor(255, 255, 255, 200)
    _VOLUME_POINT_COLOR = QColor(255, 255, 255)
    _VOLUME_POINT_RADIUS = 4
    
    # Image Overlays (Purple Gradient)
    _IMG_OVERLAY_COLOR_TOP = QColor(160, 90, 220)
    _IMG_OVERLAY_COLOR_BOT = QColor(120, 60, 180)
    _IMG_OVERLAY_BORDER = QColor(190, 120, 240)
    _IMG_OVERLAY_SELECTED_BORDER = QColor(100, 220, 255)
    _IMG_OVERLAY_SELECTED_COLOR = QColor(0, 100, 140)

    # Image Overlay Layout
    _IMG_ROW_H = 40
    _IMG_ROW_GAP = 4

    # Text Overlay Colors (Orange)
    _TEXT_OVERLAY_COLOR = QColor(255, 180, 80, 180)
    _TEXT_OVERLAY_BORDER = QColor(255, 200, 120)
    _TEXT_OVERLAY_SELECTED_COLOR = QColor(255, 140, 40)
    _TEXT_OVERLAY_SELECTED_BORDER = QColor(255, 220, 160)

    # Text Overlay Layout
    _TEXT_ROW_H = 28
    _TEXT_ROW_GAP = 4

    # Video Clips (Teal/Varied Gradient)
    # Default clip colors
    _CLIP_COLOR_TOP = QColor(0, 160, 160)
    _CLIP_COLOR_BOT = QColor(0, 120, 120)
    _CLIP_BORDER = QColor(0, 200, 200)
    _CLIP_SPLIT_LINE = QColor(255, 255, 255, 180) # Solid, visible split line
    
    # Transition Markers (Yellow/Gold)
    _TRANSITION_MARKER_COLOR = QColor(255, 215, 0, 180) # Gold semi-transparent
    
    # Selected Clip Colors
    _CLIP_SELECTED_BORDER = QColor(100, 220, 255)     # Cyan
    _CLIP_SELECTED_COLOR = QColor(0, 100, 140)        # Dark Cyan Body

    # Thumbnail Layout - LOD System
    # (min_px_per_ms, thumbnail_interval_px, min_clip_width_px)
    _LOD_LEVELS = [
        (0.5,   200,  50),   # LOD 0: Very zoomed out - wide spacing
        (0.1,   100,  30),   # LOD 1: Normal - default spacing
        (0.05,  50,   20),   # LOD 2: Zoomed in - narrow spacing
        (0.0,   25,   10),   # LOD 3: Very zoomed in - very narrow spacing
    ]

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

        self.setStyleSheet("""
            TimelineWidget {
                background-color: rgb(30, 30, 30);
                border-top: 1px solid rgb(50, 50, 50);
            }
        """)

        self._project = None
        self._primary_video_path: str | None = None  # Path to primary video for thumbnails

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

        # 텍스트 오버레이 트랙
        self._text_overlay_track = None  # TextOverlayTrack | None
        self._selected_text_overlay_index: int = -1
        self._drag_text_index: int = -1
        self._drag_text_orig_start_ms: int = 0
        self._drag_text_orig_end_ms: int = 0

        # 비디오 클립 트랙
        self._clip_track: VideoClipTrack | None = None
        self._selected_clip_track_index: int = -1
        self._selected_clip_index: int = -1
        self._drag_clip_track_index: int = -1
        self._drag_clip_index: int = -1
        self._drag_orig_source_in: int = 0
        self._drag_orig_source_out: int = 0

        # BGM 트랙 상태
        self._bgm_tracks: list = [] # AudioTrack list
        self._selected_bgm_track_index: int = -1
        self._selected_bgm_clip_index: int = -1
        self._drag_bgm_track_index: int = -1
        self._drag_bgm_clip_index: int = -1
        self._drag_bgm_orig_start_ms: int = 0
        self._drag_bgm_orig_duration_ms: int = 0

        # 프레임 스냅 FPS (0 = 비활성화)
        self._snap_fps: int = 0
        
        # 자석 스냅 상태
        self._snap_enabled: bool = True
        self._snap_guide_x: float | None = None

        # 웨이브폼 서비스 및 데이터 캐시
        self._waveform_service = None
        self._waveform_data = None  # Global project waveform (legacy)
        self._waveform_image_cache = None
        self._waveform_cache_key = None
        self._waveform_image_cache: QImage | None = None
        self._waveform_cache_key: tuple | None = None
        
        # Envelope Dragging
        self._drag_volume_point_idx: int = -1
        self._drag_clip_ref = None

        # 썸네일 서비스
        from src.services.timeline_thumbnail_service import TimelineThumbnailService
        self._thumbnail_service = TimelineThumbnailService(self)
        self._thumbnail_service.thumbnail_ready.connect(self.update)

        # 리플 편집 모드
        self._ripple_enabled: bool = False

        # 정적 레이어 캐시 (눈금자+세그먼트+오디오+이미지+웨이브폼)
        self._static_cache: QPixmap | None = None
        self._static_cache_key: tuple | None = None

        # 드롭 표시
        self._drop_indicator_x: float = -1

    def _get_thumbnail_interval(self) -> int:
        """Get thumbnail interval based on current zoom level (LOD)."""
        for min_zoom, interval, _ in self._LOD_LEVELS:
            if self._px_per_ms >= min_zoom:
                return interval
        return self._LOD_LEVELS[-1][1]  # Most zoomed in

    def _should_draw_thumbnails(self, clip_width_px: float) -> bool:
        """Check if clip is wide enough to draw thumbnails at current zoom."""
        for min_zoom, _, min_width in self._LOD_LEVELS:
            if self._px_per_ms >= min_zoom:
                return clip_width_px >= min_width
        return clip_width_px >= self._LOD_LEVELS[-1][2]

    # -------------------------------------------------------- Y Layout
    def _video_track_y(self, track_index: int) -> int:
        return _CLIP_Y + (track_index * _CLIP_H)

    def _get_num_img_rows(self) -> int:
        rows = self._compute_overlay_rows()
        return max(rows) + 1 if rows else 1

    def _get_num_text_rows(self) -> int:
        rows = self._compute_text_overlay_rows()
        return max(rows) + 1 if rows else 1

    def _subtitle_track_y(self) -> int:
        num_v = len(self._project.video_tracks) if self._project else 1
        return _CLIP_Y + (num_v * _CLIP_H) + 4

    def _audio_track_y(self) -> int:
        return self._subtitle_track_y() + _SEG_H + 4

    def _img_overlay_base_y(self) -> int:
        return self._audio_track_y() + _AUDIO_H + 4

    def _waveform_y(self) -> int:
        """Calculate Y position for waveform display."""
        num_v = len(self._project.video_tracks) if self._project else 1
        return _CLIP_Y + (num_v * _CLIP_H) + 4

    def _bgm_track_base_y(self) -> int:
        num_text_rows = self._get_num_text_rows() if hasattr(self, "_get_num_text_rows") else 1
        return self._text_overlay_base_y() + num_text_rows * (self._TEXT_ROW_H + self._TEXT_ROW_GAP) + 8

    def _bgm_track_y(self, track_index: int) -> int:
        return self._bgm_track_base_y() + track_index * (_BGM_H + 4)

    # -------------------------------------------------------- 공개 API

    def set_project(self, project) -> None:
        """Set the current project and refresh."""
        self._project = project
        self._clip_track = project.video_clip_track
        self._track = project.subtitle_track
        self._image_overlay_track = project.image_overlay_track
        self._bgm_tracks = getattr(project, "bgm_tracks", [])
        self._duration_ms = project.duration_ms
        self._has_video = project.has_video
        self._invalidate_static_cache()
        self.update()

    def set_waveform_service(self, service: TimelineWaveformService | None) -> None:
        """Set the waveform service and connect signals."""
        if self._waveform_service:
            try:
                self._waveform_service.waveform_ready.disconnect(self._on_waveform_ready)
            except (TypeError, RuntimeError):
                pass
        self._waveform_service = service
        if self._waveform_service:
            self._waveform_service.waveform_ready.connect(self._on_waveform_ready)
        self.update()

    @Slot(str, object)
    def _on_waveform_ready(self, source_path: str, data: WaveformData) -> None:
        """Handle waveform ready signal from service."""
        self.update()

    def set_primary_video_path(self, path: str | None) -> None:
        """Set the primary video path for thumbnail generation."""
        self._primary_video_path = path
        self.update()

    def set_clip_track(self, track: VideoClipTrack | None) -> None:
        """Set the current active video clip track."""
        self._clip_track = track
        self._selected_clip_index = -1
        self._invalidate_static_cache()
        self.update()

    def set_snap_fps(self, fps: int) -> None:
        """Set FPS for frame snapping during drag. 0 = disabled."""
        self._snap_fps = fps

    def toggle_magnetic_snap(self) -> bool:
        """Toggle magnetic snap state."""
        self._snap_enabled = not self._snap_enabled
        # Clear any existing snap guide
        self._snap_guide_x = None
        self.update()
        return self._snap_enabled

    def is_magnetic_snap_enabled(self) -> bool:
        return self._snap_enabled

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

    def set_bgm_tracks(self, tracks: list) -> None:
        """BGM 트랙 데이터 설정."""
        self._bgm_tracks = tracks
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

    def set_text_overlay_track(self, track) -> None:
        """Set the text overlay track for timeline display."""
        self._text_overlay_track = track
        self._selected_text_overlay_index = -1
        self._invalidate_static_cache()
        self.update()

    def select_text_overlay(self, index: int) -> None:
        """Select a text overlay by index."""
        self._selected_text_overlay_index = index
        self._invalidate_static_cache()
        self.update()

    def _start_text_drag(self, mode: _DragMode, index: int, x: float) -> None:
        """Initialize text overlay drag operation."""
        if not self._text_overlay_track or index < 0 or index >= len(self._text_overlay_track.overlays):
            return
        
        overlay = self._text_overlay_track.overlays[index]
        self._drag_mode = mode
        self._drag_text_index = index
        self._drag_start_x = x
        self._drag_text_orig_start_ms = overlay.start_ms
        self._drag_text_orig_end_ms = overlay.end_ms
        
        if mode == _DragMode.TEXT_MOVE:
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def _handle_text_drag(self, x: float) -> None:
        """Handle text overlay drag operations."""
        if not self._text_overlay_track or self._drag_text_index < 0:
            return
        if self._drag_text_index >= len(self._text_overlay_track.overlays):
            return
        
        overlay = self._text_overlay_track.overlays[self._drag_text_index]
        dx_ms = int((x - self._drag_start_x) / self._px_per_ms) if self._px_per_ms > 0 else 0
        
        if self._drag_mode == _DragMode.TEXT_MOVE:
            # Move entire overlay
            new_start = max(0, self._drag_text_orig_start_ms + dx_ms)
            duration = self._drag_text_orig_end_ms - self._drag_text_orig_start_ms
            overlay.start_ms = int(new_start)
            overlay.end_ms = int(new_start + duration)
        elif self._drag_mode == _DragMode.TEXT_RESIZE_LEFT:
            # Resize left edge
            new_start = max(0, self._drag_text_orig_start_ms + dx_ms)
            if new_start < self._drag_text_orig_end_ms - 100:  # Min 100ms duration
                overlay.start_ms = int(new_start)
        elif self._drag_mode == _DragMode.TEXT_RESIZE_RIGHT:
            # Resize right edge
            new_end = max(self._drag_text_orig_start_ms + 100, self._drag_text_orig_end_ms + dx_ms)
            overlay.end_ms = int(new_end)
        
        self._invalidate_static_cache()
        self.update()

    def _handle_image_drag(self, x: float) -> None:
        """Handle image overlay drag operations."""
        # Placeholder - implement similar to text drag if needed
        pass

    def select_clip(self, track_index: int, clip_index: int) -> None:
        self._selected_clip_track_index = track_index
        self._selected_clip_index = clip_index
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
        self._waveform_service = None
        self._waveform_data = None  # Global project waveform (legacy)
        self._waveform_image_cache = None
        self._waveform_cache_key = None
        self._invalidate_static_cache()
        self.update()

    def set_ripple_mode(self, enabled: bool) -> None:
        """Set ripple edit mode."""
        self._ripple_enabled = enabled
        self.update()

    def is_ripple_mode(self) -> bool:
        """Return True if ripple edit mode is enabled."""
        return self._ripple_enabled

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
        # Hidden track states
        v_h = self._clip_track.hidden if self._clip_track else False
        s_h = self._track.hidden if self._track else False
        o_h = self._image_overlay_track.hidden if self._image_overlay_track else False

        cache_key = (
            w, h, self._visible_start_ms, visible_ms,
            self._selected_index, self._selected_overlay_index,
            self._selected_clip_index, clip_count,
            seg_count, ovl_count, self._has_video,
            id(self._waveform_data),
            v_h, s_h, o_h
        )

        if self._static_cache_key != cache_key or self._static_cache is None:
            # 정적 레이어를 QPixmap에 렌더링
            pixmap = QPixmap(w, h)
            pp = QPainter(pixmap)
            pp.setRenderHint(QPainter.RenderHint.Antialiasing)
            pp.fillRect(0, 0, w, h, self._BG_COLOR)

            self._draw_ruler(pp, w, h, visible_ms)
            
            # Video Tracks
            if self._project:
                for idx, vt in enumerate(self._project.video_tracks):
                    if not vt.hidden:
                        self._draw_track_clips(pp, idx, vt)
                
                # Waveform (Legacy: only for track 0 if single)
                if not self._project.video_tracks[0].hidden:
                    self._draw_video_audio(pp, w, h)
            
            if self._track and not self._track.hidden:
                self._draw_audio_track(pp, h)
                self._draw_segments(pp, h)
            
            if self._image_overlay_track and not self._image_overlay_track.hidden:
                self._draw_image_overlays(pp, h)
            
            if self._text_overlay_track:
                self._draw_text_overlays(pp, h)
            
            if hasattr(self, "_bgm_tracks") and self._bgm_tracks:
                self._draw_bgm_tracks(pp, h)
            
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
            # Snap visually on timeline
            old_visual_duration = (self._drag_orig_source_out - self._drag_orig_source_in) / clip.speed
            new_visual_duration = max(100 / clip.speed, old_visual_duration - dx_ms)
            new_end = clip_start_ms + new_visual_duration
            
            snapped_end = self._apply_magnetic_snap(new_end, candidates)
            if self._snap_guide_x is None:
                 snapped_end = self._snap_ms(int(new_end))
            
            final_visual_duration = snapped_end - clip_start_ms
            if final_visual_duration < 100 / clip.speed:
                final_visual_duration = 100 / clip.speed
                
            # source_duration = visual_duration * speed
            clip.source_in_ms = int(clip.source_out_ms - (final_visual_duration * clip.speed))

        elif self._drag_mode == _DragMode.CLIP_TRIM_RIGHT:
            old_visual_duration = (self._drag_orig_source_out - self._drag_orig_source_in) / clip.speed
            new_visual_duration = max(100 / clip.speed, old_visual_duration + dx_ms)
            new_end = clip_start_ms + new_visual_duration
            
            snapped_end = self._apply_magnetic_snap(new_end, candidates)
            if self._snap_guide_x is None:
                 snapped_end = self._snap_ms(int(new_end))
                 
            final_visual_duration = snapped_end - clip_start_ms
            if final_visual_duration < 100 / clip.speed:
                final_visual_duration = 100 / clip.speed
                
            clip.source_out_ms = int(clip.source_in_ms + (final_visual_duration * clip.speed))

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

        waveform_y = self._waveform_y()
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
        """Draw fallback UI when waveform data is not available."""
        waveform_y = self._waveform_y()
        waveform_h = _WAVEFORM_H
        
        # Draw placeholder background
        painter.fillRect(0, waveform_y, w, waveform_h, QColor(40, 40, 40, 100))
        
        # Draw center line
        center_y = waveform_y + waveform_h // 2
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(0, center_y, w, center_y)
        
        # Draw label
        label_x = max(5, int(self._ms_to_x(0)) + 5)
        if 0 < label_x < w - 120:
            painter.setPen(QColor(150, 150, 150, 150))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(label_x, waveform_y + 10, "Video Audio (loading...)")

    def _draw_audio_track(self, painter: QPainter, h: int) -> None:
        """세그먼트별 TTS 오디오 구간을 녹색 박스로 그림."""
        if not self._track:
            return

        y = self._audio_track_y()
        track_h = _AUDIO_H
        
        for i, seg in enumerate(self._track):
            if not seg.audio_file:
                continue
            x1 = self._ms_to_x(seg.start_ms)
            x2 = self._ms_to_x(seg.end_ms)
            if x2 < 0 or x1 > self.width():
                continue
            
            rect = QRectF(x1, y, x2 - x1, track_h)
            painter.setBrush(QBrush(self._AUDIO_COLOR_TOP))
            painter.setPen(QPen(self._AUDIO_BORDER, 1))
            painter.drawRoundedRect(rect, 4, 4)

    def _draw_segments(self, painter: QPainter, h: int) -> None:
        """자막 세그먼트를 파란 그라데이션 박스로 그리기."""
        if not self._track:
            return

        y = self._subtitle_track_y()
        track_h = _SEG_H
        
        for i, seg in enumerate(self._track):
            x1 = self._ms_to_x(seg.start_ms)
            x2 = self._ms_to_x(seg.end_ms)
            if x2 < 0 or x1 > self.width():
                continue
            
            rect = QRectF(x1, y, x2 - x1, track_h)
            is_selected = (self._selected_index == i)
            
            top = self._SEGMENT_COLOR_TOP
            bot = self._SEGMENT_COLOR_BOT
            border = self._SEGMENT_BORDER
            
            if is_selected:
                border = self._SELECTED_BORDER
                painter.setBrush(QBrush(self._SELECTED_GLOW))
                painter.drawRect(rect.adjusted(-2, -2, 2, 2))
                
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0, top)
            grad.setColorAt(1, bot)
            
            painter.setBrush(grad)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(rect, 4, 4)
            
            painter.setPen(Qt.GlobalColor.white)
            painter.setFont(QFont("Arial", 8))
            painter.drawText(rect.adjusted(5, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, seg.text)

    # ---- 이미지 오버레이 레이아웃 상수 & 헬퍼 ----
    _IMG_ROW_H = 28
    _IMG_ROW_GAP = 2

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

    def _text_overlay_base_y(self) -> int:
        """텍스트 오버레이 트랙의 시작 Y 좌표 반환."""
        rows = self._compute_overlay_rows()
        img_height = self._img_overlay_total_h(rows)
        return self._img_overlay_base_y() + img_height + 10

    def _compute_text_overlay_rows(self) -> list[int]:
        """텍스트 오버레이를 겹치지 않게 행 배치."""
        if not self._text_overlay_track:
            return []
        
        rows = []
        row_ends = []  # 각 행의 마지막 종료 시간
        
        for overlay in self._text_overlay_track.overlays:
            placed = False
            for r_idx, end_ms in enumerate(row_ends):
                if overlay.start_ms >= end_ms:
                    rows.append(r_idx)
                    row_ends[r_idx] = overlay.end_ms
                    placed = True
                    break
            if not placed:
                rows.append(len(row_ends))
                row_ends.append(overlay.end_ms)
        
        return rows

    def _draw_text_overlays(self, painter: QPainter, h: int) -> None:
        """텍스트 오버레이 세그먼트를 타임라인에 그림."""
        if not self._text_overlay_track or len(self._text_overlay_track) == 0:
            return

        text_base_y = self._text_overlay_base_y()
        text_h = self._TEXT_ROW_H
        text_gap = self._TEXT_ROW_GAP

        rows = self._compute_text_overlay_rows()

        for i, overlay in enumerate(self._text_overlay_track.overlays):
            x1 = self._ms_to_x(overlay.start_ms)
            x2 = self._ms_to_x(overlay.end_ms)
            if x2 < 0 or x1 > self.width():
                continue

            row = rows[i]
            y = text_base_y + row * (text_h + text_gap)
            rect = QRectF(x1, y, max(x2 - x1, 2), text_h)

            if i == self._selected_text_overlay_index:
                painter.setPen(QPen(self._TEXT_OVERLAY_SELECTED_BORDER, 2))
                painter.setBrush(QBrush(self._TEXT_OVERLAY_SELECTED_COLOR))
            else:
                painter.setPen(QPen(self._TEXT_OVERLAY_BORDER, 1))
                painter.setBrush(QBrush(self._TEXT_OVERLAY_COLOR))
            painter.drawRoundedRect(rect, 3, 3)

            # 텍스트 표시
            if rect.width() > 30:
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Arial", 8))
                text_rect = rect.adjusted(4, 2, -4, -2)
                display_text = overlay.text[:20] + "..." if len(overlay.text) > 20 else overlay.text
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    painter.fontMetrics().elidedText(
                        display_text, Qt.TextElideMode.ElideRight, int(text_rect.width())
                    ),
                )

    def _draw_bgm_tracks(self, painter: QPainter, h: int) -> None:
        """BGM 트랙들을 타임라인에 그림."""
        if not hasattr(self, "_bgm_tracks") or not self._bgm_tracks:
            return
        
        for idx, track in enumerate(self._bgm_tracks):
            self._draw_bgm_track_clips(painter, idx, track)

    def _draw_bgm_track_clips(self, painter: QPainter, track_idx: int, trackObject) -> None:
        # We'll use a local import if needed or just trust the type
        from src.models.audio import AudioTrack
        track: AudioTrack = trackObject
        
        y = self._bgm_track_y(track_idx)
        th = _BGM_H
        
        for i, clip in enumerate(track.clips):
            x1 = self._ms_to_x(clip.start_ms)
            x2 = self._ms_to_x(clip.start_ms + clip.duration_ms)
            
            if x2 < 0 or x1 > self.width():
                continue
            
            rect = QRectF(x1, y, max(x2 - x1, 2), th)
            
            # Draw BGM clip with gradient
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gradient.setColorAt(0, self._BGM_COLOR_TOP)
            gradient.setColorAt(1, self._BGM_COLOR_BOT)
            
            # TODO: Implement selection state for BGM
            is_selected = False # self._selected_bgm_track == track_idx and self._selected_bgm_clip == i
            
            if is_selected:
                painter.setPen(QPen(self._BGM_SELECTED_BORDER, 2))
                painter.setBrush(QBrush(self._BGM_SELECTED_COLOR))
            else:
                painter.setPen(QPen(self._BGM_BORDER, 1))
                painter.setBrush(QBrush(gradient))
                
            painter.drawRoundedRect(rect, 4, 4)
            
            # Label
            if rect.width() > 40:
                painter.setPen(Qt.GlobalColor.white)
                painter.setFont(QFont("Arial", 8))
                label = clip.source_path.name if clip.source_path else "BGM"
                painter.drawText(rect.adjusted(10, 2, -10, -2), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)


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

    def _draw_track_clips(self, painter: QPainter, track_idx: int, track: VideoClipTrack) -> None:
        """Draw clips for a specific video track."""
        if not track.clips:
            return

        w = self.width()
        y = self._video_track_y(track_idx)
        h = _CLIP_H
        
        waveform_color = self._WAVEFORM_FILL
        waveform_edge = self._WAVEFORM_EDGE
        # Assign colors to unique source paths
        source_paths = set(c.source_path for c in track.clips)
        source_color_map = {}
        for i, path in enumerate(sorted(list(source_paths), key=lambda x: str(x) if x is not None else "")):
            source_color_map[path] = i

        # Calculate clip positions
        clip_starts = track.clip_boundaries_ms()

        for i, clip in enumerate(track.clips):
            start_ms = clip_starts[i]
            x1 = self._ms_to_x(start_ms)
            x2 = self._ms_to_x(start_ms + clip.duration_ms)

            if x2 < 0 or x1 > w:
                continue

            rect = QRectF(x1, y, max(x2 - x1, 2), h)
            
            is_selected = (self._selected_clip_track_index == track_idx and self._selected_clip_index == i)
            
            if is_selected:
                painter.setPen(QPen(self._CLIP_SELECTED_BORDER, 2))
                glow_gradient = QLinearGradient(0, y, 0, y + h)
                glow_gradient.setColorAt(0, self._CLIP_SELECTED_COLOR)
                glow_gradient.setColorAt(1, self._CLIP_SELECTED_COLOR.darker(120))
                painter.setBrush(QBrush(glow_gradient))
            else:
                color_idx = source_color_map.get(clip.source_path, 0) % len(self._SOURCE_COLORS)
                c_top, c_bot, border_color = self._SOURCE_COLORS[color_idx]
                gradient = QLinearGradient(0, y, 0, y + h)
                gradient.setColorAt(0, c_top)
                gradient.setColorAt(1, c_bot)
                painter.setBrush(QBrush(gradient))
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 6, 6)
            
            # --- Rendering Clip-level Waveform ---
            if self._waveform_service and clip.source_path:
                wf = self._waveform_service.get_waveform(clip.source_path)
                if wf:
                    self._draw_clip_waveform(painter, rect, clip, wf)
                else:
                    # Request if not available
                    self._waveform_service.request_waveform(clip.source_path)
            
            # --- Filmstrip Thumbnails ---
            if self._should_draw_thumbnails(rect.width()):
                vis_x1 = max(int(x1), int(self._ms_to_x(start_ms)))
                # Calculate visible end to avoid redundant requests
                vis_x2 = min(int(x2), int(self._ms_to_x(start_ms + clip.duration_ms)))
                
                if vis_x2 > vis_x1:
                    interval = self._get_thumbnail_interval()
                    start_grid = (vis_x1 // interval) * interval
                    painter.save()
                    painter.setClipRect(rect)
                    
                    for tx in range(start_grid, vis_x2, interval):
                        if tx + interval < x1: continue
                        offset_ms = (tx - x1) / self._px_per_ms
                        source_ms = int(clip.source_in_ms + offset_ms * clip.speed)
                        
                        # Use clip's source_path if available, otherwise use primary video path
                        video_path = clip.source_path if clip.source_path else self._primary_video_path
                        if video_path:
                            thumb = self._thumbnail_service.request_thumbnail(
                                video_path, source_ms, h
                            )
                            if thumb:
                                target_rect = QRectF(tx, y, interval, h)
                                painter.drawImage(target_rect.toRect(), thumb)
                    
                    painter.restore()
            
            # --- Transition Markers ---
            # If a transition is set, draw a visual indicator at the end of the clip.
            if hasattr(clip, "transition_out") and clip.transition_out:
                dur_px = self._px_per_ms * clip.transition_out.duration_ms
                marker_w = min(rect.width() / 2, dur_px)
                marker_rect = QRectF(x2 - marker_w, y, marker_w, h)
                
                painter.setBrush(QBrush(self._TRANSITION_MARKER_COLOR))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(marker_rect)
                
                if marker_w > 15:
                    painter.setPen(Qt.GlobalColor.black)
                    painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
                    indicator = clip.transition_out.type[0].upper() if clip.transition_out.type else "T"
                    painter.drawText(marker_rect, Qt.AlignmentFlag.AlignCenter, indicator)

            # Label
            if clip.source_path:
                from pathlib import Path
                label = Path(clip.source_path).stem
            else:
                label = "Clip"
            
            if hasattr(clip, "speed") and clip.speed != 1.0:
                 label += f" ({clip.speed:.2f}x)"
            
            if rect.width() > 40:
                painter.setPen(Qt.GlobalColor.white)
                painter.setFont(QFont("Arial", 8))
                painter.drawText(rect.adjusted(10, 2, -10, -2), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

            # --- Volume Envelope (Rubber Banding) ---
            if hasattr(clip, "volume_points") and clip.volume_points:
                self._draw_volume_envelope(painter, rect, clip)
            else:
                # Always draw a horizontal line at 100% volume (middle) if no points
                # Actually, let's draw it at the clip's 'volume' property level if no points?
                # For Phase T8, we'll draw it at y corresponding to 1.0 gain.
                self._draw_default_volume_line(painter, rect, clip)

    def _draw_clip_waveform(self, painter: QPainter, rect: QRectF, clip: VideoClip, wf: WaveformData) -> None:
        """Draw waveform for a specific clip within its timeline rectangle."""
        rect_x = rect.x()
        rect_y = rect.y()
        rect_w = rect.width()
        rect_h = rect.height()
        
        center_y = rect_y + rect_h / 2.0
        half_h = rect_h / 2.0
        
        # Clip source range
        s_in = clip.source_in_ms
        s_out = clip.source_out_ms
        
        # Pixels to iterate
        p_start = max(0, int(rect_x))
        p_end = min(self.width(), int(rect_x + rect_w))
        
        painter.setPen(QPen(self._WAVEFORM_EDGE, 1))
        
        # Get clip start on timeline for coordinate mapping
        try:
            # We assume current track clips are being drawn
            idx = self._clip_track.clips.index(clip)
            clip_start_ms = self._clip_track.clip_timeline_start(idx)
        except (ValueError, AttributeError):
            clip_start_ms = 0

        # Optimization: Loop over pixels and pick corresponding source ms
        for px in range(p_start, p_end):
            # 1. Timeline pixel -> timeline ms (relative to clip start)
            ms_on_timeline = self._x_to_ms(px)
            local_ms = ms_on_timeline - clip_start_ms
            
            # 2. Local timeline ms -> source ms
            source_ms = s_in + int(local_ms * clip.speed)
            
            if source_ms < s_in or source_ms >= s_out or source_ms >= wf.duration_ms:
                continue
            
            # 3. Source ms -> peak data index
            idx = int(source_ms)
            if idx >= len(wf.peaks_pos):
                continue
                
            peak_max = wf.peaks_pos[idx]
            peak_min = wf.peaks_neg[idx]
            
            y_top = center_y - (peak_max * half_h)
            y_bot = center_y - (peak_min * half_h)
            
            painter.drawLine(px, int(y_top), px, int(y_bot))

    def _draw_volume_envelope(self, painter: QPainter, rect: QRectF, clip: VideoClip) -> None:
        """Draw the volume line connect points + points themselves."""
        if not clip.volume_points:
            self._draw_default_volume_line(painter, rect, clip)
            return

        painter.save()
        painter.setClipRect(rect)
        
        rect_x = rect.x()
        rect_y = rect.y()
        rect_h = rect.height()
        
        # Helper to map volume (0.0 - 2.0) to y
        def vol_to_y(vol: float) -> float:
            # 2.0 -> top, 1.0 -> middle, 0.0 -> bottom
            # We use a bit of margin so points aren't cut off at the very edge
            margin = 4
            norm = (2.0 - vol) / 2.0  # 0.0 at 2.0 vol, 0.5 at 1.0 vol, 1.0 at 0.0 vol
            return rect_y + margin + norm * (rect_h - 2 * margin)

        # Sort points by offset
        sorted_points = sorted(clip.volume_points, key=lambda p: p.offset_ms)
        
        path = []
        # Start of clip
        if sorted_points[0].offset_ms > 0:
            first_vol = sorted_points[0].volume
            path.append(QPoint(int(rect_x), int(vol_to_y(first_vol))))
        
        for p in sorted_points:
            px = rect_x + p.offset_ms * self._px_per_ms
            path.append(QPoint(int(px), int(vol_to_y(p.volume))))
        
        # End of clip
        if sorted_points[-1].offset_ms < clip.duration_ms:
            last_vol = sorted_points[-1].volume
            path.append(QPoint(int(rect_x + rect.width()), int(vol_to_y(last_vol))))
        
        # Draw line
        painter.setPen(QPen(self._VOLUME_LINE_COLOR, 1.5))
        for i in range(len(path) - 1):
            painter.drawLine(path[i], path[i+1])
            
        # Draw points
        painter.setPen(QPen(self._VOLUME_LINE_COLOR, 1))
        painter.setBrush(QBrush(self._VOLUME_POINT_COLOR))
        for p in path:
            painter.drawEllipse(p, self._VOLUME_POINT_RADIUS, self._VOLUME_POINT_RADIUS)
            
        painter.restore()

    def _draw_default_volume_line(self, painter: QPainter, rect: QRectF, clip: VideoClip) -> None:
        """Draw a flat volume line at clip.volume level."""
        painter.save()
        painter.setClipRect(rect)
        
        rect_x = rect.x()
        rect_y = rect.y()
        rect_h = rect.height()
        
        # 1.0 vol -> middle
        vol = clip.volume if hasattr(clip, "volume") else 1.0
        norm = (2.0 - vol) / 2.0
        margin = 4
        y = rect_y + margin + norm * (rect_h - 2 * margin)
        
        painter.setPen(QPen(self._VOLUME_LINE_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(rect_x), int(y), int(rect_x + rect.width()), int(y))
        
        painter.restore()

    def clip_timeline_start_ms(self, clip: VideoClip) -> int:
        """Find timeline start position of a clip."""
        if not self._clip_track:
            return 0
        try:
            idx = self._clip_track.clips.index(clip)
            return self._clip_track.clip_timeline_start(idx)
        except ValueError:
            return 0

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._duration_ms <= 0 or self._px_per_ms <= 0:
            return

        x = event.position().x()
        y = event.position().y()

        # Shift + 클릭 드래그: 뷰 팬
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            seg_idx, hit, v_idx = self._hit_test(x, y)
            if hit == "clip_body" or hit == "volume_point":
                # Shift + Click on clip body or near point -> Add / Toggle point
                self._handle_volume_point_shift_click(v_idx, seg_idx, x, y)
                return
            
            self._drag_mode = _DragMode.PAN_VIEW
            self._drag_start_x = x
            self._drag_start_visible_ms = self._visible_start_ms
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            return

        seg_idx, hit, v_idx = self._hit_test(x, y)

        # 플레이헤드 드래그
        if hit == "playhead":
            self._drag_mode = _DragMode.PLAYHEAD_DRAG
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            return

        # 비디오 클립 영역 (Locked check)
        if hit.startswith("clip"):
            vt = self._project.video_tracks[v_idx] if self._project else None
            if vt and vt.locked:
                return
            
            if hit == "volume_point":
                self._selected_clip_track_index = v_idx
                self._selected_clip_index = seg_idx
                self._drag_mode = _DragMode.VOLUME_POINT_MOVE
                self._drag_volume_point_idx = seg_idx # Wait, seg_idx from hit_test is point index in this case
                # Actually, our _hit_test returns (point_idx, "volume_point", track_idx)
                self._drag_volume_point_idx = seg_idx
                self._drag_clip_track_index = v_idx
                # We need the clip index too... hit_test doesn't return it for volume_point currently
                # Let's fix hit_test to return clip_idx as well?
                # Or use _drag_clip_ref which we set in hit_test
                self.update()
                return

            if hit == "clip_body":
                self._selected_clip_track_index = v_idx
                self._selected_clip_index = seg_idx
                self._selected_index = -1
                self._selected_overlay_index = -1
                self.clip_selected.emit(v_idx, seg_idx)
            elif hit == "clip_right_edge":
                self._selected_clip_track_index = v_idx
                self._selected_clip_index = seg_idx
                self._selected_index = -1
                self._selected_overlay_index = -1
                self._start_drag(_DragMode.CLIP_TRIM_RIGHT, v_idx, seg_idx, x)
                self.clip_selected.emit(v_idx, seg_idx)
            self.update()
            return

        # 오디오 트랙 영역 (Locked check)
        if hit.startswith("audio"):
            if self._track and self._track.locked:
                return
            if hit == "body":
                self._audio_selected = True
                self._selected_index = seg_idx
                self._selected_overlay_index = -1
                self._start_audio_drag(_DragMode.AUDIO_MOVE, x)
                self.segment_selected.emit(seg_idx)
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            elif hit == "left_edge":
                self._audio_selected = True
                self._selected_index = seg_idx
                self._selected_overlay_index = -1
                self._start_audio_drag(_DragMode.AUDIO_RESIZE_LEFT, x)
                self.segment_selected.emit(seg_idx)
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif hit == "right_edge":
                self._audio_selected = True
                self._selected_index = seg_idx
                self._selected_overlay_index = -1
                self._start_audio_drag(_DragMode.AUDIO_RESIZE_RIGHT, x)
                self.segment_selected.emit(seg_idx)
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            self.update()
            self.update()
            return

        # 이미지 오버레이 영역 (Locked check)
        if hit.startswith("img"):
            if self._image_overlay_track and self._image_overlay_track.locked:
                return
            if hit == "img_left_edge":
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
            return

        # 텍스트 오버레이 영역
        if hit.startswith("text"):
            if self._text_overlay_track:  # No locked check for now, can add later
                if hit == "text_left_edge":
                    self._selected_text_overlay_index = seg_idx
                    self._selected_index = -1
                    self._selected_overlay_index = -1
                    self._start_text_drag(_DragMode.TEXT_RESIZE_LEFT, seg_idx, x)
                    self.text_overlay_selected.emit(seg_idx)
                elif hit == "text_right_edge":
                    self._selected_text_overlay_index = seg_idx
                    self._selected_index = -1
                    self._selected_overlay_index = -1
                    self._start_text_drag(_DragMode.TEXT_RESIZE_RIGHT, seg_idx, x)
                    self.text_overlay_selected.emit(seg_idx)
                elif hit == "text_body":
                    self._selected_text_overlay_index = seg_idx
                    self._selected_index = -1
                    self._selected_overlay_index = -1
                    self._start_text_drag(_DragMode.TEXT_MOVE, seg_idx, x)
                    self.text_overlay_selected.emit(seg_idx)
            return

        # BGM 영역 (Locked check)
        if hit.startswith("bgm"):
            if hasattr(self, "_bgm_tracks"):
                track = self._bgm_tracks[v_idx]
                if track.locked:
                    return
                
                self._selected_bgm_track_index = v_idx
                self._selected_bgm_clip_index = seg_idx
                self._selected_index = -1
                self._selected_overlay_index = -1
                self._selected_text_overlay_index = -1
                
                if hit == "bgm_left_edge":
                    self._start_bgm_drag(_DragMode.BGM_RESIZE_LEFT, v_idx, seg_idx, x)
                elif hit == "bgm_right_edge":
                    self._start_bgm_drag(_DragMode.BGM_RESIZE_RIGHT, v_idx, seg_idx, x)
                elif hit == "bgm_body":
                    self._start_bgm_drag(_DragMode.BGM_MOVE, v_idx, seg_idx, x)
                
                self.update()
                return

        # 자막 세그먼트 (Locked check)
        elif hit in ("left_edge", "right_edge", "body"):
            if self._track and self._track.locked:
                return
            if hit == "left_edge":
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
            return
        else:
            self._audio_selected = False
            self._selected_index = -1
            self._selected_overlay_index = -1
            self._drag_mode = _DragMode.SEEK
            self._seek_to_x(x)

        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """더블 클릭 시 텍스트 오버레이 편집 다이얼로그 요청."""
        if self._duration_ms <= 0 or self._px_per_ms <= 0:
            return

        x = event.position().x()
        y = event.position().y()

        seg_idx, hit, v_idx = self._hit_test(x, y)

        if hit.startswith("text_"):
            self.text_overlay_edit_requested.emit(seg_idx)
            return

        super().mouseDoubleClickEvent(event)

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

        if self._drag_mode in (_DragMode.TEXT_MOVE, _DragMode.TEXT_RESIZE_LEFT, _DragMode.TEXT_RESIZE_RIGHT):
            self._handle_text_drag(x)
            return

        if self._drag_mode in (_DragMode.CLIP_TRIM_LEFT, _DragMode.CLIP_TRIM_RIGHT):
            self._handle_clip_drag(x)
            return

        if self._drag_mode == _DragMode.VOLUME_POINT_MOVE:
            self._handle_volume_point_drag(x, y)
            return

        if self._drag_mode in (_DragMode.BGM_MOVE, _DragMode.BGM_RESIZE_LEFT, _DragMode.BGM_RESIZE_RIGHT):
            self._handle_bgm_drag(x)
            return

        # 호버 시 커서 변경 (플레이헤드·가장자리·본문)
        if self._drag_mode == _DragMode.NONE:
            seg_idx, hit, v_idx = self._hit_test(x, y)
            if hit == "playhead":
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
                return
            elif hit in ("left_edge", "right_edge", "img_left_edge", "img_right_edge",
                         "clip_left_edge", "clip_right_edge", "audio_left_edge", "audio_right_edge",
                         "bgm_left_edge", "bgm_right_edge"):
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif hit in ("body", "audio_body", "img_body", "clip_body", "bgm_body"):
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
        elif self._drag_mode in (_DragMode.TEXT_MOVE, _DragMode.TEXT_RESIZE_LEFT, _DragMode.TEXT_RESIZE_RIGHT):
            if self._text_overlay_track and 0 <= self._drag_text_index < len(self._text_overlay_track.overlays):
                ov = self._text_overlay_track.overlays[self._drag_text_index]
                if ov.start_ms != self._drag_text_orig_start_ms or ov.end_ms != self._drag_text_orig_end_ms:
                    self.text_overlay_moved.emit(self._drag_text_index, ov.start_ms, ov.end_ms)
            self._drag_text_index = -1
        elif self._drag_mode in (_DragMode.CLIP_TRIM_LEFT, _DragMode.CLIP_TRIM_RIGHT):
            if self._project and 0 <= self._drag_clip_track_index < len(self._project.video_tracks):
                vt = self._project.video_tracks[self._drag_clip_track_index]
                if 0 <= self._drag_clip_index < len(vt.clips):
                    clip = vt.clips[self._drag_clip_index]
                    new_in = clip.source_in_ms
                    new_out = clip.source_out_ms
                    if new_in != self._drag_orig_source_in or new_out != self._drag_orig_source_out:
                        # Revert to original so undo command's redo() applies the change
                        clip.source_in_ms = self._drag_orig_source_in
                        clip.source_out_ms = self._drag_orig_source_out
                        # We might need to update this signal to include track_index
                        self.clip_trimmed.emit(self._drag_clip_index, new_in, new_out)
            self._drag_clip_index = -1
            self._drag_clip_track_index = -1
        elif self._drag_mode == _DragMode.VOLUME_POINT_MOVE:
            if self._drag_clip_ref:
                self._drag_clip_ref.volume_points.sort(key=lambda p: p.offset_ms)
            self._drag_volume_point_idx = -1
            self._drag_clip_ref = None
        elif self._drag_mode in (_DragMode.BGM_MOVE, _DragMode.BGM_RESIZE_LEFT, _DragMode.BGM_RESIZE_RIGHT):
            if 0 <= self._drag_bgm_track_index < len(self._bgm_tracks):
                track = self._bgm_tracks[self._drag_bgm_track_index]
                if 0 <= self._drag_bgm_clip_index < len(track.clips):
                    clip = track.clips[self._drag_bgm_clip_index]
                    new_start = clip.start_ms
                    new_dur = clip.duration_ms
                    
                    if self._drag_mode == _DragMode.BGM_MOVE:
                        if new_start != self._drag_bgm_orig_start_ms:
                            clip.start_ms = self._drag_bgm_orig_start_ms # Revert for undo command
                            self.bgm_clip_moved.emit(self._drag_bgm_track_index, self._drag_bgm_clip_index, new_start)
                    else:
                        if new_start != self._drag_bgm_orig_start_ms or new_dur != self._drag_bgm_orig_duration_ms:
                            clip.start_ms = self._drag_bgm_orig_start_ms
                            clip.duration_ms = self._drag_bgm_orig_duration_ms
                            self.bgm_clip_trimmed.emit(self._drag_bgm_track_index, self._drag_bgm_clip_index, new_start, new_dur)

        self._drag_mode = _DragMode.NONE
        self._drag_seg_index = -1
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.update()

    def _handle_volume_point_shift_click(self, track_idx: int, p_idx_maybe: int, x: float, y: float) -> None:
        """Add or remove volume point with Shift+Click."""
        if not self._project or track_idx < 0: return
        vt = self._project.video_tracks[track_idx]
        clip = None
        offset = 0
        for i, c in enumerate(vt.clips):
            x1 = self._ms_to_x(offset)
            x2 = self._ms_to_x(offset + c.duration_ms)
            if x1 <= x <= x2:
                clip = c
                break
            offset += c.duration_ms
        if not clip: return
        timeline_ms = self._x_to_ms(x)
        clip_start_ms = self.clip_timeline_start_ms(clip)
        offset_ms = int(max(0, min(clip.duration_ms, timeline_ms - clip_start_ms)))
        rect_y = self._video_track_y(track_idx)
        rect_h = _CLIP_H
        margin = 4
        norm = (y - rect_y - margin) / (rect_h - 2 * margin)
        vol = 2.0 - (norm * 2.0)
        vol = max(0.0, min(2.0, vol))
        hit_p_idx = -1
        for i, p in enumerate(clip.volume_points):
            px = self._ms_to_x(clip_start_ms + p.offset_ms)
            if abs(x - px) <= self._VOLUME_POINT_RADIUS + 3:
                hit_p_idx = i
                break
        from src.models.video_clip import VolumePoint
        if hit_p_idx != -1:
            clip.volume_points.pop(hit_p_idx)
        else:
            clip.volume_points.append(VolumePoint(offset_ms=offset_ms, volume=vol))
            clip.volume_points.sort(key=lambda p: p.offset_ms)
        self.update()

    def _handle_volume_point_drag(self, x: float, y: float) -> None:
        """Drag a volume point to change volume and offset."""
        if not self._drag_clip_ref: return
        clip = self._drag_clip_ref
        p_idx = self._drag_volume_point_idx
        if p_idx < 0 or p_idx >= len(clip.volume_points): return
        p = clip.volume_points[p_idx]
        timeline_ms = self._x_to_ms(x)
        clip_start_ms = self.clip_timeline_start_ms(clip)
        new_offset = int(max(0, min(clip.duration_ms, timeline_ms - clip_start_ms)))
        rect_y = self._video_track_y(self._selected_clip_track_index)
        rect_h = _CLIP_H
        margin = 4
        norm = (y - rect_y - margin) / (rect_h - 2 * margin)
        new_vol = 2.0 - (norm * 2.0)
        new_vol = max(0.0, min(2.0, new_vol))
        p.offset_ms = new_offset
        p.volume = new_vol
        self.update()

    def contextMenuEvent(self, event) -> None:
        """우클릭: 클립 분할/삭제, 이미지 오버레이 삭제 또는 현재 위치에 삽입."""
        if self._duration_ms <= 0:
            return
        x = event.pos().x()
        y = event.pos().y()
        menu = QMenu(self)

        # 비디오 클립 트랙 영역 우클릭
        seg_idx, hit, v_idx = self._hit_test(x, y)
        if hit.startswith("clip_"):
            vt = self._project.video_tracks[v_idx] if self._project else None
            split_act = menu.addAction(tr("Split at Playhead (Ctrl+B)"))
            delete_act = None
            if vt and len(vt.clips) > 1:
                delete_act = menu.addAction(tr("Delete Clip"))
            
            trans_act = None
            if vt and seg_idx < len(vt.clips) - 1:
                trans_act = menu.addAction(tr("Add Transition..."))
            
            volume_act = menu.addAction(tr("Adjust Volume..."))
                
            action = menu.exec(event.globalPos())
            if action == split_act:
                self.clip_split_requested.emit(self._playhead_ms)
            elif delete_act and action == delete_act:
                self.clip_deleted.emit(v_idx, seg_idx)
            elif trans_act and action == trans_act:
                self.transition_requested.emit(v_idx, seg_idx)
            elif action == volume_act:
                self.clip_volume_requested.emit(v_idx, seg_idx)
            return

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

        if hit.startswith("text_"):
            edit_act = menu.addAction(tr("Edit Text Content/Style..."))
            delete_act = menu.addAction(tr("Delete Text Overlay"))
            action = menu.exec(event.globalPos())
            if action == edit_act:
                self.text_overlay_edit_requested.emit(seg_idx)
            elif action == delete_act:
                self.text_overlay_delete_requested.emit(seg_idx)
            return

        if hit.startswith("bgm_"):
            delete_act = menu.addAction(tr("Delete BGM Clip"))
            action = menu.exec(event.globalPos())
            if action == delete_act:
                self.bgm_clip_delete_requested.emit(v_idx, seg_idx)
            return
        
        insert_image_action = menu.addAction(tr("Insert Image Overlay"))
        insert_text_action = menu.addAction(tr("Insert Text Overlay"))
        action = menu.exec(event.globalPos())
        if action == insert_image_action:
            ms = int(max(0, min(int(self._duration_ms), int(self._x_to_ms(x)))))
            self.insert_image_requested.emit(ms)
        elif action == insert_text_action:
            ms = int(max(0, min(int(self._duration_ms), int(self._x_to_ms(x)))))
            self.insert_text_requested.emit(ms)

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

        # BGM Clips
        if hasattr(self, "_bgm_tracks"):
            for t_idx, track in enumerate(self._bgm_tracks):
                for i, clip in enumerate(track.clips):
                    if not (t_idx == self._drag_bgm_track_index and i == self._drag_bgm_clip_index):
                        candidates.add(clip.start_ms)
                        candidates.add(clip.start_ms + clip.duration_ms)

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
            
    def _handle_clip_drag(self, x: float) -> None:
        """비디오 클립 트림 처리."""
        if not self._project or self._drag_clip_track_index < 0:
            return
        vt = self._project.video_tracks[self._drag_clip_track_index]
        if self._drag_clip_index < 0 or self._drag_clip_index >= len(vt.clips):
            return

        dx_ms = int((x - self._drag_start_x) / self._px_per_ms) if self._px_per_ms > 0 else 0
        clip = vt.clips[self._drag_clip_index]
        
        # Clip start time on timeline (visual start)
        boundaries = vt.clip_boundaries_ms()
        if self._drag_clip_index >= len(boundaries):
             return
        clip_start_ms = boundaries[self._drag_clip_index]

        candidates = self._get_magnetic_snap_candidates(skip_clip_index=self._drag_clip_index)

        if self._drag_mode == _DragMode.CLIP_TRIM_LEFT:
            # Snap visually on timeline
            old_visual_duration = (self._drag_orig_source_out - self._drag_orig_source_in) / clip.speed
            new_visual_duration = max(100 / clip.speed, old_visual_duration - dx_ms)
            new_end = clip_start_ms + new_visual_duration
            
            snapped_end = self._apply_magnetic_snap(new_end, candidates)
            if self._snap_guide_x is None:
                 snapped_end = self._snap_ms(int(new_end))
            
            final_visual_duration = snapped_end - clip_start_ms
            if final_visual_duration < 100 / clip.speed:
                final_visual_duration = 100 / clip.speed
                
            clip.source_in_ms = int(clip.source_out_ms - (final_visual_duration * clip.speed))

        elif self._drag_mode == _DragMode.CLIP_TRIM_RIGHT:
            old_visual_duration = (self._drag_orig_source_out - self._drag_orig_source_in) / clip.speed
            new_visual_duration = max(100 / clip.speed, old_visual_duration + dx_ms)
            new_end = clip_start_ms + new_visual_duration
            
            snapped_end = self._apply_magnetic_snap(new_end, candidates)
            if self._snap_guide_x is None:
                 snapped_end = self._snap_ms(int(new_end))
                 
            final_visual_duration = snapped_end - clip_start_ms
            if final_visual_duration < 100 / clip.speed:
                final_visual_duration = 100 / clip.speed
                
            clip.source_out_ms = int(clip.source_in_ms + (final_visual_duration * clip.speed))

        self._invalidate_static_cache()
        self.update()

    def _start_audio_drag(self, mode: _DragMode, x: float) -> None:
        """오디오 트랙 드래그 시작."""
        self._drag_mode = mode
        self._drag_start_x = x
        if self._track:
            self._drag_orig_audio_start_ms = self._track.audio_start_ms
            self._drag_orig_audio_duration_ms = self._track.audio_duration_ms

    def _start_bgm_drag(self, mode: _DragMode, track_idx: int, clip_idx: int, x: float) -> None:
        """BGM 드래그 시작."""
        self._drag_mode = mode
        self._drag_start_x = x
        self._drag_bgm_track_index = track_idx
        self._drag_bgm_clip_index = clip_idx

        if 0 <= track_idx < len(self._bgm_tracks):
            track = self._bgm_tracks[track_idx]
            if 0 <= clip_idx < len(track.clips):
                clip = track.clips[clip_idx]
                self._drag_bgm_orig_start_ms = clip.start_ms
                self._drag_bgm_orig_duration_ms = clip.duration_ms

        if mode == _DragMode.BGM_MOVE:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

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

    def _hit_test(self, x: float, y: float) -> tuple[int, str, int]:
        """(x,y)에 해당하는 (인덱스, 히트 영역, 트랙 인덱스) 반환. 없으면 (-1, '', -1)."""
        playhead_x = self._ms_to_x(self._playhead_ms)
        if abs(x - playhead_x) <= _PLAYHEAD_HIT_PX:
            return -3, "playhead", -1

        # Video tracks
        if self._project:
            for v_idx, vt in enumerate(self._project.video_tracks):
                track_y = self._video_track_y(v_idx)
                if track_y <= y < track_y + _CLIP_H:
                    offset = 0
                    for i, clip in enumerate(vt.clips):
                        x1 = self._ms_to_x(offset)
                        x2 = self._ms_to_x(offset + clip.duration_ms)
                        offset += clip.duration_ms
                        if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                            continue
                        if abs(x - x1) <= _EDGE_PX and i > 0:
                            return i, "clip_left_edge", v_idx
                        if abs(x - x2) <= _EDGE_PX and i < len(vt.clips) - 1:
                            return i, "clip_right_edge", v_idx
                        if x1 <= x <= x2:
                            # --- Check for volume point hits ---
                            if hasattr(clip, "volume_points") and clip.volume_points:
                                rect_y = track_y
                                rect_h = _CLIP_H
                                margin = 4
                                # Helper to map volume to y (same logic as drawing)
                                def vol_to_y(vol):
                                    norm = (2.0 - vol) / 2.0
                                    return rect_y + margin + norm * (rect_h - 2 * margin)
                                
                                for p_idx, p in enumerate(clip.volume_points):
                                    px = x1 + p.offset_ms * self._px_per_ms
                                    py = vol_to_y(p.volume)
                                    if abs(x - px) <= self._VOLUME_POINT_RADIUS + 2 and abs(y - py) <= self._VOLUME_POINT_RADIUS + 2:
                                        # Use a special string or tuple for volume point hit
                                        self._drag_clip_ref = clip
                                        return p_idx, "volume_point", v_idx
                            
                            return i, "clip_body", v_idx

        # Subtitle tracks
        seg_y = self._subtitle_track_y()
        if seg_y <= y < seg_y + _SEG_H:
             if self._track:
                 for i, seg in enumerate(self._track):
                     x1 = self._ms_to_x(seg.start_ms)
                     x2 = self._ms_to_x(seg.end_ms)
                     if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX: continue
                     if abs(x - x1) <= _EDGE_PX: return i, "left_edge", 0
                     if abs(x - x2) <= _EDGE_PX: return i, "right_edge", 0
                     if x1 <= x <= x2: return i, "body", 0

        # Audio tracks
        audio_y = self._audio_track_y()
        if audio_y <= y < audio_y + _AUDIO_H:
             if self._track:
                 for i, seg in enumerate(self._track):
                     if not seg.audio_file: continue
                     x1 = self._ms_to_x(seg.start_ms)
                     x2 = self._ms_to_x(seg.end_ms)
                     if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX: continue
                     if abs(x - x1) <= _EDGE_PX: return i, "left_edge", 0
                     if abs(x - x2) <= _EDGE_PX: return i, "right_edge", 0
                     if x1 <= x <= x2: return i, "body", 0

        # Overlays
        if self._image_overlay_track:
            img_base_y = self._img_overlay_base_y()
            rows = self._compute_overlay_rows()
            total_h = self._img_overlay_total_h(rows)
            if img_base_y <= y <= img_base_y + total_h:
                for i, ov in enumerate(self._image_overlay_track):
                    row = rows[i]
                    ov_y = img_base_y + row * (self._IMG_ROW_H + self._IMG_ROW_GAP)
                    if not (ov_y <= y <= ov_y + self._IMG_ROW_H): continue
                    x1 = self._ms_to_x(ov.start_ms)
                    x2 = self._ms_to_x(ov.end_ms)
                    if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX: continue
                    if abs(x - x1) <= _EDGE_PX: return i, "img_left_edge", 0
                    if abs(x - x2) <= _EDGE_PX: return i, "img_right_edge", 0
                    if x1 <= x <= x2: return i, "img_body", 0

        # Text Overlays
        if self._text_overlay_track:
            text_base_y = self._text_overlay_base_y()
            rows = self._compute_text_overlay_rows()
            for i, overlay in enumerate(self._text_overlay_track.overlays):
                row = rows[i]
                ov_y = text_base_y + row * (self._TEXT_ROW_H + self._TEXT_ROW_GAP)
                if not (ov_y <= y <= ov_y + self._TEXT_ROW_H): continue
                x1 = self._ms_to_x(overlay.start_ms)
                x2 = self._ms_to_x(overlay.end_ms)
                if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX: continue
                if abs(x - x1) <= _EDGE_PX: return i, "text_left_edge", 0
                if abs(x - x2) <= _EDGE_PX: return i, "text_right_edge", 0
                if x1 <= x <= x2: return i, "text_body", 0

        # BGM tracks
        if hasattr(self, "_bgm_tracks"):
            for track_idx, track in enumerate(self._bgm_tracks):
                ty = self._bgm_track_y(track_idx)
                if ty <= y < ty + _BGM_H:
                    for i, clip in enumerate(track.clips):
                        x1 = self._ms_to_x(clip.start_ms)
                        x2 = self._ms_to_x(clip.start_ms + clip.duration_ms)
                        if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                            continue
                        if abs(x - x1) <= _EDGE_PX:
                            return i, "bgm_left_edge", track_idx
                        if abs(x - x2) <= _EDGE_PX:
                            return i, "bgm_right_edge", track_idx
                        if x1 <= x <= x2:
                            return i, "bgm_body", track_idx

        return -1, "", -1

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

    def _start_bgm_drag(self, mode: _DragMode, track_idx: int, clip_idx: int, x: float) -> None:
        """BGM 클립 드래그 시작."""
        self._drag_mode = mode
        self._drag_bgm_track_index = track_idx
        self._drag_bgm_clip_index = clip_idx
        self._drag_start_x = x
        
        track = self._bgm_tracks[track_idx]
        clip = track.clips[clip_idx]
        self._drag_bgm_orig_start_ms = clip.start_ms
        self._drag_bgm_orig_duration_ms = clip.duration_ms
        
        if mode == _DragMode.BGM_MOVE:
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def _handle_bgm_drag(self, x: float) -> None:
        """BGM 클립 드래그 처리."""
        if self._drag_bgm_track_index < 0 or not hasattr(self, "_bgm_tracks"):
            return
        track = self._bgm_tracks[self._drag_bgm_track_index]
        clip = track.clips[self._drag_bgm_clip_index]
        
        dx_ms = (x - self._drag_start_x) / self._px_per_ms if self._px_per_ms > 0 else 0
        
        candidates = sorted(list(self._get_magnetic_snap_candidates()))
        
        if self._drag_mode == _DragMode.BGM_MOVE:
            new_start = int(max(0, self._drag_bgm_orig_start_ms + dx_ms))
            new_start = self._apply_magnetic_snap(new_start, candidates)
            clip.start_ms = new_start
        elif self._drag_mode == _DragMode.BGM_RESIZE_LEFT:
            new_start = int(max(0, self._drag_bgm_orig_start_ms + dx_ms))
            new_start = self._apply_magnetic_snap(new_start, candidates)
            # Duration must be at least 10ms
            new_dur = int(max(10, self._drag_bgm_orig_duration_ms - (new_start - self._drag_bgm_orig_start_ms)))
            # Re-calculate start to match duration clamp
            clip.start_ms = self._drag_bgm_orig_start_ms + (self._drag_bgm_orig_duration_ms - new_dur)
            clip.duration_ms = new_dur
        elif self._drag_mode == _DragMode.BGM_RESIZE_RIGHT:
            new_end = int(self._drag_bgm_orig_start_ms + self._drag_bgm_orig_duration_ms + dx_ms)
            new_end = self._apply_magnetic_snap(new_end, candidates)
            clip.duration_ms = int(max(10, new_end - clip.start_ms))
            
        self.update()

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
            from src.utils.config import VIDEO_EXTENSIONS, AUDIO_EXTENSIONS
            url = mime.urls()[0]
            suffix = Path(url.toLocalFile()).suffix.lower()
            return suffix in VIDEO_EXTENSIONS or suffix in AUDIO_EXTENSIONS
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
        from src.utils.config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS

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
        elif suffix in AUDIO_EXTENSIONS:
            self.audio_file_dropped.emit(file_path, position_ms)
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
