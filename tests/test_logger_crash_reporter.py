"""tests/test_logger_crash_reporter.py — logger + crash_reporter 단위 테스트."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# ─────────────────────── logger ───────────────────────

class TestGetLogger:
    def test_returns_logger_instance(self):
        from src.utils.logger import get_logger
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_prefixed(self):
        from src.utils.logger import get_logger
        logger = get_logger("mymod")
        assert "mymod" in logger.name

    def test_same_name_same_instance(self):
        from src.utils.logger import get_logger
        a = get_logger("dupe")
        b = get_logger("dupe")
        assert a is b

    def test_no_duplicate_handlers_on_repeated_configure(self):
        """_configure_root 를 두 번 호출해도 핸들러가 중복 추가되지 않는다."""
        from src.utils import logger as logger_mod
        # 루트 로거를 직접 참조
        root = logging.getLogger(logger_mod._ROOT_LOGGER_NAME)
        initial_count = len(root.handlers)

        logger_mod._configure_root()   # 두 번째 호출
        assert len(root.handlers) == initial_count  # 동일 유지

    def test_get_log_dir_returns_path(self):
        from src.utils.logger import get_log_dir
        d = get_log_dir()
        assert isinstance(d, Path)
        assert "logs" in str(d)


# ─────────────────────── crash_reporter ───────────────────────

class TestCrashReporter:
    def test_get_crash_log_dir_returns_path(self):
        from src.utils.crash_reporter import get_crash_log_dir
        d = get_crash_log_dir()
        assert isinstance(d, Path)
        assert "crashes" in str(d)

    def test_write_crash_file_creates_file(self, tmp_path):
        from src.utils import crash_reporter
        # 크래시 디렉터리를 tmp_path 로 리디렉션
        orig_dir = crash_reporter._CRASH_DIR
        crash_reporter._CRASH_DIR = tmp_path / "crashes"
        try:
            exc = ValueError("테스트 오류")
            try:
                raise exc
            except ValueError:
                exc_type, exc_val, exc_tb = sys.exc_info()
            path = crash_reporter._write_crash_file(exc_type, exc_val, exc_tb)
            assert path.exists()
            content = path.read_text(encoding="utf-8")
            assert "ValueError" in content
            assert "테스트 오류" in content
        finally:
            crash_reporter._CRASH_DIR = orig_dir

    def test_crash_file_contains_traceback(self, tmp_path):
        from src.utils import crash_reporter
        orig_dir = crash_reporter._CRASH_DIR
        crash_reporter._CRASH_DIR = tmp_path / "crashes"
        try:
            try:
                raise RuntimeError("트레이스백 확인")
            except RuntimeError:
                exc_type, exc_val, exc_tb = sys.exc_info()
            path = crash_reporter._write_crash_file(exc_type, exc_val, exc_tb)
            content = path.read_text(encoding="utf-8")
            assert "Traceback" in content
            assert "test_crash_file_contains_traceback" in content
        finally:
            crash_reporter._CRASH_DIR = orig_dir

    def test_excepthook_keyboard_interrupt_uses_default(self):
        """KeyboardInterrupt는 기본 excepthook으로 위임된다."""
        from src.utils.crash_reporter import _excepthook
        with patch.object(sys, "__excepthook__") as mock_default:
            _excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
            mock_default.assert_called_once()

    def test_setup_excepthook_replaces_sys_excepthook(self):
        from src.utils.crash_reporter import setup_excepthook, _excepthook
        original = sys.excepthook
        try:
            setup_excepthook()
            assert sys.excepthook is _excepthook
        finally:
            sys.excepthook = original


# ─────────────────────── i18n keys ───────────────────────

class TestCrashI18nKeys:
    def test_crash_i18n_keys(self):
        from src.utils.lang.ko import STRINGS
        required = [
            "Application Error",
            "An unexpected error occurred:",
            "Crash log saved to:",
            "Copy to Clipboard",
            "Open Log Folder",
        ]
        for key in required:
            assert key in STRINGS, f"Missing i18n key: {key!r}"
