"""Tests for ExportPreset model (to_dict/from_dict) and ExportPresetManager service.

Run:
    pytest tests/test_export2.py -v
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from src.models.export_preset import DEFAULT_PRESETS, ExportPreset


# ─────────────────── ExportPreset 모델 ───────────────────


def test_export_preset_defaults():
    """crf=23, speed_preset='medium', audio_bitrate='192k' 기본값 검증."""
    p = ExportPreset("My Preset", 1920, 1080, "h264", "mp4")
    assert p.crf == 23
    assert p.speed_preset == "medium"
    assert p.audio_bitrate == "192k"


def test_export_preset_to_dict_roundtrip():
    """to_dict/from_dict 라운드트립 — 모든 필드가 보존되어야 한다."""
    p = ExportPreset(
        "Test",
        width=1280,
        height=720,
        codec="hevc",
        container="mkv",
        audio_bitrate="128k",
        crf=18,
        speed_preset="slow",
        suffix="_test",
    )
    d = p.to_dict()
    p2 = ExportPreset.from_dict(d)

    assert p2.name == "Test"
    assert p2.width == 1280
    assert p2.height == 720
    assert p2.codec == "hevc"
    assert p2.container == "mkv"
    assert p2.audio_bitrate == "128k"
    assert p2.crf == 18
    assert p2.speed_preset == "slow"
    assert p2.suffix == "_test"


def test_export_preset_from_dict_defaults():
    """from_dict 에서 누락 필드는 기본값으로 채워져야 한다."""
    p = ExportPreset.from_dict({"name": "X", "codec": "h264", "container": "mp4"})
    assert p.width == 0
    assert p.height == 0
    assert p.crf == 23
    assert p.speed_preset == "medium"
    assert p.audio_bitrate == "192k"
    assert p.suffix == ""


def test_export_preset_resolution_label():
    """resolution_label 프로퍼티 검증."""
    p = ExportPreset("A", 1920, 1080, "h264", "mp4")
    assert p.resolution_label == "1920x1080"

    p_original = ExportPreset("B", 0, 0, "h264", "mp4")
    assert p_original.resolution_label == "Original"


def test_export_preset_file_extension():
    """file_extension 프로퍼티 검증."""
    assert ExportPreset("C", 0, 0, "h264", "mkv").file_extension == ".mkv"
    assert ExportPreset("D", 0, 0, "h264", "mp4").file_extension == ".mp4"
    assert ExportPreset("E", 0, 0, "h264", "webm").file_extension == ".webm"


def test_default_presets_count_and_fields():
    """DEFAULT_PRESETS — 7개 유지, 신규 필드 기본값(crf=23, speed_preset='medium') 검증."""
    assert len(DEFAULT_PRESETS) == 7
    for preset in DEFAULT_PRESETS:
        assert preset.crf == 23
        assert preset.speed_preset == "medium"
        assert preset.audio_bitrate == "192k"


# ─────────────────── ExportPresetManager ───────────────────


@pytest.fixture()
def manager():
    """격리된 QSettings 네임스페이스로 동작하는 ExportPresetManager."""
    if not QCoreApplication.instance():
        QCoreApplication([])

    # ExportPresetManager가 사용하는 QSettings()과 동일한 네임스페이스로 격리
    QCoreApplication.setOrganizationName("FastMovieMakerTest")
    QCoreApplication.setApplicationName("ExportPresetTest")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)

    # 이전 테스트 잔류 데이터 일괄 삭제 (단일 sync)
    settings = QSettings()
    settings.beginGroup("ExportPresets")
    settings.remove("")
    settings.endGroup()
    settings.sync()

    from src.services.export_preset_manager import ExportPresetManager
    mgr = ExportPresetManager()

    yield mgr

    settings.beginGroup("ExportPresets")
    settings.remove("")
    settings.endGroup()
    settings.sync()


def test_manager_save_and_load(manager):
    """save_preset/load_preset 기본 동작."""
    preset = ExportPreset("User1080p", 1920, 1080, "h264", "mp4", crf=20, speed_preset="fast")
    manager.save_preset("User1080p", preset)

    loaded = manager.load_preset("User1080p")
    assert loaded is not None
    assert loaded.width == 1920
    assert loaded.height == 1080
    assert loaded.codec == "h264"
    assert loaded.crf == 20
    assert loaded.speed_preset == "fast"


def test_manager_load_nonexistent_returns_none(manager):
    """존재하지 않는 프리셋 로드 시 None 반환."""
    assert manager.load_preset("NonExistent") is None


def test_manager_load_default_preset_name_returns_none(manager):
    """기본 프리셋 이름은 manager에 저장된 적 없으므로 None 반환."""
    assert manager.load_preset("1080p MP4 (H.264)") is None
    assert manager.load_preset("Original MP4 (H.264)") is None


def test_manager_delete(manager):
    """delete_preset 후 preset_exists가 False가 되어야 한다."""
    preset = ExportPreset("ToDelete", 720, 480, "h264", "mp4")
    manager.save_preset("ToDelete", preset)
    assert manager.preset_exists("ToDelete")

    manager.delete_preset("ToDelete")
    assert not manager.preset_exists("ToDelete")
    assert manager.load_preset("ToDelete") is None


def test_manager_list_presets_sorted(manager):
    """list_presets()가 알파벳 정렬된 목록을 반환한다."""
    for name in ["Zebra", "Apple", "Mango"]:
        manager.save_preset(name, ExportPreset(name, 0, 0, "h264", "mp4"))

    assert manager.list_presets() == ["Apple", "Mango", "Zebra"]


def test_manager_get_all_presets(manager):
    """get_all_presets()가 저장된 모든 프리셋 딕셔너리를 반환한다."""
    for name in ["P1", "P2"]:
        manager.save_preset(name, ExportPreset(name, 1920, 1080, "h264", "mp4"))

    all_p = manager.get_all_presets()
    assert len(all_p) == 2
    assert "P1" in all_p
    assert "P2" in all_p


def test_manager_preset_exists(manager):
    """preset_exists()가 저장 여부를 정확히 반환한다."""
    assert not manager.preset_exists("Ghost")
    manager.save_preset("Ghost", ExportPreset("Ghost", 0, 0, "h264", "mp4"))
    assert manager.preset_exists("Ghost")
