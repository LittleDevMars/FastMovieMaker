"""Manager for saving and loading TTS settings presets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from PySide6.QtCore import QSettings

from src.utils.config import TTSEngine, TTS_DEFAULT_VOICE, TTS_DEFAULT_SPEED
from src.services.text_splitter import SplitStrategy


@dataclass
class TTSPreset:
    """TTS 설정 프리셋 데이터."""

    engine: str = TTSEngine.EDGE_TTS
    language: str = "Korean"
    voice: str = TTS_DEFAULT_VOICE
    speed: float = TTS_DEFAULT_SPEED
    strategy: str = SplitStrategy.SENTENCE.value


class TTSPresetManager:
    """QSettings 기반 TTS 프리셋 관리자."""

    _GROUP = "TTSPresets"

    def __init__(self):
        self._settings = QSettings()
        self._settings.beginGroup(self._GROUP)

    def __del__(self):
        try:
            self._settings.endGroup()
        except Exception:
            pass

    def save_preset(self, name: str, preset: TTSPreset) -> None:
        """프리셋을 저장한다. 동일 이름이 있으면 덮어쓴다."""
        self._settings.beginGroup(name)
        self._settings.setValue("engine", preset.engine)
        self._settings.setValue("language", preset.language)
        self._settings.setValue("voice", preset.voice)
        self._settings.setValue("speed", float(preset.speed))
        self._settings.setValue("strategy", preset.strategy)
        self._settings.endGroup()
        self._settings.sync()

    def load_preset(self, name: str) -> TTSPreset | None:
        """이름으로 프리셋을 로드한다. 없으면 None 반환."""
        if not self._settings.contains(f"{name}/engine"):
            return None
        self._settings.beginGroup(name)
        preset = TTSPreset(
            engine=self._settings.value("engine", TTSEngine.EDGE_TTS),
            language=self._settings.value("language", "Korean"),
            voice=self._settings.value("voice", TTS_DEFAULT_VOICE),
            speed=float(self._settings.value("speed", TTS_DEFAULT_SPEED)),
            strategy=self._settings.value("strategy", SplitStrategy.SENTENCE.value),
        )
        self._settings.endGroup()
        return preset

    def delete_preset(self, name: str) -> None:
        """프리셋을 삭제한다."""
        self._settings.remove(name)
        self._settings.sync()

    def list_presets(self) -> List[str]:
        """저장된 프리셋 이름 목록을 정렬하여 반환한다."""
        return sorted(self._settings.childGroups())

    def preset_exists(self, name: str) -> bool:
        """프리셋 존재 여부를 반환한다."""
        return self._settings.contains(f"{name}/engine")

    def get_all_presets(self) -> Dict[str, TTSPreset]:
        """모든 프리셋을 딕셔너리로 반환한다."""
        result: Dict[str, TTSPreset] = {}
        for name in self.list_presets():
            preset = self.load_preset(name)
            if preset:
                result[name] = preset
        return result
