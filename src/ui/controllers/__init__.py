"""UI Controllers — MainWindow 책임 분리.

각 Controller는 QObject를 상속하여 시그널/슬롯 사용 가능.
AppContext를 통해 공유 상태에 접근한다.
"""

from src.ui.controllers.app_context import AppContext

__all__ = ["AppContext"]
