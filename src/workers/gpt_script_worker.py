"""GPT 대본 생성 백그라운드 워커."""

from PySide6.QtCore import QObject, Signal

from src.services.gpt_script_service import GptScriptService


class GptScriptWorker(QObject):
    """QThread + moveToThread 패턴으로 GPT API 호출을 백그라운드 처리한다."""

    finished = Signal(str)  # 생성된 스크립트 텍스트
    error    = Signal(str)

    def __init__(
        self,
        topic: str,
        style: str,
        length: str,
        language: str,
        api_key: str,
    ) -> None:
        super().__init__()
        self._topic    = topic
        self._style    = style
        self._length   = length
        self._language = language
        self._api_key  = api_key
        self._cancelled = False

    def cancel(self) -> None:
        """작업 취소 플래그 설정 (진행 중인 HTTP 요청은 중단 불가)."""
        self._cancelled = True

    def run(self) -> None:
        """백그라운드 스레드에서 실행된다."""
        try:
            script = GptScriptService.generate_script(
                self._topic,
                self._style,
                self._length,
                self._language,
                self._api_key,
            )
            if not self._cancelled:
                self.finished.emit(script)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
