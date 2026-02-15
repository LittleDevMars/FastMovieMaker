"""TimelineDragManager — TimelineWidget의 드래그 관련 로직을 캡슐화.

TimelineWidget에서 ~600줄의 드래그 코드를 분리하여,
TimelineWidget은 마우스 이벤트·공개 API에 집중한다.

Strategy 패턴: 드래그 모드별로 start/update/end 메서드 그룹화.
"""

from __future__ import annotations

import bisect
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from src.ui.timeline_widget import TimelineWidget


# ------------------------------------------------------------------ 상수

class DragMode(Enum):
    """드래그 종류."""
    NONE = auto()
    SEEK = auto()
    MOVE = auto()
    RESIZE_LEFT = auto()
    RESIZE_RIGHT = auto()
    AUDIO_MOVE = auto()
    AUDIO_RESIZE_LEFT = auto()
    AUDIO_RESIZE_RIGHT = auto()
    PLAYHEAD_DRAG = auto()
    PAN_VIEW = auto()
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


class TimelineDragManager:
    """TimelineWidget 전용 드래그 매니저 — 모든 드래그 로직을 소유."""

    def __init__(self, tw: TimelineWidget) -> None:
        self.tw = tw

        # ---- 공통 드래그 상태 ----
        self.mode = DragMode.NONE
        self.seg_index: int = -1
        self.start_x: float = 0.0
        self.orig_start_ms: int = 0
        self.orig_end_ms: int = 0

        # 오디오
        self.orig_audio_start_ms: int = 0
        self.orig_audio_duration_ms: int = 0

        # 텍스트 오버레이
        self.text_index: int = -1
        self.text_orig_start_ms: int = 0
        self.text_orig_end_ms: int = 0

        # 비디오 클립
        self.clip_track_index: int = -1
        self.clip_index: int = -1
        self.orig_source_in: int = 0
        self.orig_source_out: int = 0

        # BGM
        self.bgm_track_index: int = -1
        self.bgm_clip_index: int = -1
        self.bgm_orig_start_ms: int = 0
        self.bgm_orig_duration_ms: int = 0

        # 볼륨 포인트
        self.volume_point_idx: int = -1
        self.clip_ref = None

        # PAN_VIEW
        self.start_visible_ms: float = 0.0

    # ================================================================
    # 드래그 시작
    # ================================================================

    def start_subtitle(self, mode: DragMode, seg_idx: int, x: float) -> None:
        """자막 세그먼트 드래그 시작 (MOVE/RESIZE_LEFT/RESIZE_RIGHT)."""
        tw = self.tw
        if not tw._track or seg_idx < 0 or seg_idx >= len(tw._track):
            return
        seg = tw._track[seg_idx]
        self.mode = mode
        self.seg_index = seg_idx
        self.start_x = x
        self.orig_start_ms = seg.start_ms
        self.orig_end_ms = seg.end_ms
        if seg.audio_file:
            self.orig_audio_start_ms = seg.audio_start_ms
            self.orig_audio_duration_ms = seg.audio_duration_ms
        if mode == DragMode.MOVE:
            tw.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            tw.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def start_clip(self, mode: DragMode, track_idx: int, clip_idx: int, x: float) -> None:
        """비디오 클립 트림 시작."""
        tw = self.tw
        self.mode = mode
        self.clip_track_index = track_idx
        self.clip_index = clip_idx
        self.start_x = x
        if tw._clip_track and 0 <= clip_idx < len(tw._clip_track.clips):
            clip = tw._clip_track.clips[clip_idx]
            self.orig_source_in = clip.source_in_ms
            self.orig_source_out = clip.source_out_ms
        tw.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def start_audio(self, mode: DragMode, x: float) -> None:
        """오디오 트랙 드래그 시작."""
        tw = self.tw
        self.mode = mode
        self.start_x = x
        if tw._track:
            self.orig_audio_start_ms = tw._track.audio_start_ms
            self.orig_audio_duration_ms = tw._track.audio_duration_ms

    def start_text(self, mode: DragMode, index: int, x: float) -> None:
        """텍스트 오버레이 드래그 시작."""
        tw = self.tw
        if not tw._text_overlay_track or index < 0 or index >= len(tw._text_overlay_track.overlays):
            return
        overlay = tw._text_overlay_track.overlays[index]
        self.mode = mode
        self.text_index = index
        self.start_x = x
        self.text_orig_start_ms = overlay.start_ms
        self.text_orig_end_ms = overlay.end_ms
        if mode == DragMode.TEXT_MOVE:
            tw.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            tw.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def start_image(self, mode: DragMode, seg_idx: int, x: float) -> None:
        """이미지 오버레이 드래그 시작."""
        tw = self.tw
        if not tw._image_overlay_track or seg_idx < 0 or seg_idx >= len(tw._image_overlay_track):
            return
        ov = tw._image_overlay_track[seg_idx]
        self.mode = mode
        self.seg_index = seg_idx
        self.start_x = x
        self.orig_start_ms = ov.start_ms
        self.orig_end_ms = ov.end_ms
        if mode == DragMode.IMAGE_MOVE:
            tw.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            tw.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def start_bgm(self, mode: DragMode, track_idx: int, clip_idx: int, x: float) -> None:
        """BGM 클립 드래그 시작."""
        tw = self.tw
        self.mode = mode
        self.start_x = x
        self.bgm_track_index = track_idx
        self.bgm_clip_index = clip_idx
        if 0 <= track_idx < len(tw._bgm_tracks):
            track = tw._bgm_tracks[track_idx]
            if 0 <= clip_idx < len(track.clips):
                clip = track.clips[clip_idx]
                self.bgm_orig_start_ms = clip.start_ms
                self.bgm_orig_duration_ms = clip.duration_ms
        if mode == DragMode.BGM_MOVE:
            tw.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            tw.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def start_playhead(self) -> None:
        """플레이헤드 드래그 시작."""
        self.mode = DragMode.PLAYHEAD_DRAG
        self.tw.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def start_seek(self, x: float) -> None:
        """빈 공간 시크 시작."""
        self.mode = DragMode.SEEK
        self.tw._seek_to_x(x)

    def start_pan_view(self, x: float) -> None:
        """뷰 팬 시작."""
        tw = self.tw
        self.mode = DragMode.PAN_VIEW
        self.start_x = x
        self.start_visible_ms = tw._visible_start_ms
        tw.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

    def start_volume_point(self, point_idx: int, track_idx: int) -> None:
        """볼륨 포인트 드래그 시작."""
        self.mode = DragMode.VOLUME_POINT_MOVE
        self.volume_point_idx = point_idx
        self.clip_track_index = track_idx

    # ================================================================
    # 드래그 업데이트 (on_move)
    # ================================================================

    def on_move(self, x: float, y: float) -> bool:
        """드래그 중 업데이트. 처리했으면 True 반환."""
        m = self.mode
        if m == DragMode.NONE:
            return False

        if m == DragMode.PAN_VIEW:
            self._handle_pan_view(x)
        elif m == DragMode.PLAYHEAD_DRAG:
            self._handle_playhead(x)
        elif m == DragMode.SEEK:
            self.tw._seek_to_x(x)
        elif m in (DragMode.MOVE, DragMode.RESIZE_LEFT, DragMode.RESIZE_RIGHT):
            self._handle_subtitle_drag(x)
        elif m in (DragMode.AUDIO_MOVE, DragMode.AUDIO_RESIZE_LEFT, DragMode.AUDIO_RESIZE_RIGHT):
            self._handle_audio_drag(x)
        elif m in (DragMode.IMAGE_MOVE, DragMode.IMAGE_RESIZE_LEFT, DragMode.IMAGE_RESIZE_RIGHT):
            self._handle_image_drag(x)
        elif m in (DragMode.TEXT_MOVE, DragMode.TEXT_RESIZE_LEFT, DragMode.TEXT_RESIZE_RIGHT):
            self._handle_text_drag(x)
        elif m in (DragMode.CLIP_TRIM_LEFT, DragMode.CLIP_TRIM_RIGHT):
            self._handle_clip_drag(x)
        elif m == DragMode.VOLUME_POINT_MOVE:
            self._handle_volume_point_drag(x, y)
        elif m in (DragMode.BGM_MOVE, DragMode.BGM_RESIZE_LEFT, DragMode.BGM_RESIZE_RIGHT):
            self._handle_bgm_drag(x)
        return True

    # ================================================================
    # 드래그 종료 (on_release)
    # ================================================================

    def on_release(self) -> None:
        """드래그 종료 — 시그널 발행 후 상태 초기화."""
        tw = self.tw
        m = self.mode

        if m in (DragMode.MOVE, DragMode.RESIZE_LEFT, DragMode.RESIZE_RIGHT):
            if tw._track and 0 <= self.seg_index < len(tw._track):
                seg = tw._track[self.seg_index]
                if seg.start_ms != self.orig_start_ms or seg.end_ms != self.orig_end_ms:
                    tw.segment_moved.emit(self.seg_index, seg.start_ms, seg.end_ms)

        elif m in (DragMode.AUDIO_MOVE, DragMode.AUDIO_RESIZE_LEFT, DragMode.AUDIO_RESIZE_RIGHT):
            if tw._track and 0 <= self.seg_index < len(tw._track):
                seg = tw._track[self.seg_index]
                if seg.audio_file and (seg.audio_start_ms != self.orig_audio_start_ms
                                       or seg.audio_duration_ms != self.orig_audio_duration_ms):
                    tw.audio_moved.emit(seg.audio_start_ms, seg.audio_duration_ms)

        elif m in (DragMode.IMAGE_MOVE, DragMode.IMAGE_RESIZE_LEFT, DragMode.IMAGE_RESIZE_RIGHT):
            if tw._image_overlay_track and 0 <= self.seg_index < len(tw._image_overlay_track):
                ov = tw._image_overlay_track[self.seg_index]
                if ov.start_ms != self.orig_start_ms or ov.end_ms != self.orig_end_ms:
                    tw.image_overlay_moved.emit(self.seg_index, ov.start_ms, ov.end_ms)

        elif m in (DragMode.TEXT_MOVE, DragMode.TEXT_RESIZE_LEFT, DragMode.TEXT_RESIZE_RIGHT):
            if tw._text_overlay_track and 0 <= self.text_index < len(tw._text_overlay_track.overlays):
                ov = tw._text_overlay_track.overlays[self.text_index]
                if ov.start_ms != self.text_orig_start_ms or ov.end_ms != self.text_orig_end_ms:
                    tw.text_overlay_moved.emit(self.text_index, ov.start_ms, ov.end_ms)
            self.text_index = -1

        elif m in (DragMode.CLIP_TRIM_LEFT, DragMode.CLIP_TRIM_RIGHT):
            if tw._project and 0 <= self.clip_track_index < len(tw._project.video_tracks):
                vt = tw._project.video_tracks[self.clip_track_index]
                if 0 <= self.clip_index < len(vt.clips):
                    clip = vt.clips[self.clip_index]
                    new_in = clip.source_in_ms
                    new_out = clip.source_out_ms
                    if new_in != self.orig_source_in or new_out != self.orig_source_out:
                        # Undo를 위해 원래 값으로 복원
                        clip.source_in_ms = self.orig_source_in
                        clip.source_out_ms = self.orig_source_out
                        tw.clip_trimmed.emit(self.clip_index, new_in, new_out)
            self.clip_index = -1
            self.clip_track_index = -1

        elif m == DragMode.VOLUME_POINT_MOVE:
            if self.clip_ref:
                self.clip_ref.volume_points.sort(key=lambda p: p.offset_ms)
            self.volume_point_idx = -1
            self.clip_ref = None

        elif m in (DragMode.BGM_MOVE, DragMode.BGM_RESIZE_LEFT, DragMode.BGM_RESIZE_RIGHT):
            if 0 <= self.bgm_track_index < len(tw._bgm_tracks):
                track = tw._bgm_tracks[self.bgm_track_index]
                if 0 <= self.bgm_clip_index < len(track.clips):
                    clip = track.clips[self.bgm_clip_index]
                    new_start = clip.start_ms
                    new_dur = clip.duration_ms
                    if m == DragMode.BGM_MOVE:
                        if new_start != self.bgm_orig_start_ms:
                            clip.start_ms = self.bgm_orig_start_ms
                            tw.bgm_clip_moved.emit(self.bgm_track_index, self.bgm_clip_index, new_start)
                    else:
                        if new_start != self.bgm_orig_start_ms or new_dur != self.bgm_orig_duration_ms:
                            clip.start_ms = self.bgm_orig_start_ms
                            clip.duration_ms = self.bgm_orig_duration_ms
                            tw.bgm_clip_trimmed.emit(
                                self.bgm_track_index, self.bgm_clip_index, new_start, new_dur
                            )

        # 상태 초기화
        self.mode = DragMode.NONE
        self.seg_index = -1
        tw.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        tw.update()

    # ================================================================
    # 볼륨 포인트 Shift+Click
    # ================================================================

    def handle_volume_point_shift_click(self, track_idx: int, p_idx_maybe: int, x: float, y: float) -> None:
        """Shift+Click으로 볼륨 포인트 추가/제거."""
        tw = self.tw
        from src.ui.timeline_widget import _CLIP_H
        if not tw._project or track_idx < 0:
            return
        vt = tw._project.video_tracks[track_idx]
        clip = None
        offset = 0
        for _i, c in enumerate(vt.clips):
            x1 = tw._ms_to_x(offset)
            x2 = tw._ms_to_x(offset + c.duration_ms)
            if x1 <= x <= x2:
                clip = c
                break
            offset += c.duration_ms
        if not clip:
            return
        timeline_ms = tw._x_to_ms(x)
        clip_start_ms = tw.clip_timeline_start_ms(clip)
        offset_ms = int(max(0, min(clip.duration_ms, timeline_ms - clip_start_ms)))
        rect_y = tw._video_track_y(track_idx)
        rect_h = _CLIP_H
        margin = 4
        norm = (y - rect_y - margin) / (rect_h - 2 * margin)
        vol = 2.0 - (norm * 2.0)
        vol = max(0.0, min(2.0, vol))
        hit_p_idx = -1
        for i, p in enumerate(clip.volume_points):
            px = tw._ms_to_x(clip_start_ms + p.offset_ms)
            if abs(x - px) <= tw._VOLUME_POINT_RADIUS + 3:
                hit_p_idx = i
                break
        from src.models.video_clip import VolumePoint
        if hit_p_idx != -1:
            clip.volume_points.pop(hit_p_idx)
        else:
            clip.volume_points.append(VolumePoint(offset_ms=offset_ms, volume=vol))
            clip.volume_points.sort(key=lambda p: p.offset_ms)
        tw.update()

    # ================================================================
    # 자석 스냅 헬퍼
    # ================================================================

    def get_snap_candidates(
        self,
        skip_seg_index: int = -1,
        skip_clip_index: int = -1,
        skip_img_index: int = -1,
    ) -> list[int]:
        """자석 스냅을 위한 후보 지점(ms) 수집."""
        tw = self.tw
        candidates: set[int] = {0}
        if tw._duration_ms > 0:
            candidates.add(tw._duration_ms)
        candidates.add(tw._playhead_ms)

        # Video Clips
        if tw._clip_track:
            offset = 0
            for i, clip in enumerate(tw._clip_track.clips):
                start = offset
                end = offset + clip.duration_ms
                offset += clip.duration_ms
                if i != skip_clip_index:
                    candidates.add(start)
                    candidates.add(end)

        # Subtitle Segments
        if tw._track:
            for i, seg in enumerate(tw._track):
                if i != skip_seg_index:
                    candidates.add(seg.start_ms)
                    candidates.add(seg.end_ms)
                    if seg.audio_file:
                        candidates.add(seg.audio_start_ms)
                        candidates.add(seg.audio_start_ms + seg.audio_duration_ms)

        # BGM Clips
        if hasattr(tw, "_bgm_tracks"):
            for t_idx, track in enumerate(tw._bgm_tracks):
                for i, clip in enumerate(track.clips):
                    if not (t_idx == self.bgm_track_index and i == self.bgm_clip_index):
                        candidates.add(clip.start_ms)
                        candidates.add(clip.start_ms + clip.duration_ms)

        # Image Overlays
        if tw._image_overlay_track:
            for i, ov in enumerate(tw._image_overlay_track):
                if i != skip_img_index:
                    candidates.add(ov.start_ms)
                    candidates.add(ov.end_ms)

        return sorted(candidates)

    def apply_snap(self, ms: int, candidates: list[int]) -> int:
        """이진 탐색(CLRS Ch.2.3)으로 가장 가까운 후보에 자석 스냅 적용.

        candidates는 정렬된 상태여야 한다 (get_snap_candidates가 sorted 반환).
        _ms_to_x가 선형 변환이므로 ms 공간의 최근접 = 픽셀 공간의 최근접.
        """
        tw = self.tw
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            tw._snap_guide_x = None
            return ms
        if not tw._snap_enabled or tw._px_per_ms <= 0:
            tw._snap_guide_x = None
            return ms
        if not candidates:
            tw._snap_guide_x = None
            return ms

        # 이진 탐색으로 ms에 가장 가까운 후보 찾기
        idx = bisect.bisect_left(candidates, ms)
        closest_ms = -1
        min_dist = float("inf")
        # idx-1, idx 두 후보만 비교하면 충분
        for i in (idx - 1, idx):
            if 0 <= i < len(candidates):
                dist = abs(candidates[i] - ms)
                if dist < min_dist:
                    min_dist = dist
                    closest_ms = candidates[i]

        # 픽셀 거리로 threshold 확인
        threshold_px = tw._SNAP_THRESHOLD_PX
        dist_px = abs(tw._ms_to_x(closest_ms) - tw._ms_to_x(ms))
        if dist_px <= threshold_px:
            tw._snap_guide_x = tw._ms_to_x(closest_ms)
            return closest_ms

        tw._snap_guide_x = None
        return ms

    # ================================================================
    # 개별 드래그 핸들러
    # ================================================================

    def _handle_pan_view(self, x: float) -> None:
        tw = self.tw
        diff_gx = self.start_x - x
        diff_ms = diff_gx / tw._px_per_ms if tw._px_per_ms > 0 else 0
        new_start = self.start_visible_ms + diff_ms
        tw._visible_start_ms = max(0.0, min(float(tw._duration_ms), new_start))
        tw._clamp_visible_start(tw._visible_range_ms())
        tw._invalidate_static_cache()
        tw.update()

    def _handle_playhead(self, x: float) -> None:
        tw = self.tw
        current_ms = tw._x_to_ms(x)
        candidates = self.get_snap_candidates()
        snapped_ms = self.apply_snap(int(current_ms), candidates)
        if tw._snap_guide_x is None:
            snapped_ms = tw._snap_ms(int(current_ms))
        tw._playhead_ms = max(0, min(tw._duration_ms, snapped_ms))
        tw.update()
        tw.seek_requested.emit(tw._playhead_ms)

    # ---- 자막 드래그 ----

    def _handle_subtitle_drag(self, x: float) -> None:
        """자막 MOVE/RESIZE_LEFT/RESIZE_RIGHT 처리."""
        tw = self.tw
        if not tw._track or self.seg_index < 0:
            return
        seg = tw._track[self.seg_index]
        current_ms = tw._x_to_ms(x)

        if self.mode == DragMode.MOVE:
            duration = self.orig_end_ms - self.orig_start_ms
            diff_ms = current_ms - tw._x_to_ms(self.start_x)
            new_start = self.orig_start_ms + int(diff_ms)

            candidates = self.get_snap_candidates(skip_seg_index=self.seg_index)

            # start 스냅
            snapped_start = self.apply_snap(new_start, candidates)
            guide_x_start = tw._snap_guide_x
            # end 스냅
            new_end_tentative = new_start + duration
            snapped_end = self.apply_snap(new_end_tentative, candidates)
            guide_x_end = tw._snap_guide_x

            is_start_snap = snapped_start != new_start
            is_end_snap = snapped_end != new_end_tentative
            final_start = new_start

            if is_start_snap and is_end_snap:
                if abs(snapped_start - new_start) <= abs(snapped_end - new_end_tentative):
                    final_start = snapped_start
                    tw._snap_guide_x = guide_x_start
                else:
                    final_start = snapped_end - duration
                    tw._snap_guide_x = guide_x_end
            elif is_start_snap:
                final_start = snapped_start
                tw._snap_guide_x = guide_x_start
            elif is_end_snap:
                final_start = snapped_end - duration
                tw._snap_guide_x = guide_x_end
            else:
                tw._snap_guide_x = None

            if not is_start_snap and not is_end_snap:
                final_start = tw._snap_ms(final_start)

            final_start = max(0, min(tw._duration_ms - duration, final_start))
            new_end = final_start + duration

            audio_offset = 0
            if seg.audio_file:
                audio_offset = self.orig_audio_start_ms - self.orig_start_ms

            seg.start_ms = final_start
            seg.end_ms = new_end
            if seg.audio_file:
                seg.audio_start_ms = final_start + audio_offset

            tw.segment_moved.emit(self.seg_index, final_start, new_end)
            if seg.audio_file:
                tw.audio_moved.emit(seg.audio_start_ms, self.orig_audio_duration_ms)

        elif self.mode == DragMode.RESIZE_LEFT:
            limit_right = seg.end_ms - 100
            new_start = int(current_ms)
            candidates = self.get_snap_candidates(skip_seg_index=self.seg_index)
            new_start = self.apply_snap(new_start, candidates)
            if tw._snap_guide_x is None:
                new_start = tw._snap_ms(new_start)
            new_start = max(0, min(limit_right, new_start))
            seg.start_ms = new_start
            tw.segment_moved.emit(self.seg_index, new_start, seg.end_ms)

        elif self.mode == DragMode.RESIZE_RIGHT:
            limit_left = seg.start_ms + 100
            new_end = int(current_ms)
            candidates = self.get_snap_candidates(skip_seg_index=self.seg_index)
            new_end = self.apply_snap(new_end, candidates)
            if tw._snap_guide_x is None:
                new_end = tw._snap_ms(new_end)
            new_end = max(limit_left, min(tw._duration_ms, new_end))
            seg.end_ms = new_end
            tw.segment_moved.emit(self.seg_index, seg.start_ms, new_end)

        tw._invalidate_static_cache()
        tw.update()

    # ---- 오디오 드래그 ----

    def _handle_audio_drag(self, x: float) -> None:
        """오디오 트랙 이동/리사이즈 처리."""
        tw = self.tw
        if not tw._track or self.seg_index < 0:
            return
        current_ms = tw._x_to_ms(x)

        if self.mode == DragMode.AUDIO_MOVE:
            seg = tw._track[self.seg_index]
            if not seg.audio_file:
                return
            diff_ms = current_ms - tw._x_to_ms(self.start_x)
            new_audio_start = self.orig_audio_start_ms + int(diff_ms)

            candidates = self.get_snap_candidates(skip_seg_index=self.seg_index)
            snapped_start = self.apply_snap(new_audio_start, candidates)
            guide_x_start = tw._snap_guide_x
            new_audio_end = new_audio_start + self.orig_audio_duration_ms
            snapped_end = self.apply_snap(new_audio_end, candidates)
            guide_x_end = tw._snap_guide_x

            is_start_snap = snapped_start != new_audio_start
            is_end_snap = snapped_end != new_audio_end

            if is_start_snap and is_end_snap:
                if abs(snapped_start - new_audio_start) <= abs(snapped_end - new_audio_end):
                    new_audio_start = snapped_start
                    tw._snap_guide_x = guide_x_start
                else:
                    new_audio_start = snapped_end - self.orig_audio_duration_ms
                    tw._snap_guide_x = guide_x_end
            elif is_start_snap:
                new_audio_start = snapped_start
                tw._snap_guide_x = guide_x_start
            elif is_end_snap:
                new_audio_start = snapped_end - self.orig_audio_duration_ms
                tw._snap_guide_x = guide_x_end
            else:
                tw._snap_guide_x = None
                new_audio_start = tw._snap_ms(new_audio_start)

            new_audio_start = max(0, min(tw._duration_ms - self.orig_audio_duration_ms, new_audio_start))
            seg.audio_start_ms = new_audio_start
            tw.audio_moved.emit(new_audio_start, self.orig_audio_duration_ms)

        elif self.mode == DragMode.AUDIO_RESIZE_LEFT:
            candidates = self.get_snap_candidates(skip_seg_index=self.seg_index)
            diff_ms = int((x - self.start_x) / tw._px_per_ms) if tw._px_per_ms > 0 else 0
            new_start = self.orig_audio_start_ms + diff_ms
            new_start = self.apply_snap(new_start, candidates)
            if tw._snap_guide_x is None:
                new_start = tw._snap_ms(new_start)
            new_start = max(0, min(new_start, tw._track.audio_start_ms + tw._track.audio_duration_ms - 100))
            duration_change = tw._track.audio_start_ms - new_start
            tw._track.audio_start_ms = new_start
            tw._track.audio_duration_ms += duration_change

        elif self.mode == DragMode.AUDIO_RESIZE_RIGHT:
            candidates = self.get_snap_candidates(skip_seg_index=self.seg_index)
            dx_ms = int((x - self.start_x) / tw._px_per_ms) if tw._px_per_ms > 0 else 0
            new_duration = self.orig_audio_duration_ms + dx_ms
            new_end = tw._track.audio_start_ms + new_duration
            new_end = self.apply_snap(new_end, candidates)
            if tw._snap_guide_x is None:
                new_end = tw._snap_ms(new_end)
            new_duration = new_end - tw._track.audio_start_ms
            new_duration = max(100, new_duration)
            max_duration = tw._duration_ms - tw._track.audio_start_ms
            tw._track.audio_duration_ms = min(new_duration, max_duration)

        tw._invalidate_static_cache()
        tw.update()

    # ---- 이미지 오버레이 드래그 ----

    def _handle_image_drag(self, x: float) -> None:
        """이미지 오버레이 이동/리사이즈 처리."""
        tw = self.tw
        if not tw._image_overlay_track or self.seg_index < 0:
            return
        ov = tw._image_overlay_track[self.seg_index]
        current_ms = tw._x_to_ms(x)

        if self.mode == DragMode.IMAGE_MOVE:
            duration = self.orig_end_ms - self.orig_start_ms
            diff_ms = current_ms - tw._x_to_ms(self.start_x)
            new_start = self.orig_start_ms + int(diff_ms)

            candidates = self.get_snap_candidates(skip_img_index=self.seg_index)
            snapped_start = self.apply_snap(new_start, candidates)
            guide_x_start = tw._snap_guide_x
            new_end_tentative = new_start + duration
            snapped_end = self.apply_snap(new_end_tentative, candidates)
            guide_x_end = tw._snap_guide_x

            is_start_snap = snapped_start != new_start
            is_end_snap = snapped_end != new_end_tentative
            final_start = new_start

            if is_start_snap and is_end_snap:
                if abs(snapped_start - new_start) <= abs(snapped_end - new_end_tentative):
                    final_start = snapped_start
                    tw._snap_guide_x = guide_x_start
                else:
                    final_start = snapped_end - duration
                    tw._snap_guide_x = guide_x_end
            elif is_start_snap:
                final_start = snapped_start
                tw._snap_guide_x = guide_x_start
            elif is_end_snap:
                final_start = snapped_end - duration
                tw._snap_guide_x = guide_x_end
            else:
                tw._snap_guide_x = None
                final_start = tw._snap_ms(final_start)

            final_start = max(0, min(tw._duration_ms - duration, final_start))
            ov.start_ms = final_start
            ov.end_ms = final_start + duration
            tw.image_overlay_moved.emit(self.seg_index, ov.start_ms, ov.end_ms)

        elif self.mode == DragMode.IMAGE_RESIZE_LEFT:
            limit_right = ov.end_ms - 100
            new_start = int(current_ms)
            candidates = self.get_snap_candidates(skip_img_index=self.seg_index)
            new_start = self.apply_snap(new_start, candidates)
            if tw._snap_guide_x is None:
                new_start = tw._snap_ms(new_start)
            new_start = max(0, min(limit_right, new_start))
            ov.start_ms = new_start
            tw.image_overlay_moved.emit(self.seg_index, ov.start_ms, ov.end_ms)

        elif self.mode == DragMode.IMAGE_RESIZE_RIGHT:
            limit_left = ov.start_ms + 100
            new_end = int(current_ms)
            candidates = self.get_snap_candidates(skip_img_index=self.seg_index)
            new_end = self.apply_snap(new_end, candidates)
            if tw._snap_guide_x is None:
                new_end = tw._snap_ms(new_end)
            new_end = max(limit_left, min(tw._duration_ms, new_end))
            ov.end_ms = new_end
            tw.image_overlay_moved.emit(self.seg_index, ov.start_ms, ov.end_ms)

        tw._invalidate_static_cache()
        tw.update()

    # ---- 텍스트 오버레이 드래그 ----

    def _handle_text_drag(self, x: float) -> None:
        """텍스트 오버레이 이동/리사이즈 처리."""
        tw = self.tw
        if not tw._text_overlay_track or self.text_index < 0:
            return
        if self.text_index >= len(tw._text_overlay_track.overlays):
            return
        overlay = tw._text_overlay_track.overlays[self.text_index]
        dx_ms = int((x - self.start_x) / tw._px_per_ms) if tw._px_per_ms > 0 else 0

        if self.mode == DragMode.TEXT_MOVE:
            new_start = max(0, self.text_orig_start_ms + dx_ms)
            duration = self.text_orig_end_ms - self.text_orig_start_ms
            overlay.start_ms = int(new_start)
            overlay.end_ms = int(new_start + duration)
        elif self.mode == DragMode.TEXT_RESIZE_LEFT:
            new_start = max(0, self.text_orig_start_ms + dx_ms)
            if new_start < self.text_orig_end_ms - 100:
                overlay.start_ms = int(new_start)
        elif self.mode == DragMode.TEXT_RESIZE_RIGHT:
            new_end = max(self.text_orig_start_ms + 100, self.text_orig_end_ms + dx_ms)
            overlay.end_ms = int(new_end)

        tw._invalidate_static_cache()
        tw.update()

    # ---- 비디오 클립 드래그 ----

    def _handle_clip_drag(self, x: float) -> None:
        """비디오 클립 트림 처리."""
        tw = self.tw
        if not tw._project or self.clip_track_index < 0:
            return
        vt = tw._project.video_tracks[self.clip_track_index]
        if self.clip_index < 0 or self.clip_index >= len(vt.clips):
            return

        dx_ms = int((x - self.start_x) / tw._px_per_ms) if tw._px_per_ms > 0 else 0
        clip = vt.clips[self.clip_index]

        boundaries = vt.clip_boundaries_ms()
        if self.clip_index >= len(boundaries):
            return
        clip_start_ms = boundaries[self.clip_index]
        candidates = self.get_snap_candidates(skip_clip_index=self.clip_index)

        if self.mode == DragMode.CLIP_TRIM_LEFT:
            old_visual_duration = (self.orig_source_out - self.orig_source_in) / clip.speed
            new_visual_duration = max(100 / clip.speed, old_visual_duration - dx_ms)
            new_end = clip_start_ms + new_visual_duration

            snapped_end = self.apply_snap(new_end, candidates)
            if tw._snap_guide_x is None:
                snapped_end = tw._snap_ms(int(new_end))

            final_visual_duration = snapped_end - clip_start_ms
            if final_visual_duration < 100 / clip.speed:
                final_visual_duration = 100 / clip.speed
            clip.source_in_ms = int(clip.source_out_ms - (final_visual_duration * clip.speed))

        elif self.mode == DragMode.CLIP_TRIM_RIGHT:
            old_visual_duration = (self.orig_source_out - self.orig_source_in) / clip.speed
            new_visual_duration = max(100 / clip.speed, old_visual_duration + dx_ms)
            new_end = clip_start_ms + new_visual_duration

            snapped_end = self.apply_snap(new_end, candidates)
            if tw._snap_guide_x is None:
                snapped_end = tw._snap_ms(int(new_end))

            final_visual_duration = snapped_end - clip_start_ms
            if final_visual_duration < 100 / clip.speed:
                final_visual_duration = 100 / clip.speed
            clip.source_out_ms = int(clip.source_in_ms + (final_visual_duration * clip.speed))

        tw._invalidate_static_cache()
        tw.update()

    # ---- 볼륨 포인트 드래그 ----

    def _handle_volume_point_drag(self, x: float, y: float) -> None:
        """볼륨 포인트 드래그로 볼륨·오프셋 변경."""
        tw = self.tw
        from src.ui.timeline_widget import _CLIP_H
        if not self.clip_ref:
            return
        clip = self.clip_ref
        p_idx = self.volume_point_idx
        if p_idx < 0 or p_idx >= len(clip.volume_points):
            return
        p = clip.volume_points[p_idx]
        timeline_ms = tw._x_to_ms(x)
        clip_start_ms = tw.clip_timeline_start_ms(clip)
        new_offset = int(max(0, min(clip.duration_ms, timeline_ms - clip_start_ms)))
        rect_y = tw._video_track_y(tw._selected_clip_track_index)
        rect_h = _CLIP_H
        margin = 4
        norm = (y - rect_y - margin) / (rect_h - 2 * margin)
        new_vol = 2.0 - (norm * 2.0)
        new_vol = max(0.0, min(2.0, new_vol))
        p.offset_ms = new_offset
        p.volume = new_vol
        tw.update()

    # ---- BGM 드래그 ----

    def _handle_bgm_drag(self, x: float) -> None:
        """BGM 클립 드래그 처리."""
        tw = self.tw
        if self.bgm_track_index < 0 or not hasattr(tw, "_bgm_tracks"):
            return
        track = tw._bgm_tracks[self.bgm_track_index]
        clip = track.clips[self.bgm_clip_index]

        dx_ms = (x - self.start_x) / tw._px_per_ms if tw._px_per_ms > 0 else 0
        candidates = self.get_snap_candidates()

        if self.mode == DragMode.BGM_MOVE:
            new_start = int(max(0, self.bgm_orig_start_ms + dx_ms))
            new_start = self.apply_snap(new_start, candidates)
            clip.start_ms = new_start
        elif self.mode == DragMode.BGM_RESIZE_LEFT:
            new_start = int(max(0, self.bgm_orig_start_ms + dx_ms))
            new_start = self.apply_snap(new_start, candidates)
            new_dur = int(max(10, self.bgm_orig_duration_ms - (new_start - self.bgm_orig_start_ms)))
            clip.start_ms = self.bgm_orig_start_ms + (self.bgm_orig_duration_ms - new_dur)
            clip.duration_ms = new_dur
        elif self.mode == DragMode.BGM_RESIZE_RIGHT:
            new_end = int(self.bgm_orig_start_ms + self.bgm_orig_duration_ms + dx_ms)
            new_end = self.apply_snap(new_end, candidates)
            clip.duration_ms = int(max(10, new_end - clip.start_ms))

        tw.update()
