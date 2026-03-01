"""단축키 설정 단위 테스트 (Qt 불필요 — QSettings 모킹)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.settings_manager import SettingsManager, _SHORTCUT_DEFAULTS


# QSettings를 in-memory dict로 모킹하는 헬퍼
class _FakeQSettings:
    def __init__(self):
        self._data: dict[str, str] = {}

    def value(self, key: str, default, type_=None):
        return self._data.get(key, default)

    def setValue(self, key: str, value) -> None:
        self._data[key] = value

    def clear(self) -> None:
        self._data.clear()

    def sync(self) -> None:
        pass


def _make_manager() -> tuple[SettingsManager, _FakeQSettings]:
    """SettingsManager + FakeQSettings 쌍 반환."""
    fake = _FakeQSettings()
    mgr = SettingsManager.__new__(SettingsManager)
    mgr._settings = fake
    return mgr, fake


class TestShortcutDefaults:
    def test_default_value(self) -> None:
        """저장 전 get_shortcut → 기본값 반환."""
        mgr, _ = _make_manager()
        assert mgr.get_shortcut("play_pause") == "Space"
        assert mgr.get_shortcut("zoom_in") == "Ctrl+="

    def test_unknown_action_default(self) -> None:
        """미등록 action → 빈 문자열."""
        mgr, _ = _make_manager()
        assert mgr.get_shortcut("nonexistent_action") == ""

    def test_all_defaults_valid(self) -> None:
        """모든 기본 단축키가 비어있지 않음."""
        for action, key in _SHORTCUT_DEFAULTS.items():
            assert key, f"action '{action}'의 기본 단축키가 비어있습니다"


class TestShortcutRoundtrip:
    def test_set_get_roundtrip(self) -> None:
        """set_shortcut 후 get_shortcut → 저장한 값 반환."""
        mgr, _ = _make_manager()
        mgr.set_shortcut("play_pause", "F5")
        assert mgr.get_shortcut("play_pause") == "F5"

    def test_set_overrides_default(self) -> None:
        """커스텀 값 저장 시 기본값 무시."""
        mgr, _ = _make_manager()
        mgr.set_shortcut("seek_back", "A")
        assert mgr.get_shortcut("seek_back") == "A"
        assert mgr.get_shortcut("seek_back") != _SHORTCUT_DEFAULTS["seek_back"]

    def test_multiple_actions_independent(self) -> None:
        """서로 다른 action 키가 독립적으로 저장됨."""
        mgr, _ = _make_manager()
        mgr.set_shortcut("zoom_in", "Ctrl+Up")
        mgr.set_shortcut("zoom_out", "Ctrl+Down")
        assert mgr.get_shortcut("zoom_in") == "Ctrl+Up"
        assert mgr.get_shortcut("zoom_out") == "Ctrl+Down"
