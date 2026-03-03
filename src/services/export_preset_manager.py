"""Manager for saving and loading export presets via QSettings."""

from __future__ import annotations

from PySide6.QtCore import QSettings

from src.models.export_preset import ExportPreset


class ExportPresetManager:
    """QSettings 기반 내보내기 프리셋 관리자.

    기본 프리셋(DEFAULT_PRESETS)은 이 관리자에 저장되지 않으며,
    사용자가 직접 저장한 프리셋만 관리한다.
    """

    _GROUP = "ExportPresets"

    def __init__(self):
        self._settings = QSettings()
        self._settings.beginGroup(self._GROUP)

    def save_preset(self, name: str, preset: ExportPreset) -> None:
        """프리셋을 저장한다. 동일 이름이 있으면 덮어쓴다."""
        self._settings.beginGroup(name)
        self._settings.setValue("width", preset.width)
        self._settings.setValue("height", preset.height)
        self._settings.setValue("codec", preset.codec)
        self._settings.setValue("container", preset.container)
        self._settings.setValue("audio_bitrate", preset.audio_bitrate)
        self._settings.setValue("crf", preset.crf)
        self._settings.setValue("speed_preset", preset.speed_preset)
        self._settings.endGroup()

    def load_preset(self, name: str) -> ExportPreset | None:
        """이름으로 프리셋을 로드한다. 저장된 적 없으면 None 반환."""
        if not self._settings.contains(f"{name}/codec"):
            return None
        self._settings.beginGroup(name)
        preset = ExportPreset(
            name=name,
            width=int(self._settings.value("width", 0)),
            height=int(self._settings.value("height", 0)),
            codec=self._settings.value("codec", "h264"),
            container=self._settings.value("container", "mp4"),
            audio_bitrate=self._settings.value("audio_bitrate", "192k"),
            crf=int(self._settings.value("crf", 23)),
            speed_preset=self._settings.value("speed_preset", "medium"),
        )
        self._settings.endGroup()
        return preset

    def delete_preset(self, name: str) -> None:
        """프리셋을 삭제한다."""
        self._settings.remove(name)

    def list_presets(self) -> list[str]:
        """저장된 프리셋 이름 목록을 정렬하여 반환한다."""
        return sorted(self._settings.childGroups())

    def preset_exists(self, name: str) -> bool:
        """프리셋 존재 여부를 반환한다."""
        return self._settings.contains(f"{name}/codec")

    def get_all_presets(self) -> dict[str, ExportPreset]:
        """모든 프리셋을 {이름: ExportPreset} 딕셔너리로 반환한다."""
        result: dict[str, ExportPreset] = {}
        for name in self._settings.childGroups():
            self._settings.beginGroup(name)
            result[name] = ExportPreset(
                name=name,
                width=int(self._settings.value("width", 0)),
                height=int(self._settings.value("height", 0)),
                codec=self._settings.value("codec", "h264"),
                container=self._settings.value("container", "mp4"),
                audio_bitrate=self._settings.value("audio_bitrate", "192k"),
                crf=int(self._settings.value("crf", 23)),
                speed_preset=self._settings.value("speed_preset", "medium"),
            )
            self._settings.endGroup()
        return dict(sorted(result.items()))
