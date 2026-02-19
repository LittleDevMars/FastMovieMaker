"""TimelinePainter — TimelineWidget의 모든 렌더링/페인팅 로직을 캡슐화.

TimelineWidget에서 ~725줄의 페인팅 코드를 분리하여,
TimelineWidget은 이벤트 핸들링·공개 API에 집중한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPoint, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygon,
    QPolygonF,
)

import numpy as np

from src.models.video_clip import VideoClip, VideoClipTrack
from src.services.waveform_service import WaveformData
from src.utils.time_utils import ms_to_display

if TYPE_CHECKING:
    from src.ui.timeline_widget import TimelineWidget

# ---- Track Layout 상수 (TimelineWidget과 공유) ----
_RULER_H = 14
_CLIP_H = 32
_SEG_H = 40
_AUDIO_H = 34
_WAVEFORM_H = 45
_BGM_H = 34


class TimelinePainter:
    """TimelineWidget 전용 렌더러 — 모든 _draw_* 메서드를 소유."""

    # ---- 색상/스타일 상수 ----
    # Background
    _BG_COLOR = QColor(18, 18, 18)
    _RULER_BG_COLOR = QColor(25, 25, 25)
    _RULER_COLOR = QColor(60, 60, 60)
    _RULER_TEXT_COLOR = QColor(140, 140, 140)

    # Subtitle Segments
    _SEGMENT_COLOR_TOP = QColor(60, 140, 220)
    _SEGMENT_COLOR_BOT = QColor(40, 100, 180)
    _SEGMENT_BORDER = QColor(80, 170, 255)
    _SELECTED_BORDER = QColor(100, 220, 255)
    _SELECTED_GLOW = QColor(100, 220, 255, 60)

    # Snap
    _SNAP_GUIDE_COLOR = QColor(255, 255, 0, 200)

    # Playhead
    _PLAYHEAD_COLOR = QColor(255, 60, 80)
    _PLAYHEAD_LINE_COLOR = QColor(255, 60, 80, 200)

    # Audio (TTS)
    _AUDIO_COLOR_TOP = QColor(80, 180, 100)
    _AUDIO_BORDER = QColor(100, 200, 120)

    # BGM
    _BGM_COLOR_TOP = QColor(100, 80, 200)
    _BGM_COLOR_BOT = QColor(60, 40, 160)
    _BGM_BORDER = QColor(130, 100, 240)
    _BGM_SELECTED_BORDER = QColor(100, 220, 255)
    _BGM_SELECTED_COLOR = QColor(40, 20, 100)

    # Waveform
    _WAVEFORM_FILL = QColor(255, 140, 40, 120)
    _WAVEFORM_EDGE = QColor(255, 180, 80, 200)
    _WAVEFORM_CENTER = QColor(255, 220, 150)

    # Volume Envelope
    _VOLUME_LINE_COLOR = QColor(255, 255, 255, 200)
    _VOLUME_POINT_COLOR = QColor(255, 255, 255)
    _VOLUME_POINT_RADIUS = 4

    # Image Overlay
    _IMG_OVERLAY_COLOR = QColor(160, 90, 220, 180)
    _IMG_OVERLAY_BORDER = QColor(190, 120, 240)
    _IMG_OVERLAY_SELECTED_BORDER = QColor(100, 220, 255)
    _IMG_OVERLAY_SELECTED_COLOR = QColor(0, 100, 140)

    # Text Overlay
    _TEXT_OVERLAY_COLOR = QColor(255, 180, 80, 180)
    _TEXT_OVERLAY_BORDER = QColor(255, 200, 120)
    _TEXT_OVERLAY_SELECTED_COLOR = QColor(255, 140, 40)
    _TEXT_OVERLAY_SELECTED_BORDER = QColor(255, 220, 160)

    # Clip Colors
    _CLIP_SELECTED_BORDER = QColor(100, 220, 255)
    _CLIP_SELECTED_COLOR = QColor(0, 100, 140)
    _TRANSITION_MARKER_COLOR = QColor(255, 215, 0, 180)

    _SOURCE_COLORS = [
        (QColor(0, 160, 160), QColor(0, 120, 120), QColor(0, 200, 200)),
        (QColor(200, 120, 40), QColor(160, 90, 20), QColor(230, 150, 60)),
        (QColor(140, 70, 190), QColor(100, 40, 150), QColor(170, 100, 220)),
        (QColor(60, 160, 80), QColor(40, 120, 50), QColor(90, 190, 110)),
        (QColor(200, 60, 80), QColor(150, 40, 60), QColor(230, 90, 110)),
        (QColor(70, 110, 200), QColor(40, 80, 160), QColor(100, 140, 230)),
    ]

    def __init__(self, tw: TimelineWidget) -> None:
        self.tw = tw
        # 웨이브폼 이미지 캐시
        self._waveform_image_cache: QImage | None = None
        self._waveform_cache_key: tuple | None = None

    # ================================================================
    # 메인 페인트 엔트리
    # ================================================================

    def paint(self) -> None:
        """TimelineWidget.paintEvent에서 호출되는 메인 렌더링 루틴."""
        tw = self.tw
        w = tw.width()
        h = tw.height()

        if tw._duration_ms <= 0:
            painter = QPainter(tw)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(0, 0, w, h, self._BG_COLOR)
            painter.setPen(self._RULER_TEXT_COLOR)
            painter.drawText(tw.rect(), Qt.AlignmentFlag.AlignCenter, "No video loaded")
            painter.end()
            return

        visible_ms = tw._visible_range_ms()
        if visible_ms <= 0:
            visible_ms = tw._duration_ms
        tw._px_per_ms = w / visible_ms

        # 정적 레이어 캐시 키
        seg_count = len(tw._track) if tw._track else 0
        ovl_count = len(tw._image_overlay_track) if tw._image_overlay_track else 0
        clip_count = len(tw._clip_track) if tw._clip_track else 0
        v_h = tw._clip_track.hidden if tw._clip_track else False
        s_h = tw._track.hidden if tw._track else False
        o_h = tw._image_overlay_track.hidden if tw._image_overlay_track else False

        cache_key = (
            w, h, tw._visible_start_ms, visible_ms,
            tw._selected_index, tw._selected_overlay_index,
            tw._selected_clip_index, clip_count,
            seg_count, ovl_count, tw._has_video,
            id(tw._waveform_data),
            v_h, s_h, o_h,
        )

        if tw._static_cache_key != cache_key or tw._static_cache is None:
            pixmap = QPixmap(w, h)
            pp = QPainter(pixmap)
            pp.setRenderHint(QPainter.RenderHint.Antialiasing)
            pp.fillRect(0, 0, w, h, self._BG_COLOR)

            self._draw_ruler(pp, w, h, visible_ms)

            if tw._project:
                for idx, vt in enumerate(tw._project.video_tracks):
                    if not vt.hidden:
                        self._draw_track_clips(pp, idx, vt)
                if not tw._project.video_tracks[0].hidden:
                    self._draw_video_audio(pp, w, h)

            if tw._track and not tw._track.hidden:
                self._draw_audio_track(pp, h)
                self._draw_segments(pp, h)

            if tw._image_overlay_track and not tw._image_overlay_track.hidden:
                self._draw_image_overlays(pp, h)

            if tw._text_overlay_track:
                self._draw_text_overlays(pp, h)

            if hasattr(tw, "_bgm_tracks") and tw._bgm_tracks:
                self._draw_bgm_tracks(pp, h)

            pp.end()
            tw._static_cache = pixmap
            tw._static_cache_key = cache_key

        # 캐시된 정적 레이어 블릿 + 동적 요소
        painter = QPainter(tw)
        painter.drawPixmap(0, 0, tw._static_cache)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_playhead(painter, h)
        self._draw_track_highlight(painter, w)
        self._draw_snap_indicator(painter, h)
        self._draw_drop_indicator(painter, h)
        painter.end()

    # ================================================================
    # 개별 드로잉 메서드
    # ================================================================

    def _draw_ruler(self, painter: QPainter, w: int, h: int, visible_ms: float) -> None:
        """상단 눈금자."""
        tw = self.tw
        painter.fillRect(0, 0, w, _RULER_H, self._RULER_BG_COLOR)
        painter.setFont(QFont("Arial", 8))
        tick_ms = self._nice_tick_interval(visible_ms)
        if tick_ms <= 0:
            return
        # 로컬 변수 캐싱 — while 루프 내 속성 접근 최소화
        vis_start = tw._visible_start_ms
        ms_to_x = tw._ms_to_x
        ruler_color = self._RULER_COLOR
        ruler_text = self._RULER_TEXT_COLOR
        ruler_h = _RULER_H
        start_tick = int(vis_start / tick_ms) * tick_ms
        if start_tick < vis_start:
            start_tick += tick_ms
        t = start_tick
        end_ms = vis_start + visible_ms
        while t <= end_ms:
            x = ms_to_x(t)
            painter.setPen(QPen(ruler_color, 1))
            painter.drawLine(int(x), 0, int(x), ruler_h)
            painter.setPen(ruler_text)
            painter.drawText(int(x) + 4, 11, ms_to_display(int(t)))
            t += tick_ms

    def _draw_snap_indicator(self, painter: QPainter, h: int) -> None:
        """자석 스냅 가이드라인."""
        if self.tw._snap_guide_x is None:
            return
        x = float(self.tw._snap_guide_x)
        painter.setPen(QPen(self._SNAP_GUIDE_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(x), 0, int(x), h)

    def _draw_drop_indicator(self, painter: QPainter, h: int) -> None:
        """드롭 위치 표시."""
        if self.tw._drop_indicator_x < 0:
            return
        pen = QPen(QColor(0, 188, 212), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        x = int(self.tw._drop_indicator_x)
        painter.drawLine(x, 0, x, h)

    def _draw_track_highlight(self, painter: QPainter, w: int) -> None:
        """드래그 앤 드롭 시 타겟 트랙 하이라이트."""
        idx = self.tw._drop_target_track_index
        if idx >= 0:
            y = self.tw._video_track_y(idx)
            h = _CLIP_H
            # Light blue overlay
            painter.fillRect(0, y, w, h, QColor(100, 220, 255, 30))
            painter.setPen(QPen(QColor(100, 220, 255), 2))
            painter.drawRect(0, y, w, h)

    # ---- Video Audio / Waveform ----

    def _draw_video_audio(self, painter: QPainter, w: int, h: int) -> None:
        """비디오 오디오 웨이브폼 또는 로딩 중 대체 바."""
        tw = self.tw
        if tw._duration_ms <= 0 or not tw._has_video:
            return
        if tw._clip_track and len(tw._clip_track.clips) >= 1:
            return
        if tw._waveform_data is not None and tw._waveform_data.duration_ms > 0:
            self._draw_waveform(painter, w)
        else:
            self._draw_video_audio_fallback(painter, w)

    def _draw_waveform(self, painter: QPainter, w: int) -> None:
        """캐시된 QImage로 웨이브폼 그리기."""
        tw = self.tw
        wf = tw._waveform_data
        if wf is None or wf.duration_ms <= 0:
            return
        waveform_y = tw._waveform_y()
        waveform_h = _WAVEFORM_H
        visible_ms = tw._visible_range_ms()
        cache_key = (tw._visible_start_ms, visible_ms, w)

        if self._waveform_cache_key != cache_key:
            self._waveform_image_cache = self._render_waveform_image(w, waveform_h)
            self._waveform_cache_key = cache_key

        if self._waveform_image_cache is not None:
            painter.drawImage(0, waveform_y, self._waveform_image_cache)

        label_x = max(5, int(tw._ms_to_x(0)) + 5)
        if 0 < label_x < w - 80:
            painter.setPen(QColor(255, 200, 100, 200))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(label_x, waveform_y + 10, "Video Audio")

    def _render_waveform_image(self, w: int, h: int) -> QImage:
        """웨이브폼을 QImage로 렌더링. NumPy 벡터화로 O(w) Python 루프 제거."""
        tw = self.tw
        wf = tw._waveform_data
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0, 0))
        if wf is None or wf.duration_ms <= 0:
            return img

        center_y = h // 2
        half_h = h / 2.0

        # --- NumPy 벡터화: 모든 픽셀의 ms 범위를 한 번에 계산 ---
        vis_start = tw._visible_start_ms
        px_per_ms = tw._px_per_ms
        if px_per_ms <= 0:
            return img

        # 각 픽셀 x좌표 → ms 변환 (인라인 _x_to_ms 벡터화)
        px_arr = np.arange(w, dtype=np.float64)
        ms_starts = vis_start + px_arr / px_per_ms
        ms_ends = vis_start + (px_arr + 1.0) / px_per_ms

        # 정수 인덱스로 클램핑
        peaks_len = len(wf.peaks_pos)
        dur_ms = int(wf.duration_ms)
        ms_start_i = np.clip(ms_starts.astype(np.int64), 0, dur_ms)
        ms_end_i = np.clip(ms_ends.astype(np.int64), 0, min(dur_ms, peaks_len))

        # 유효 픽셀 마스크
        valid = (ms_start_i < ms_end_i) & (ms_start_i < dur_ms) & (ms_end_i <= peaks_len)

        # 유효 픽셀에 대해서만 peak_max, peak_min 계산
        # (각 픽셀 구간의 ms 범위가 다르므로 완전 벡터화가 어렵지만,
        #  대부분 구간이 1~2ms이므로 인덱싱으로 대체 가능)
        peak_max_arr = np.zeros(w, dtype=np.float64)
        peak_min_arr = np.zeros(w, dtype=np.float64)

        valid_idx = np.where(valid)[0]
        if len(valid_idx) > 0:
            s_i = ms_start_i[valid_idx]
            e_i = ms_end_i[valid_idx]
            # 구간 길이가 1인 경우 (대부분): 직접 인덱싱으로 빠르게
            single = (e_i - s_i) == 1
            single_idx = valid_idx[single]
            multi_idx = valid_idx[~single]

            if len(single_idx) > 0:
                peak_max_arr[single_idx] = wf.peaks_pos[s_i[single]]
                peak_min_arr[single_idx] = wf.peaks_neg[s_i[single]]

            # 구간 길이 > 1인 경우: 개별 슬라이싱 (소수)
            for vi in multi_idx:
                si, ei = ms_start_i[vi], ms_end_i[vi]
                peak_max_arr[vi] = np.max(wf.peaks_pos[si:ei])
                peak_min_arr[vi] = np.min(wf.peaks_neg[si:ei])

        # y 좌표 계산 (벡터)
        y_top = (center_y - (peak_max_arr * half_h)).astype(np.int32)
        y_bot = (center_y - (peak_min_arr * half_h)).astype(np.int32)
        # y_bot <= y_top인 경우 최소 1px 보장
        y_bot = np.maximum(y_bot, y_top + 1)

        # --- QPainter로 유효 픽셀만 그리기 ---
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        fill_color = self._WAVEFORM_FILL
        edge_color = self._WAVEFORM_EDGE

        p.setPen(Qt.PenStyle.NoPen)
        for vi in valid_idx:
            px = int(vi)
            yt = int(y_top[vi])
            yb = int(y_bot[vi])
            height = yb - yt
            p.setBrush(QBrush(fill_color))
            p.drawRect(px, yt, 1, height)
            p.setBrush(QBrush(edge_color))
            p.drawRect(px, yt, 1, 1)
            if height > 2:
                p.drawRect(px, yb - 1, 1, 1)

        p.setPen(QPen(self._WAVEFORM_CENTER, 1))
        p.drawLine(0, center_y, w, center_y)
        p.end()
        return img

    def _draw_video_audio_fallback(self, painter: QPainter, w: int) -> None:
        """웨이브폼 데이터 없을 때 대체 UI."""
        tw = self.tw
        waveform_y = tw._waveform_y()
        waveform_h = _WAVEFORM_H
        painter.fillRect(0, waveform_y, w, waveform_h, QColor(40, 40, 40, 100))
        center_y = waveform_y + waveform_h // 2
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(0, center_y, w, center_y)
        label_x = max(5, int(tw._ms_to_x(0)) + 5)
        if 0 < label_x < w - 120:
            painter.setPen(QColor(150, 150, 150, 150))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(label_x, waveform_y + 10, "Video Audio (loading...)")

    # ---- Audio / Subtitle ----

    def _draw_audio_track(self, painter: QPainter, h: int) -> None:
        """세그먼트별 TTS 오디오 구간."""
        tw = self.tw
        if not tw._track:
            return
        y = tw._audio_track_y()
        track_h = _AUDIO_H
        for i, seg in enumerate(tw._track):
            if not seg.audio_file:
                continue
            x1 = tw._ms_to_x(seg.start_ms)
            x2 = tw._ms_to_x(seg.end_ms)
            if x2 < 0 or x1 > tw.width():
                continue
            rect = QRectF(x1, y, x2 - x1, track_h)
            painter.setBrush(QBrush(self._AUDIO_COLOR_TOP))
            painter.setPen(QPen(self._AUDIO_BORDER, 1))
            painter.drawRoundedRect(rect, 4, 4)

    def _draw_segments(self, painter: QPainter, h: int) -> None:
        """자막 세그먼트 (파란 그라데이션)."""
        tw = self.tw
        if not tw._track:
            return
        y = tw._subtitle_track_y()
        track_h = _SEG_H
        # 로컬 변수 캐싱 — self.tw._xxx 딕셔너리 룩업 체인 제거
        ms_to_x = tw._ms_to_x
        widget_w = tw.width()
        selected_idx = tw._selected_index
        seg_top = self._SEGMENT_COLOR_TOP
        seg_bot = self._SEGMENT_COLOR_BOT
        seg_border = self._SEGMENT_BORDER
        sel_border = self._SELECTED_BORDER
        sel_glow = self._SELECTED_GLOW
        for i, seg in enumerate(tw._track):
            x1 = ms_to_x(seg.start_ms)
            x2 = ms_to_x(seg.end_ms)
            if x2 < 0 or x1 > widget_w:
                continue
            rect = QRectF(x1, y, x2 - x1, track_h)
            is_selected = (selected_idx == i)
            top = seg_top
            bot = seg_bot
            border = seg_border
            if is_selected:
                border = sel_border
                painter.setBrush(QBrush(sel_glow))
                painter.drawRect(rect.adjusted(-2, -2, 2, 2))
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0, top)
            grad.setColorAt(1, bot)
            painter.setBrush(grad)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(Qt.GlobalColor.white)
            painter.setFont(QFont("Arial", 8))
            painter.drawText(
                rect.adjusted(5, 0, -5, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                seg.text,
            )

    # ---- Image Overlays ----

    # 이미지 오버레이 팔레트 (상수 — 매 호출마다 리스트 재생성 방지)
    _IMG_PALETTE: tuple[QColor, ...] | None = None
    _IMG_BORDER_PALETTE: tuple[QColor, ...] | None = None

    def _get_img_palettes(self) -> tuple[tuple, tuple]:
        """이미지 오버레이 팔레트 lazy 초기화 (최초 1회)."""
        if self._IMG_PALETTE is None:
            TimelinePainter._IMG_PALETTE = (
                self._IMG_OVERLAY_COLOR,
                QColor(120, 80, 180, 180),
                QColor(80, 160, 120, 180),
                QColor(180, 120, 80, 180),
            )
            TimelinePainter._IMG_BORDER_PALETTE = (
                self._IMG_OVERLAY_BORDER,
                QColor(160, 120, 220),
                QColor(120, 200, 160),
                QColor(220, 160, 120),
            )
        return self._IMG_PALETTE, self._IMG_BORDER_PALETTE

    def _draw_image_overlays(self, painter: QPainter, h: int) -> None:
        """이미지 오버레이 세그먼트."""
        tw = self.tw
        if not tw._image_overlay_track or len(tw._image_overlay_track) == 0:
            return
        img_base_y = tw._img_overlay_base_y()
        img_h = tw._IMG_ROW_H
        img_gap = tw._IMG_ROW_GAP
        rows = tw._compute_overlay_rows()
        palette, border_palette = self._get_img_palettes()
        # 로컬 변수 캐싱
        ms_to_x = tw._ms_to_x
        widget_w = tw.width()
        sel_ov_idx = tw._selected_overlay_index
        for i, ov in enumerate(tw._image_overlay_track):
            x1 = ms_to_x(ov.start_ms)
            x2 = ms_to_x(ov.end_ms)
            if x2 < 0 or x1 > widget_w:
                continue
            row = rows[i]
            y = img_base_y + row * (img_h + img_gap)
            rect = QRectF(x1, y, max(x2 - x1, 2), img_h)
            color_idx = row % len(palette)
            if i == sel_ov_idx:
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

    # ---- Text Overlays ----

    def _draw_text_overlays(self, painter: QPainter, h: int) -> None:
        """텍스트 오버레이 세그먼트."""
        tw = self.tw
        if not tw._text_overlay_track or len(tw._text_overlay_track) == 0:
            return
        text_base_y = tw._text_overlay_base_y()
        text_h = tw._TEXT_ROW_H
        text_gap = tw._TEXT_ROW_GAP
        rows = tw._compute_text_overlay_rows()
        for i, overlay in enumerate(tw._text_overlay_track.overlays):
            x1 = tw._ms_to_x(overlay.start_ms)
            x2 = tw._ms_to_x(overlay.end_ms)
            if x2 < 0 or x1 > tw.width():
                continue
            row = rows[i]
            y = text_base_y + row * (text_h + text_gap)
            rect = QRectF(x1, y, max(x2 - x1, 2), text_h)
            if i == tw._selected_text_overlay_index:
                painter.setPen(QPen(self._TEXT_OVERLAY_SELECTED_BORDER, 2))
                painter.setBrush(QBrush(self._TEXT_OVERLAY_SELECTED_COLOR))
            else:
                painter.setPen(QPen(self._TEXT_OVERLAY_BORDER, 1))
                painter.setBrush(QBrush(self._TEXT_OVERLAY_COLOR))
            painter.drawRoundedRect(rect, 3, 3)
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

    # ---- BGM Tracks ----

    def _draw_bgm_tracks(self, painter: QPainter, h: int) -> None:
        """BGM 트랙 전체."""
        tw = self.tw
        if not hasattr(tw, "_bgm_tracks") or not tw._bgm_tracks:
            return
        for idx, track in enumerate(tw._bgm_tracks):
            self._draw_bgm_track_clips(painter, idx, track)

    def _draw_bgm_track_clips(self, painter: QPainter, track_idx: int, trackObject) -> None:
        """BGM 트랙의 개별 클립."""
        from src.models.audio import AudioTrack
        tw = self.tw
        track: AudioTrack = trackObject
        y = tw._bgm_track_y(track_idx)
        th = _BGM_H
        for i, clip in enumerate(track.clips):
            x1 = tw._ms_to_x(clip.start_ms)
            x2 = tw._ms_to_x(clip.start_ms + clip.duration_ms)
            if x2 < 0 or x1 > tw.width():
                continue
            rect = QRectF(x1, y, max(x2 - x1, 2), th)
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gradient.setColorAt(0, self._BGM_COLOR_TOP)
            gradient.setColorAt(1, self._BGM_COLOR_BOT)
            is_selected = False
            if is_selected:
                painter.setPen(QPen(self._BGM_SELECTED_BORDER, 2))
                painter.setBrush(QBrush(self._BGM_SELECTED_COLOR))
            else:
                painter.setPen(QPen(self._BGM_BORDER, 1))
                painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(rect, 4, 4)
            if rect.width() > 40:
                painter.setPen(Qt.GlobalColor.white)
                painter.setFont(QFont("Arial", 8))
                label = clip.source_path.name if clip.source_path else "BGM"
                painter.drawText(
                    rect.adjusted(10, 2, -10, -2),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    label,
                )

    # ---- Playhead ----

    def _draw_playhead(self, painter: QPainter, h: int) -> None:
        """현재 재생 위치 세로선 + 상단 노브."""
        tw = self.tw
        x = tw._ms_to_x(tw._playhead_ms)
        painter.setPen(QPen(self._PLAYHEAD_LINE_COLOR, 1))
        painter.drawLine(int(x), 0, int(x), h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._PLAYHEAD_COLOR))
        painter.drawPolygon(QPolygon([
            QPoint(int(x), 0),
            QPoint(int(x) + 6, 5),
            QPoint(int(x) + 6, 14),
            QPoint(int(x) - 6, 14),
            QPoint(int(x) - 6, 5),
        ]))

    # ---- Video Track Clips ----

    def _draw_track_clips(self, painter: QPainter, track_idx: int, track: VideoClipTrack) -> None:
        """비디오 클립 트랙 그리기."""
        if not track.clips:
            return
        tw = self.tw
        w = tw.width()
        y = tw._video_track_y(track_idx)
        h = _CLIP_H

        source_paths = {c.source_path for c in track.clips}
        source_color_map = {}
        for i, path in enumerate(sorted(source_paths, key=lambda x: str(x) if x is not None else "")):
            source_color_map[path] = i

        clip_starts = track.clip_boundaries_ms()
        # 로컬 변수 캐싱
        ms_to_x = tw._ms_to_x
        sel_track_idx = tw._selected_clip_track_index
        sel_clip_idx = tw._selected_clip_index
        source_colors = self._SOURCE_COLORS

        for i, clip in enumerate(track.clips):
            start_ms = clip_starts[i]
            x1 = ms_to_x(start_ms)
            x2 = ms_to_x(start_ms + clip.duration_ms)
            if x2 < 0 or x1 > w:
                continue
            rect = QRectF(x1, y, max(x2 - x1, 2), h)
            is_selected = (sel_track_idx == track_idx and sel_clip_idx == i)
            if is_selected:
                painter.setPen(QPen(self._CLIP_SELECTED_BORDER, 2))
                glow_gradient = QLinearGradient(0, y, 0, y + h)
                glow_gradient.setColorAt(0, self._CLIP_SELECTED_COLOR)
                glow_gradient.setColorAt(1, self._CLIP_SELECTED_COLOR.darker(120))
                painter.setBrush(QBrush(glow_gradient))
            else:
                color_idx = source_color_map.get(clip.source_path, 0) % len(source_colors)
                c_top, c_bot, border_color = source_colors[color_idx]
                gradient = QLinearGradient(0, y, 0, y + h)
                gradient.setColorAt(0, c_top)
                gradient.setColorAt(1, c_bot)
                painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 6, 6)

            # 클립 레벨 웨이브폼
            if tw._waveform_service and clip.source_path:
                wf = tw._waveform_service.get_waveform(clip.source_path)
                if wf:
                    self._draw_clip_waveform(painter, rect, clip, wf, tw)
                else:
                    tw._waveform_service.request_waveform(clip.source_path)

            # 필름스트립 썸네일
            if tw._should_draw_thumbnails(rect.width()):
                vis_x1 = max(int(x1), 0)
                vis_x2 = min(int(x2), tw.width())
                if vis_x2 > vis_x1:
                    interval = tw._get_thumbnail_interval()
                    start_grid = (vis_x1 // interval) * interval
                    painter.save()
                    painter.setClipRect(rect)
                    for tx in range(start_grid, vis_x2, interval):
                        if tx + interval < x1:
                            continue
                        offset_ms = (tx - x1) / tw._px_per_ms
                        source_ms = int(clip.source_in_ms + offset_ms * clip.speed)
                        video_path = clip.source_path if clip.source_path else tw._primary_video_path
                        if video_path:
                            thumb = tw._thumbnail_service.request_thumbnail(video_path, source_ms, h)
                            if thumb:
                                target_rect = QRectF(tx, y, interval, h)
                                painter.drawImage(target_rect.toRect(), thumb)
                    painter.restore()

            # 트랜지션 마커 그리기
            self._draw_transition_marker(painter, clip, rect)
            # 클립 라벨
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
                painter.drawText(
                    rect.adjusted(10, 2, -10, -2),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    label,
                )

            # 볼륨 엔벨로프
            if hasattr(clip, "volume_points") and clip.volume_points:
                self._draw_volume_envelope(painter, rect, clip)
                self._draw_default_volume_line(painter, rect, clip)

    def _draw_transition_marker(self, painter: QPainter, clip: VideoClip, rect: QRectF) -> None:
        """트랜지션 마커 그리기."""
        if not (hasattr(clip, "transition_out") and clip.transition_out):
            return

        painter.save()
        try:
            tw = self.tw
            x2 = rect.right()
            y = rect.top()
            h = rect.height()

            dur_px = tw._px_per_ms * clip.transition_out.duration_ms
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
        finally:
            painter.restore()

    # ---- Clip Waveform ----

    def _draw_clip_waveform(
        self, painter: QPainter, rect: QRectF, clip: VideoClip, wf: WaveformData, tw: TimelineWidget
    ) -> None:
        """클립 내부 웨이브폼. NumPy 벡터화로 O(px) Python 루프 최소화."""
        rect_x = rect.x()
        rect_y = rect.y()
        rect_w = rect.width()
        rect_h = rect.height()
        center_y = rect_y + rect_h / 2.0
        half_h = rect_h / 2.0
        s_in = clip.source_in_ms
        s_out = clip.source_out_ms
        speed = clip.speed
        p_start = max(0, int(rect_x))
        p_end = min(tw.width(), int(rect_x + rect_w))
        if p_start >= p_end:
            return

        try:
            cidx = tw._clip_track.clips.index(clip)
            clip_start_ms = tw._clip_track.clip_timeline_start(cidx)
        except (ValueError, AttributeError):
            clip_start_ms = 0

        # --- NumPy 벡터화: 모든 픽셀의 source_ms를 한 번에 계산 ---
        vis_start = tw._visible_start_ms
        px_per_ms = tw._px_per_ms
        if px_per_ms <= 0:
            return

        px_arr = np.arange(p_start, p_end, dtype=np.float64)
        ms_on_timeline = vis_start + px_arr / px_per_ms
        local_ms = ms_on_timeline - clip_start_ms
        source_ms = (s_in + local_ms * speed).astype(np.int64)

        # 유효 인덱스 마스크
        peaks_len = len(wf.peaks_pos)
        valid = (source_ms >= s_in) & (source_ms < s_out) & (source_ms < wf.duration_ms) & (source_ms < peaks_len)
        valid_idx = np.where(valid)[0]
        if len(valid_idx) == 0:
            return

        # 벡터 peak 조회
        src_idx = source_ms[valid_idx]
        peak_max = wf.peaks_pos[src_idx]
        peak_min = wf.peaks_neg[src_idx]
        y_tops = (center_y - peak_max * half_h).astype(np.int32)
        y_bots = (center_y - peak_min * half_h).astype(np.int32)
        px_vals = (px_arr[valid_idx]).astype(np.int32)

        # QPainter 드로잉 (유효 픽셀만)
        painter.setPen(QPen(self._WAVEFORM_EDGE, 1))
        for i in range(len(valid_idx)):
            painter.drawLine(int(px_vals[i]), int(y_tops[i]), int(px_vals[i]), int(y_bots[i]))

    # ---- Volume Envelope ----

    def _draw_volume_envelope(self, painter: QPainter, rect: QRectF, clip: VideoClip) -> None:
        """볼륨 엔벨로프 포인트+라인."""
        tw = self.tw
        if not clip.volume_points:
            self._draw_default_volume_line(painter, rect, clip)
            return
        painter.save()
        painter.setClipRect(rect)
        rect_x = rect.x()
        rect_y = rect.y()
        rect_h = rect.height()

        def vol_to_y(vol: float) -> float:
            margin = 4
            norm = (2.0 - vol) / 2.0
            return rect_y + margin + norm * (rect_h - 2 * margin)

        sorted_points = sorted(clip.volume_points, key=lambda p: p.offset_ms)
        path = []
        if sorted_points[0].offset_ms > 0:
            first_vol = sorted_points[0].volume
            path.append(QPoint(int(rect_x), int(vol_to_y(first_vol))))
        for p in sorted_points:
            px = rect_x + p.offset_ms * tw._px_per_ms
            path.append(QPoint(int(px), int(vol_to_y(p.volume))))
        if sorted_points[-1].offset_ms < clip.duration_ms:
            last_vol = sorted_points[-1].volume
            path.append(QPoint(int(rect_x + rect.width()), int(vol_to_y(last_vol))))
        painter.setPen(QPen(self._VOLUME_LINE_COLOR, 1.5))
        for i in range(len(path) - 1):
            painter.drawLine(path[i], path[i + 1])
        painter.setPen(QPen(self._VOLUME_LINE_COLOR, 1))
        painter.setBrush(QBrush(self._VOLUME_POINT_COLOR))
        for p in path:
            painter.drawEllipse(p, self._VOLUME_POINT_RADIUS, self._VOLUME_POINT_RADIUS)
        painter.restore()

    def _draw_default_volume_line(self, painter: QPainter, rect: QRectF, clip: VideoClip) -> None:
        """기본 볼륨 수평선."""
        painter.save()
        painter.setClipRect(rect)
        rect_x = rect.x()
        rect_y = rect.y()
        rect_h = rect.height()
        vol = clip.volume if hasattr(clip, "volume") else 1.0
        norm = (2.0 - vol) / 2.0
        margin = 4
        y = rect_y + margin + norm * (rect_h - 2 * margin)
        painter.setPen(QPen(self._VOLUME_LINE_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(rect_x), int(y), int(rect_x + rect.width()), int(y))
        painter.restore()

    # ---- 유틸 ----

    # 틱 간격 후보 (상수 튜플 — 매 호출마다 리스트 재생성 방지)
    _TICK_CANDIDATES = (500, 1000, 2000, 5000, 10000, 15000, 30000,
                        60000, 120000, 300000, 600000)

    @staticmethod
    def _nice_tick_interval(visible_ms: float) -> int:
        """눈금자 틱 간격 계산. bisect로 O(log n)."""
        import bisect
        raw = visible_ms / 8
        cands = TimelinePainter._TICK_CANDIDATES
        idx = bisect.bisect_left(cands, raw)
        return cands[idx] if idx < len(cands) else cands[-1]
