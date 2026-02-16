"""타임라인 (x,y) 히트 테스트. TimelineWidget에서 위임용."""

_EDGE_PX = 6
_PLAYHEAD_HIT_PX = 20
_CLIP_H = 32
_SEG_H = 40
_AUDIO_H = 34
_BGM_H = 34


class TimelineHitTester:
    """위젯 참조로 (x, y)에 대한 (seg_idx, hit_kind, track_idx) 반환."""

    def __init__(self, widget) -> None:
        self._w = widget

    def hit_test(self, x: float, y: float) -> tuple[int, str, int]:
        """(x,y)에 해당하는 (인덱스, 히트 영역, 트랙 인덱스) 반환. 없으면 (-1, '', -1)."""
        playhead_x = self._w._ms_to_x(self._w._playhead_ms)
        if abs(x - playhead_x) <= _PLAYHEAD_HIT_PX:
            return -3, "playhead", -1

        if self._w._project:
            for v_idx, vt in enumerate(self._w._project.video_tracks):
                track_y = self._w._video_track_y(v_idx)
                if track_y <= y < track_y + _CLIP_H:
                    offset = 0
                    for i, clip in enumerate(vt.clips):
                        x1 = self._w._ms_to_x(offset)
                        x2 = self._w._ms_to_x(offset + clip.duration_ms)
                        offset += clip.duration_ms
                        if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                            continue
                        if abs(x - x1) <= _EDGE_PX and i > 0:
                            return i, "clip_left_edge", v_idx
                        if abs(x - x2) <= _EDGE_PX and i < len(vt.clips) - 1:
                            return i, "clip_right_edge", v_idx
                        if x1 <= x <= x2:
                            if hasattr(clip, "volume_points") and clip.volume_points:
                                rect_y = track_y
                                rect_h = _CLIP_H
                                margin = 4

                                def vol_to_y(vol):
                                    norm = (2.0 - vol) / 2.0
                                    return rect_y + margin + norm * (rect_h - 2 * margin)

                                for p_idx, p in enumerate(clip.volume_points):
                                    px = x1 + p.offset_ms * self._w._px_per_ms
                                    py = vol_to_y(p.volume)
                                    r = getattr(self._w, "_VOLUME_POINT_RADIUS", 4) + 2
                                    if abs(x - px) <= r and abs(y - py) <= r:
                                        self._w._drag_mgr.clip_ref = clip
                                        return p_idx, "volume_point", v_idx
                            return i, "clip_body", v_idx

        seg_y = self._w._subtitle_track_y()
        if seg_y <= y < seg_y + _SEG_H:
            if self._w._track:
                for i, seg in enumerate(self._w._track):
                    x1 = self._w._ms_to_x(seg.start_ms)
                    x2 = self._w._ms_to_x(seg.end_ms)
                    if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                        continue
                    if abs(x - x1) <= _EDGE_PX:
                        return i, "left_edge", 0
                    if abs(x - x2) <= _EDGE_PX:
                        return i, "right_edge", 0
                    if x1 <= x <= x2:
                        return i, "body", 0

        audio_y = self._w._audio_track_y()
        if audio_y <= y < audio_y + _AUDIO_H:
            if self._w._track:
                for i, seg in enumerate(self._w._track):
                    if not seg.audio_file:
                        continue
                    x1 = self._w._ms_to_x(seg.start_ms)
                    x2 = self._w._ms_to_x(seg.end_ms)
                    if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                        continue
                    if abs(x - x1) <= _EDGE_PX:
                        return i, "left_edge", 0
                    if abs(x - x2) <= _EDGE_PX:
                        return i, "right_edge", 0
                    if x1 <= x <= x2:
                        return i, "body", 0

        if self._w._image_overlay_track:
            img_base_y = self._w._img_overlay_base_y()
            rows = self._w._compute_overlay_rows()
            total_h = self._w._img_overlay_total_h(rows)
            if img_base_y <= y <= img_base_y + total_h:
                img_row_h = getattr(self._w, "_IMG_ROW_H", 40)
                img_gap = getattr(self._w, "_IMG_ROW_GAP", 4)
                for i, ov in enumerate(self._w._image_overlay_track):
                    row = rows[i]
                    ov_y = img_base_y + row * (img_row_h + img_gap)
                    if not (ov_y <= y <= ov_y + img_row_h):
                        continue
                    x1 = self._w._ms_to_x(ov.start_ms)
                    x2 = self._w._ms_to_x(ov.end_ms)
                    if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                        continue
                    if abs(x - x1) <= _EDGE_PX:
                        return i, "img_left_edge", 0
                    if abs(x - x2) <= _EDGE_PX:
                        return i, "img_right_edge", 0
                    if x1 <= x <= x2:
                        return i, "img_body", 0

        if self._w._text_overlay_track:
            text_base_y = self._w._text_overlay_base_y()
            rows = self._w._compute_text_overlay_rows()
            text_row_h = getattr(self._w, "_TEXT_ROW_H", 28)
            text_gap = getattr(self._w, "_TEXT_ROW_GAP", 4)
            for i, overlay in enumerate(self._w._text_overlay_track.overlays):
                row = rows[i]
                ov_y = text_base_y + row * (text_row_h + text_gap)
                if not (ov_y <= y <= ov_y + text_row_h):
                    continue
                x1 = self._w._ms_to_x(overlay.start_ms)
                x2 = self._w._ms_to_x(overlay.end_ms)
                if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                    continue
                if abs(x - x1) <= _EDGE_PX:
                    return i, "text_left_edge", 0
                if abs(x - x2) <= _EDGE_PX:
                    return i, "text_right_edge", 0
                if x1 <= x <= x2:
                    return i, "text_body", 0

        if hasattr(self._w, "_bgm_tracks") and self._w._bgm_tracks:
            for track_idx, track in enumerate(self._w._bgm_tracks):
                ty = self._w._bgm_track_y(track_idx)
                if ty <= y < ty + _BGM_H:
                    for i, clip in enumerate(track.clips):
                        x1 = self._w._ms_to_x(clip.start_ms)
                        x2 = self._w._ms_to_x(clip.start_ms + clip.duration_ms)
                        if x < x1 - _EDGE_PX or x > x2 + _EDGE_PX:
                            continue
                        if abs(x - x1) <= _EDGE_PX:
                            return i, "bgm_left_edge", track_idx
                        if abs(x - x2) <= _EDGE_PX:
                            return i, "bgm_right_edge", track_idx
                        if x1 <= x <= x2:
                            return i, "bgm_body", track_idx

        return -1, "", -1
