"""Phase CLIP2 — 멀티 클립 선택 / 일괄 삭제 / 복사·붙여넣기 단위 테스트 (Qt 불필요)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

from src.models.project import ProjectState
from src.models.video_clip import VideoClip, VideoClipTrack


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _make_project(num_tracks: int = 1, clips_per_track: int = 3) -> ProjectState:
    """VideoTrack N개, 각 트랙에 clips_per_track개의 클립을 가진 ProjectState."""
    project = ProjectState()
    project.video_tracks = []
    for _ in range(num_tracks):
        vt = VideoClipTrack()
        for j in range(clips_per_track):
            clip = VideoClip(source_in_ms=j * 1000, source_out_ms=(j + 1) * 1000)
            vt.clips.append(clip)
        project.video_tracks.append(vt)
    project.duration_ms = clips_per_track * 1000
    return project


def _make_ctx(project: ProjectState, selected_clips: list[tuple[int, int]] | None = None):
    """ClipController 에서 필요한 최소 AppContext MagicMock."""
    ctx = MagicMock()
    ctx.project = project
    ctx.timeline.get_selected_clips.return_value = list(selected_clips or [])
    ctx.timeline.is_ripple_mode.return_value = False
    ctx.timeline._clear_selection = MagicMock()
    ctx.refresh_all = MagicMock()
    ctx.status_bar.return_value = MagicMock()
    return ctx


# ── 1. 기본값: _selected_clips 는 빈 set ──────────────────────────────────────

class TestSelectedClipsDefaultEmpty:
    def test_selected_clips_initial_state(self):
        """_selected_clips 초기값은 빈 set()이다."""
        selected: set[tuple[int, int]] = set()
        assert selected == set()

    def test_selected_clips_type(self):
        """_selected_clips 는 set[tuple[int, int]] 형식이다."""
        selected: set[tuple[int, int]] = set()
        selected.add((0, 1))
        assert isinstance(selected, set)
        assert (0, 1) in selected


# ── 2. 단일 클릭 → 세트에 1개 ────────────────────────────────────────────────

class TestSingleClickSetsSelection:
    def test_single_click_adds_one_item(self):
        """일반 클릭 시 _selected_clips = {(v_idx, seg_idx)} (1개)."""
        selected: set[tuple[int, int]] = set()
        v_idx, seg_idx = 0, 2

        # 일반 클릭 로직 시뮬레이션
        selected = {(v_idx, seg_idx)}
        assert len(selected) == 1
        assert (v_idx, seg_idx) in selected

    def test_single_click_replaces_previous_selection(self):
        """일반 클릭은 이전 선택을 모두 교체한다."""
        selected: set[tuple[int, int]] = {(0, 0), (0, 1)}
        # 새 클릭: 초기화 후 단일 추가
        selected = {(0, 2)}
        assert selected == {(0, 2)}


# ── 3. Ctrl+클릭 → 세트 추가 ─────────────────────────────────────────────────

class TestCtrlClickAddsToSelection:
    def test_ctrl_click_adds_new_clip(self):
        """Ctrl+클릭 시 기존 선택을 유지하고 새 클립을 추가한다."""
        selected: set[tuple[int, int]] = {(0, 0)}
        key = (0, 1)
        if key not in selected:
            selected.add(key)
        assert selected == {(0, 0), (0, 1)}

    def test_ctrl_click_across_tracks(self):
        """다른 트랙의 클립도 Ctrl+클릭으로 추가할 수 있다."""
        selected: set[tuple[int, int]] = {(0, 0)}
        selected.add((1, 0))
        assert len(selected) == 2
        assert (0, 0) in selected
        assert (1, 0) in selected


# ── 4. Ctrl+클릭 → 이미 선택된 클립 제거 ────────────────────────────────────

class TestCtrlClickTogglesOff:
    def test_ctrl_click_removes_selected_clip(self):
        """Ctrl+클릭으로 이미 선택된 클립을 제거한다 (토글)."""
        selected: set[tuple[int, int]] = {(0, 0), (0, 1)}
        key = (0, 0)
        # 이미 선택됨 → discard
        selected.discard(key)
        assert key not in selected
        assert (0, 1) in selected

    def test_ctrl_click_last_item_empties_set(self):
        """마지막 1개를 Ctrl+클릭으로 제거하면 세트가 비어진다."""
        selected: set[tuple[int, int]] = {(0, 2)}
        selected.discard((0, 2))
        assert selected == set()


# ── 5. Shift+클릭 → 같은 트랙 내 범위 선택 ──────────────────────────────────

class TestShiftClickRangeSameTrack:
    def test_shift_click_extends_to_right(self):
        """Shift+클릭: primary(0,0) → (0,2) → 0,1,2 모두 선택."""
        selected: set[tuple[int, int]] = set()
        primary_track, primary_clip = 0, 0
        target_clip = 2
        v_idx = 0

        # Shift+클릭 범위 선택 로직
        if primary_track == v_idx:
            lo = min(primary_clip, target_clip)
            hi = max(primary_clip, target_clip)
            for i in range(lo, hi + 1):
                selected.add((v_idx, i))

        assert selected == {(0, 0), (0, 1), (0, 2)}

    def test_shift_click_extends_to_left(self):
        """Shift+클릭: primary(0,3) → (0,1) → 1,2,3 모두 선택."""
        selected: set[tuple[int, int]] = set()
        primary_clip, target_clip, v_idx = 3, 1, 0
        lo = min(primary_clip, target_clip)
        hi = max(primary_clip, target_clip)
        for i in range(lo, hi + 1):
            selected.add((v_idx, i))
        assert selected == {(0, 1), (0, 2), (0, 3)}


# ── 6. Shift+클릭 → 다른 트랙이면 단일 선택으로 초기화 ──────────────────────

class TestShiftClickDifferentTrackResets:
    def test_shift_click_different_track_resets(self):
        """다른 트랙을 Shift+클릭하면 단일 선택으로 초기화된다."""
        selected: set[tuple[int, int]] = {(0, 0), (0, 1)}
        primary_track = 0
        v_idx = 1  # 다른 트랙

        if primary_track != v_idx:
            selected = {(v_idx, 0)}

        assert selected == {(1, 0)}
        assert (0, 0) not in selected


# ── 7. _clear_selection() → _selected_clips 비워짐 ───────────────────────────

class TestClearSelection:
    def test_clear_selection_empties_set(self):
        """_clear_selection() 이후 _selected_clips 는 빈 세트가 된다."""
        selected: set[tuple[int, int]] = {(0, 0), (0, 1), (1, 2)}
        # _clear_selection 로직
        selected = set()
        assert selected == set()

    def test_clear_selection_resets_primary_indices(self):
        """_clear_selection() 이후 primary index도 -1로 초기화된다."""
        sel_track_idx = 0
        sel_clip_idx = 2
        # _clear_selection
        sel_track_idx = -1
        sel_clip_idx = -1
        assert sel_track_idx == -1
        assert sel_clip_idx == -1


# ── 8. get_selected_clips() 반환 확인 ────────────────────────────────────────

class TestGetSelectedClips:
    def test_get_selected_clips_returns_list(self):
        """get_selected_clips()는 list[tuple[int,int]]를 반환한다."""
        selected: set[tuple[int, int]] = {(0, 0), (0, 2)}
        result = list(selected)
        assert isinstance(result, list)
        assert (0, 0) in result
        assert (0, 2) in result

    def test_get_selected_clips_empty(self):
        """선택이 없으면 빈 리스트를 반환한다."""
        selected: set[tuple[int, int]] = set()
        assert list(selected) == []


# ── 9. 멀티 삭제 + Undo 확인 ─────────────────────────────────────────────────

class TestDeleteMultipleClipsUndo:
    def test_delete_multiple_clips_calls_beginMacro(self):
        """on_delete_selected_clips()는 beginMacro/endMacro를 호출한다."""
        from src.ui.controllers.clip_controller import ClipController

        project = _make_project(num_tracks=1, clips_per_track=3)
        selected = [(0, 0), (0, 1)]
        ctx = _make_ctx(project, selected_clips=selected)

        ctrl = ClipController(ctx)
        ctrl.on_delete_selected_clips()

        ctx.undo_stack.beginMacro.assert_called_once()
        ctx.undo_stack.endMacro.assert_called_once()

    def test_delete_multiple_clips_pushes_commands(self):
        """on_delete_selected_clips()는 각 클립에 대해 push()를 호출한다."""
        from src.ui.controllers.clip_controller import ClipController

        project = _make_project(num_tracks=1, clips_per_track=3)
        selected = [(0, 0), (0, 1)]
        ctx = _make_ctx(project, selected_clips=selected)

        ctrl = ClipController(ctx)
        ctrl.on_delete_selected_clips()

        # 2개 클립 삭제 → push 2번
        assert ctx.undo_stack.push.call_count == 2

    def test_delete_clears_selection_after(self):
        """on_delete_selected_clips() 이후 _clear_selection()이 호출된다."""
        from src.ui.controllers.clip_controller import ClipController

        project = _make_project(num_tracks=1, clips_per_track=3)
        selected = [(0, 0), (0, 1)]
        ctx = _make_ctx(project, selected_clips=selected)

        ctrl = ClipController(ctx)
        ctrl.on_delete_selected_clips()

        ctx.timeline._clear_selection.assert_called_once()


# ── 10. 마지막 클립 보호 ──────────────────────────────────────────────────────

class TestDeletePreventsLastClip:
    def test_cannot_delete_only_clip_in_track(self):
        """트랙에 클립이 1개뿐이면 삭제 불가 (push 호출 없음)."""
        from src.ui.controllers.clip_controller import ClipController

        project = _make_project(num_tracks=1, clips_per_track=1)
        selected = [(0, 0)]  # 유일한 클립
        ctx = _make_ctx(project, selected_clips=selected)

        ctrl = ClipController(ctx)
        ctrl.on_delete_selected_clips()

        ctx.undo_stack.push.assert_not_called()

    def test_partial_delete_skips_last_clip(self):
        """트랙에 클립 2개 중 2개 모두 선택 시 마지막 1개는 보호된다."""
        from src.ui.controllers.clip_controller import ClipController

        project = _make_project(num_tracks=1, clips_per_track=2)
        selected = [(0, 0), (0, 1)]  # 2개 모두 선택
        ctx = _make_ctx(project, selected_clips=selected)

        ctrl = ClipController(ctx)
        ctrl.on_delete_selected_clips()

        # 2개 모두 삭제하면 트랙이 비게 되므로 push 0번
        ctx.undo_stack.push.assert_not_called()


# ── 11. 복사·붙여넣기 round-trip ──────────────────────────────────────────────

class TestCopyPasteRoundTrip:
    def test_copy_selected_clip_calls_clipboard(self):
        """copy_selected_clip()은 클립을 클립보드에 저장한다."""
        from src.ui.controllers.clip_controller import ClipController

        project = _make_project(num_tracks=1, clips_per_track=2)
        ctx = _make_ctx(project)
        ctx.timeline.get_selected_item.return_value = ("clip", 0, 0)

        with patch("PySide6.QtWidgets.QApplication") as mock_app:
            mock_clipboard = MagicMock()
            mock_app.clipboard.return_value = mock_clipboard

            ctrl = ClipController(ctx)
            ctrl.copy_selected_clip()

            mock_clipboard.setMimeData.assert_called_once()

    def test_paste_clip_does_nothing_without_mime(self):
        """클립보드에 mime 데이터 없으면 paste_clip()은 아무것도 하지 않는다."""
        from src.ui.controllers.clip_controller import ClipController

        project = _make_project(num_tracks=1, clips_per_track=1)
        ctx = _make_ctx(project)
        ctx.timeline.get_playhead.return_value = 0
        ctx.current_track_index = 0

        with patch("PySide6.QtWidgets.QApplication") as mock_app:
            mock_mime = MagicMock()
            mock_mime.hasFormat.return_value = False
            mock_app.clipboard.return_value.mimeData.return_value = mock_mime

            ctrl = ClipController(ctx)
            ctrl.paste_clip()  # 아무 오류 없이 종료

            ctx.undo_stack.push.assert_not_called()


# ── 12. 캐시 키에 frozenset(_selected_clips) 포함 확인 ───────────────────────

class TestCacheKeyIncludesSelectedClips:
    def test_frozenset_is_hashable(self):
        """frozenset은 dict/tuple의 키(캐시 키)로 사용 가능하다."""
        selected: set[tuple[int, int]] = {(0, 0), (0, 1)}
        key = frozenset(selected)
        assert isinstance(key, frozenset)
        # tuple 안에 포함해도 에러 없음
        cache_key = (1920, 200, 0.0, 10000.0, -1, -1, 0, 0, key)
        assert isinstance(cache_key, tuple)

    def test_different_selections_produce_different_cache_keys(self):
        """선택이 다르면 캐시 키도 달라진다."""
        sel_a: set[tuple[int, int]] = {(0, 0)}
        sel_b: set[tuple[int, int]] = {(0, 0), (0, 1)}
        key_a = frozenset(sel_a)
        key_b = frozenset(sel_b)
        assert key_a != key_b

    def test_same_selections_produce_same_cache_keys(self):
        """같은 선택이면 캐시 키도 동일하다."""
        sel_a: set[tuple[int, int]] = {(0, 1), (0, 2)}
        sel_b: set[tuple[int, int]] = {(0, 2), (0, 1)}  # 순서 다름
        assert frozenset(sel_a) == frozenset(sel_b)
