"""커스텀 페인팅 타임라인 위젯: 자막 블록, 플레이헤드, 오디오/이미지 오버레이 표시."""

from __future__ import annotations

from src.utils.i18n import tr

from PySide6.QtCore import Qt, Signal, QPoint, QRectF, Slot
from PySide6.QtGui import (
    QCursor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QMouseEvent,
    QPaintEvent,
    QPixmap,
    QWheelEvent,
)


from PySide6.QtWidgets import QMenu, QWidget

from src.models.image_overlay import ImageOverlayTrack
from src.models.subtitle import SubtitleTrack
from src.models.video_clip import VideoClip, VideoClipTrack
from src.services.waveform_service import WaveformData
from src.services.timeline_waveform_service import TimelineWaveformService
from src.ui.timeline_painter import TimelinePainter
from src.ui.timeline_drag import DragMode, TimelineDragManager
from src.utils.config import TIMELINE_HEIGHT


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

    # ---- 색상 상수는 TimelinePainter로 이동됨 (src/ui/timeline_painter.py) ----
    # 아래는 비-페인팅 코드(히트테스트, 레이아웃 계산)에서도 사용되어 유지하는 상수들

    # Snap
    _SNAP_THRESHOLD_PX = 10

    # Audio Envelope hit-test
    _VOLUME_POINT_RADIUS = 4

    # Image Overlay Layout
    _IMG_ROW_H = 40
    _IMG_ROW_GAP = 4

    # Text Overlay Layout
    _TEXT_ROW_H = 28
    _TEXT_ROW_GAP = 4

    # Thumbnail Layout - LOD System
    # (min_px_per_ms, thumbnail_interval_px, min_clip_width_px)
    _LOD_LEVELS = [
        (0.5,   200,  50),   # LOD 0: Very zoomed out - wide spacing
        (0.1,   100,  30),   # LOD 1: Normal - default spacing
        (0.05,  50,   20),   # LOD 2: Zoomed in - narrow spacing
        (0.0,   25,   10),   # LOD 3: Very zoomed in - very narrow spacing
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

        # 이미지 오버레이 트랙
        self._image_overlay_track: ImageOverlayTrack | None = None
        self._selected_overlay_index: int = -1

        # 텍스트 오버레이 트랙
        self._text_overlay_track = None  # TextOverlayTrack | None
        self._selected_text_overlay_index: int = -1

        # 비디오 클립 트랙
        self._clip_track: VideoClipTrack | None = None
        self._selected_clip_track_index: int = -1
        self._selected_clip_index: int = -1

        # BGM 트랙 상태
        self._bgm_tracks: list = []  # AudioTrack list
        self._selected_bgm_track_index: int = -1
        self._selected_bgm_clip_index: int = -1

        # 프레임 스냅 FPS (0 = 비활성화)
        self._snap_fps: int = 0

        # 자석 스냅 상태
        self._snap_enabled: bool = True
        self._snap_guide_x: float | None = None

        # 웨이브폼 서비스 및 데이터 캐시
        self._waveform_service = None
        self._waveform_data = None  # Global project waveform (legacy)
        # _waveform_image_cache, _waveform_cache_key → TimelinePainter에서 관리

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

        # 페인터 (렌더링 로직 위임)
        self._painter = TimelinePainter(self)
        # 드래그 매니저 (드래그 로직 위임)
        self._drag_mgr = TimelineDragManager(self)

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

    def _compute_overlay_rows(self) -> list[int]:
        """이미지 오버레이의 행 배치 계산 (겹치는 오버레이를 다른 행에 배치).

        Greedy interval packing: 각 오버레이를 겹치지 않는 첫 번째 행에 배치.
        """
        if not self._image_overlay_track:
            return []
        rows: list[int] = []
        row_ends: list[int] = []  # 각 행에서 마지막 오버레이의 end_ms
        for ov in self._image_overlay_track:
            placed = False
            for r in range(len(row_ends)):
                if ov.start_ms >= row_ends[r]:
                    rows.append(r)
                    row_ends[r] = ov.end_ms
                    placed = True
                    break
            if not placed:
                rows.append(len(row_ends))
                row_ends.append(ov.end_ms)
        return rows

    def _compute_text_overlay_rows(self) -> list[int]:
        """텍스트 오버레이의 행 배치 계산 (겹치는 오버레이를 다른 행에 배치)."""
        if not self._text_overlay_track or len(self._text_overlay_track) == 0:
            return []
        rows: list[int] = []
        row_ends: list[int] = []
        for overlay in self._text_overlay_track.overlays:
            placed = False
            for r in range(len(row_ends)):
                if overlay.start_ms >= row_ends[r]:
                    rows.append(r)
                    row_ends[r] = overlay.end_ms
                    placed = True
                    break
            if not placed:
                rows.append(len(row_ends))
                row_ends.append(overlay.end_ms)
        return rows

    def _img_overlay_total_h(self, rows: list[int]) -> int:
        """이미지 오버레이 영역의 총 높이 (행 수 기반)."""
        if not rows:
            return 0
        num_rows = max(rows) + 1
        return num_rows * (self._IMG_ROW_H + self._IMG_ROW_GAP)

    def _text_overlay_base_y(self) -> int:
        """텍스트 오버레이 영역의 Y 시작 위치."""
        img_rows = self._compute_overlay_rows()
        img_total_h = self._img_overlay_total_h(img_rows)
        gap = 4 if img_total_h > 0 else 0
        return self._img_overlay_base_y() + img_total_h + gap

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
        if self._drag_mgr.mode == DragMode.PLAYHEAD_DRAG:
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
        self._painter._waveform_image_cache = None
        self._painter._waveform_cache_key = None
        self._invalidate_static_cache()
        self.update()

    def clear_waveform(self) -> None:
        """웨이브폼 제거."""
        self._waveform_service = None
        self._waveform_data = None  # Global project waveform (legacy)
        self._painter._waveform_image_cache = None
        self._painter._waveform_cache_key = None
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
        self._painter.paint()

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
        dm = self._drag_mgr

        # Shift + 클릭 드래그: 뷰 팬 또는 볼륨 포인트 토글
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            seg_idx, hit, v_idx = self._hit_test(x, y)
            if hit in ("clip_body", "volume_point"):
                dm.handle_volume_point_shift_click(v_idx, seg_idx, x, y)
                return
            dm.start_pan_view(x)
            return

        seg_idx, hit, v_idx = self._hit_test(x, y)

        # 플레이헤드 드래그
        if hit == "playhead":
            dm.start_playhead()
            return

        # 비디오 클립 영역
        if hit.startswith("clip"):
            vt = self._project.video_tracks[v_idx] if self._project else None
            if vt and vt.locked:
                return
            if hit == "volume_point":
                self._selected_clip_track_index = v_idx
                self._selected_clip_index = seg_idx
                dm.start_volume_point(seg_idx, v_idx)
                # _hit_test에서 dm.clip_ref를 설정함
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
                dm.start_clip(DragMode.CLIP_TRIM_RIGHT, v_idx, seg_idx, x)
                self.clip_selected.emit(v_idx, seg_idx)
            self.update()
            return

        # 오디오 트랙 영역
        if hit.startswith("audio"):
            if self._track and self._track.locked:
                return
            audio_mode_map = {"body": DragMode.AUDIO_MOVE, "left_edge": DragMode.AUDIO_RESIZE_LEFT,
                              "right_edge": DragMode.AUDIO_RESIZE_RIGHT}
            if hit in audio_mode_map:
                self._audio_selected = True
                self._selected_index = seg_idx
                self._selected_overlay_index = -1
                dm.start_audio(audio_mode_map[hit], x)
                self.segment_selected.emit(seg_idx)
            self.update()
            return

        # 이미지 오버레이 영역
        if hit.startswith("img"):
            if self._image_overlay_track and self._image_overlay_track.locked:
                return
            img_mode_map = {"img_left_edge": DragMode.IMAGE_RESIZE_LEFT,
                            "img_right_edge": DragMode.IMAGE_RESIZE_RIGHT,
                            "img_body": DragMode.IMAGE_MOVE}
            if hit in img_mode_map:
                self._selected_overlay_index = seg_idx
                self._selected_index = -1
                dm.start_image(img_mode_map[hit], seg_idx, x)
                self.image_overlay_selected.emit(seg_idx)
            return

        # 텍스트 오버레이 영역
        if hit.startswith("text"):
            if self._text_overlay_track:
                text_mode_map = {"text_left_edge": DragMode.TEXT_RESIZE_LEFT,
                                 "text_right_edge": DragMode.TEXT_RESIZE_RIGHT,
                                 "text_body": DragMode.TEXT_MOVE}
                if hit in text_mode_map:
                    self._selected_text_overlay_index = seg_idx
                    self._selected_index = -1
                    self._selected_overlay_index = -1
                    dm.start_text(text_mode_map[hit], seg_idx, x)
                    self.text_overlay_selected.emit(seg_idx)
            return

        # BGM 영역
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
                bgm_mode_map = {"bgm_left_edge": DragMode.BGM_RESIZE_LEFT,
                                "bgm_right_edge": DragMode.BGM_RESIZE_RIGHT,
                                "bgm_body": DragMode.BGM_MOVE}
                if hit in bgm_mode_map:
                    dm.start_bgm(bgm_mode_map[hit], v_idx, seg_idx, x)
                self.update()
                return

        # 자막 세그먼트
        elif hit in ("left_edge", "right_edge", "body"):
            if self._track and self._track.locked:
                return
            seg_mode_map = {"left_edge": DragMode.RESIZE_LEFT,
                            "right_edge": DragMode.RESIZE_RIGHT,
                            "body": DragMode.MOVE}
            self._audio_selected = False
            self._selected_overlay_index = -1
            if hit == "body":
                self._selected_index = seg_idx
                self.segment_selected.emit(seg_idx)
            dm.start_subtitle(seg_mode_map[hit], seg_idx, x)
            return
        else:
            self._audio_selected = False
            self._selected_index = -1
            self._selected_overlay_index = -1
            dm.start_seek(x)

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

        # 드래그 매니저에게 위임
        if self._drag_mgr.on_move(x, y):
            return

        # 호버 시 커서 변경 (드래그 중이 아닐 때)
        seg_idx, hit, v_idx = self._hit_test(x, y)
        if hit == "playhead":
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif hit in ("left_edge", "right_edge", "img_left_edge", "img_right_edge",
                     "clip_left_edge", "clip_right_edge", "audio_left_edge", "audio_right_edge",
                     "bgm_left_edge", "bgm_right_edge"):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif hit in ("body", "audio_body", "img_body", "clip_body", "bgm_body"):
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_mgr.on_release()

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
                                        self._drag_mgr.clip_ref = clip
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
