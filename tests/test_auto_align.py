"""자막 자동 정렬 단위 테스트 (Qt 불필요)."""

from __future__ import annotations

import pytest

from src.models.subtitle import SubtitleSegment, SubtitleTrack


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _track(*time_pairs: tuple[int, int]) -> SubtitleTrack:
    """(start, end) 쌍으로 SubtitleTrack 생성 (정렬 보장)."""
    track = SubtitleTrack()
    for s, e in time_pairs:
        track.add_segment(SubtitleSegment(start_ms=s, end_ms=e, text="x"))
    return track


def _auto_align(track: SubtitleTrack, gap_ms: int = 50) -> list[tuple[int, int]]:
    """알고리즘만 독립적으로 검증 (Controller 없이)."""
    old_times = [(seg.start_ms, seg.end_ms) for seg in track.segments]
    new_times = list(old_times)
    for i in range(1, len(new_times)):
        prev_end = new_times[i - 1][1]
        s, e = new_times[i]
        if s < prev_end + gap_ms:
            shift = prev_end + gap_ms - s
            new_times[i] = (s + shift, e + shift)
    return new_times


# ── find_overlapping_pairs ───────────────────────────────────────────────────

class TestFindOverlappingPairs:
    def test_no_overlap(self) -> None:
        track = _track((0, 1000), (1100, 2000), (2200, 3000))
        assert track.find_overlapping_pairs() == []

    def test_single_overlap(self) -> None:
        # 세그먼트 0 end(1000) > 세그먼트 1 start(500) → 겹침
        track = _track((0, 1000), (500, 1500))
        assert track.find_overlapping_pairs() == [(0, 1)]

    def test_adjacent_no_overlap(self) -> None:
        # end == next_start는 겹침이 아님
        track = _track((0, 1000), (1000, 2000))
        assert track.find_overlapping_pairs() == []

    def test_multiple_overlaps(self) -> None:
        track = _track((0, 1000), (500, 1500), (800, 1800))
        pairs = track.find_overlapping_pairs()
        assert (0, 1) in pairs
        assert (1, 2) in pairs


# ── 자동 정렬 알고리즘 ────────────────────────────────────────────────────────

class TestAutoAlignAlgorithm:
    def test_auto_align_basic(self) -> None:
        """겹치는 2개 세그먼트 → gap 50ms 보장."""
        track = _track((0, 1000), (500, 1500))
        new_times = _auto_align(track)
        # 세그먼트 1 new_start == 1000 + 50 = 1050
        assert new_times[1][0] == 1050
        assert new_times[1][1] == 2050
        # 세그먼트 0 불변
        assert new_times[0] == (0, 1000)

    def test_auto_align_chain(self) -> None:
        """3개 연속 겹침 → 모두 순서대로 정렬."""
        track = _track((0, 1000), (500, 1500), (800, 1800))
        new_times = _auto_align(track)
        # seg0 불변
        assert new_times[0] == (0, 1000)
        # seg1: 1000+50-500=550 shift → (1050, 2050)
        assert new_times[1] == (1050, 2050)
        # seg2: prev_end=2050, 800 < 2100 → shift=1300 → (2100, 3100)
        assert new_times[2] == (2100, 3100)

    def test_auto_align_no_change(self) -> None:
        """겹침 없으면 시간 그대로."""
        track = _track((0, 1000), (1100, 2000), (2200, 3000))
        old = [(s.start_ms, s.end_ms) for s in track.segments]
        new_times = _auto_align(track)
        assert new_times == old

    def test_gap_respected(self) -> None:
        """정렬 후 인접 세그먼트 간격이 gap 이상임을 보장."""
        track = _track((0, 1000), (900, 1800), (1700, 2700))
        new_times = _auto_align(track, gap_ms=50)
        for i in range(1, len(new_times)):
            assert new_times[i][0] >= new_times[i - 1][1] + 50


# ── AutoAlignSubtitlesCommand (Undo/Redo) ──────────────────────────────────

class TestAutoAlignCommand:
    """QUndoStack 없이 Command.redo()/undo() 직접 호출로 검증."""

    def _make_command(self, track):
        from src.ui.commands import AutoAlignSubtitlesCommand
        old_times = [(s.start_ms, s.end_ms) for s in track.segments]
        new_times = _auto_align(track)
        return AutoAlignSubtitlesCommand(track, old_times, new_times), old_times, new_times

    def test_command_redo(self) -> None:
        track = _track((0, 1000), (500, 1500))
        cmd, old_times, new_times = self._make_command(track)
        cmd.redo()
        assert track.segments[1].start_ms == new_times[1][0]
        assert track.segments[1].end_ms == new_times[1][1]

    def test_command_undo(self) -> None:
        track = _track((0, 1000), (500, 1500))
        cmd, old_times, new_times = self._make_command(track)
        cmd.redo()
        cmd.undo()
        # 원래 값으로 복원
        assert track.segments[1].start_ms == old_times[1][0]
        assert track.segments[1].end_ms == old_times[1][1]

    def test_command_redo_after_undo(self) -> None:
        """undo → redo → 정렬된 값 재적용."""
        track = _track((0, 1000), (500, 1500))
        cmd, old_times, new_times = self._make_command(track)
        cmd.redo()
        cmd.undo()
        cmd.redo()
        assert track.segments[1].start_ms == new_times[1][0]
