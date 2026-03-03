"""Tests for src.utils.resource_path."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch


def test_dev_mode_returns_path():
    """frozen=False 이면 Path 인스턴스를 반환한다."""
    with patch.object(sys, "frozen", False, create=True):
        from src.utils.resource_path import get_resource_path
        result = get_resource_path("resources/icon.png")
    assert isinstance(result, Path)


def test_dev_mode_relative_appended():
    """개발 환경에서 'resources/icon.png' 이 결과 경로에 포함된다."""
    with patch.object(sys, "frozen", False, create=True):
        from src.utils.resource_path import get_resource_path
        result = get_resource_path("resources/icon.png")
    assert result.parts[-1] == "icon.png"
    assert "resources" in result.parts


def test_dev_mode_base_is_project_root():
    """개발 환경에서 기본 경로가 프로젝트 루트(src의 3단계 위)인지 확인한다."""
    import src.utils.resource_path as _rp_module
    expected_base = Path(_rp_module.__file__).resolve().parent.parent.parent
    with patch.object(sys, "frozen", False, create=True):
        result = _rp_module.get_resource_path("resources")
    assert result == expected_base / "resources"


def test_frozen_mode_uses_meipass():
    """frozen 모드에서 sys._MEIPASS 기준 경로를 반환한다."""
    fake_meipass = "/tmp/fake_meipass"
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "_MEIPASS", fake_meipass, create=True):
        import importlib
        import src.utils.resource_path as _rp_module
        importlib.reload(_rp_module)
        result = _rp_module.get_resource_path("resources/icon.png")
    assert str(result).startswith(fake_meipass)
    # 모듈 상태 복원
    import importlib
    import src.utils.resource_path as _rp_module2
    importlib.reload(_rp_module2)


def test_frozen_mode_relative_appended():
    """frozen 모드에서도 relative 문자열이 경로에 포함된다."""
    fake_meipass = "/tmp/fake_meipass2"
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "_MEIPASS", fake_meipass, create=True):
        import importlib
        import src.utils.resource_path as _rp_module
        importlib.reload(_rp_module)
        result = _rp_module.get_resource_path("resources/icon.png")
    assert result == Path(fake_meipass) / "resources" / "icon.png"
    # 모듈 상태 복원
    import importlib
    import src.utils.resource_path as _rp_module2
    importlib.reload(_rp_module2)
