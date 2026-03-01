"""tests/test_wrap_subtitles.py — 자막 자동 줄바꿈 단위 테스트."""

import pytest

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.ui.commands import WrapSubtitlesCommand


def _make_track(*texts: str) -> SubtitleTrack:
    track = SubtitleTrack()
    for i, text in enumerate(texts):
        track.add_segment(SubtitleSegment(start_ms=i * 1000, end_ms=(i + 1) * 1000, text=text))
    return track


# ── SubtitleTrack.wrap_all_texts ──────────────────────────────────────────────


def test_wrap_short_text_no_change():
    """짧은 텍스트는 변경 목록이 비어있어야 한다."""
    track = _make_track("Hello", "World")
    changes = track.wrap_all_texts(max_chars=40)
    assert changes == []


def test_wrap_long_text():
    """max_chars보다 긴 텍스트는 new_text가 달라야 한다."""
    long_text = "This is a very long subtitle text that definitely exceeds forty characters in total"
    track = _make_track(long_text)
    changes = track.wrap_all_texts(max_chars=40)
    assert len(changes) == 1
    idx, old, new = changes[0]
    assert idx == 0
    assert old == long_text
    assert new != old


def test_wrap_changes_list():
    """변경 목록이 (index, old_text, new_text) 형태를 정확히 반환한다."""
    long_text = "A" * 50
    track = _make_track("short", long_text)
    changes = track.wrap_all_texts(max_chars=30)
    assert len(changes) == 1
    idx, old, new = changes[0]
    assert idx == 1
    assert old == long_text
    assert "\n" in new


def test_wrap_no_changes_empty_list():
    """이미 짧은 세그먼트들은 빈 리스트를 반환한다."""
    track = _make_track("Hi", "Bye", "OK")
    changes = track.wrap_all_texts(max_chars=100)
    assert changes == []


def test_wrap_multiple_segments():
    """다중 세그먼트 중 일부만 변경 목록에 포함된다."""
    track = _make_track(
        "Short",                                  # 짧음 → 제외
        "This text is longer than twenty chars",  # 긺 → 포함
        "OK",                                     # 짧음 → 제외
    )
    changes = track.wrap_all_texts(max_chars=20)
    assert len(changes) == 1
    assert changes[0][0] == 1  # 두 번째 세그먼트(인덱스 1)


# ── WrapSubtitlesCommand ──────────────────────────────────────────────────────


def test_command_redo():
    """WrapSubtitlesCommand.redo()는 새 텍스트를 적용한다."""
    track = _make_track("old text")
    changes = [(0, "old text", "new\ntext")]
    cmd = WrapSubtitlesCommand(track, changes)
    cmd.redo()
    assert track.segments[0].text == "new\ntext"


def test_command_undo():
    """WrapSubtitlesCommand.undo()는 원래 텍스트를 복원한다."""
    track = _make_track("old text")
    changes = [(0, "old text", "new\ntext")]
    cmd = WrapSubtitlesCommand(track, changes)
    cmd.redo()
    cmd.undo()
    assert track.segments[0].text == "old text"


def test_command_redo_after_undo():
    """undo → redo 순서가 정상 동작한다."""
    track = _make_track("original")
    changes = [(0, "original", "new\nvalue")]
    cmd = WrapSubtitlesCommand(track, changes)
    cmd.redo()
    cmd.undo()
    cmd.redo()
    assert track.segments[0].text == "new\nvalue"
