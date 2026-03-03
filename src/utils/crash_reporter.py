"""미처리 예외 포착 및 크래시 리포트 파일 생성.

sys.excepthook을 교체해 미처리 예외 발생 시 다음 작업을 수행한다:
1. ~/.fastmoviemaker/crashes/ 에 크래시 로그 파일 저장
2. Qt 앱이 실행 중이면 CrashReportDialog 표시
3. 기존 로거에 CRITICAL 기록
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.utils.logger import get_logger

if TYPE_CHECKING:
    from types import TracebackType

_logger = get_logger(__name__)

_CRASH_DIR: Path = Path.home() / ".fastmoviemaker" / "crashes"


def get_crash_log_dir() -> Path:
    """크래시 로그 디렉터리 경로를 반환한다."""
    return _CRASH_DIR


def _write_crash_file(
    exc_type: type,
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> Path:
    """크래시 정보를 파일로 저장하고 경로를 반환한다."""
    _CRASH_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    crash_path = _CRASH_DIR / f"crash_{timestamp}.txt"

    lines = [
        f"FastMovieMaker Crash Report",
        f"Time: {datetime.now().isoformat()}",
        f"Python: {sys.version}",
        f"Platform: {sys.platform}",
        "",
        f"Exception: {exc_type.__name__}: {exc_value}",
        "",
        "Traceback:",
        "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    ]

    crash_path.write_text("\n".join(lines), encoding="utf-8")
    return crash_path


def _excepthook(
    exc_type: type,
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    """미처리 예외 핸들러."""
    # KeyboardInterrupt는 기본 동작 유지
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    # 로거에 CRITICAL 기록
    _logger.critical(
        "Unhandled exception",
        exc_info=(exc_type, exc_value, exc_tb),
    )

    # 크래시 파일 저장
    crash_path: Path | None = None
    try:
        crash_path = _write_crash_file(exc_type, exc_value, exc_tb)
    except OSError:
        pass

    # Qt 앱이 실행 중이면 CrashReportDialog 표시
    try:
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() is not None:
            from src.ui.dialogs.crash_report_dialog import CrashReportDialog
            tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            dlg = CrashReportDialog(
                exc_type=exc_type.__name__,
                exc_message=str(exc_value),
                traceback_text=tb_text,
                crash_log_path=crash_path,
            )
            dlg.exec()
    except Exception:
        # 다이얼로그 표시 중 오류 → 기본 stderr 출력
        traceback.print_exception(exc_type, exc_value, exc_tb)


def setup_excepthook() -> None:
    """sys.excepthook을 크래시 리포터로 교체한다.

    main() 최초 진입점에서 한 번만 호출한다.
    """
    sys.excepthook = _excepthook
