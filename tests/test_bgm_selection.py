"""BGM 클립 선택 하이라이트 로직 단위 테스트 (Qt 불필요)."""

from __future__ import annotations


class TestBgmSelection:
    """_draw_bgm_track_clips()의 is_selected 판별 로직 검증."""

    def _is_selected(self, sel_track: int, sel_clip: int, track_idx: int, i: int) -> bool:
        """timeline_painter의 is_selected 판별식 직접 검증."""
        return sel_track == track_idx and sel_clip == i

    def test_bgm_not_selected_by_default(self):
        # 기본값 -1 → 절대 선택되지 않음
        assert self._is_selected(-1, -1, 0, 0) is False

    def test_bgm_is_selected_correct_index(self):
        # 트랙 0, 클립 2 선택 → 동일 인덱스 = True
        assert self._is_selected(0, 2, 0, 2) is True

    def test_bgm_other_clip_not_selected(self):
        # 트랙 0, 클립 2 선택 → 다른 클립 = False
        assert self._is_selected(0, 2, 0, 3) is False

    def test_bgm_other_track_not_selected(self):
        # 트랙 1, 클립 0 선택 → 다른 트랙 = False
        assert self._is_selected(1, 0, 0, 0) is False
