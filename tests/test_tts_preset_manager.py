"""Tests for TTSPresetManager."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from src.services.tts_preset_manager import TTSPreset, TTSPresetManager
from src.services.text_splitter import SplitStrategy
from src.utils.config import TTSEngine, TTS_DEFAULT_VOICE, TTS_DEFAULT_SPEED


@pytest.fixture
def preset_manager():
    """격리된 QSettings 범위로 동작하는 TTSPresetManager."""
    if not QCoreApplication.instance():
        QCoreApplication([])

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    # 테스트 전용 네임스페이스 사용
    settings = QSettings("FastMovieMakerTest", "TTSPresetTest")
    settings.beginGroup("TTSPresets")
    settings.remove("")   # 그룹 내 모든 키 삭제
    settings.endGroup()
    settings.sync()

    manager = TTSPresetManager()
    # 혹시 남은 항목 제거
    for name in manager.list_presets():
        manager.delete_preset(name)

    yield manager

    settings.beginGroup("TTSPresets")
    settings.remove("")
    settings.endGroup()
    settings.sync()


# ── 기본 CRUD ────────────────────────────────────────────────────────────────

def test_tts_preset_defaults():
    """TTSPreset 기본값 검증."""
    p = TTSPreset()
    assert p.engine == TTSEngine.EDGE_TTS
    assert p.language == "Korean"
    assert p.voice == TTS_DEFAULT_VOICE
    assert p.speed == TTS_DEFAULT_SPEED
    assert p.strategy == SplitStrategy.SENTENCE.value


def test_save_and_load_preset(preset_manager):
    """저장 후 로드하면 동일한 값을 반환해야 한다."""
    preset = TTSPreset(
        engine=TTSEngine.EDGE_TTS,
        language="English",
        voice="en-US-GuyNeural",
        speed=1.2,
        strategy=SplitStrategy.NEWLINE.value,
    )
    preset_manager.save_preset("Test", preset)

    loaded = preset_manager.load_preset("Test")
    assert loaded is not None
    assert loaded.engine == TTSEngine.EDGE_TTS
    assert loaded.language == "English"
    assert loaded.voice == "en-US-GuyNeural"
    assert loaded.speed == pytest.approx(1.2)
    assert loaded.strategy == SplitStrategy.NEWLINE.value


def test_load_nonexistent_returns_none(preset_manager):
    result = preset_manager.load_preset("Nonexistent")
    assert result is None


def test_overwrite_preset(preset_manager):
    """동일 이름으로 저장하면 덮어써야 한다."""
    preset_manager.save_preset("P", TTSPreset(speed=1.0))
    preset_manager.save_preset("P", TTSPreset(speed=1.5))

    loaded = preset_manager.load_preset("P")
    assert loaded.speed == pytest.approx(1.5)


def test_delete_preset(preset_manager):
    preset_manager.save_preset("Del", TTSPreset())
    assert preset_manager.preset_exists("Del")

    preset_manager.delete_preset("Del")

    assert not preset_manager.preset_exists("Del")
    assert preset_manager.load_preset("Del") is None


def test_delete_nonexistent_is_safe(preset_manager):
    """존재하지 않는 프리셋 삭제 시 에러 없이 통과해야 한다."""
    preset_manager.delete_preset("Ghost")  # should not raise


# ── 목록 조회 ────────────────────────────────────────────────────────────────

def test_list_presets_empty(preset_manager):
    assert preset_manager.list_presets() == []


def test_list_presets_sorted(preset_manager):
    preset_manager.save_preset("Bravo", TTSPreset())
    preset_manager.save_preset("Alpha", TTSPreset())
    preset_manager.save_preset("Charlie", TTSPreset())

    names = preset_manager.list_presets()
    assert names == ["Alpha", "Bravo", "Charlie"]


def test_preset_exists(preset_manager):
    preset_manager.save_preset("Existing", TTSPreset())

    assert preset_manager.preset_exists("Existing")
    assert not preset_manager.preset_exists("Missing")


def test_get_all_presets(preset_manager):
    preset_manager.save_preset("A", TTSPreset(language="Korean"))
    preset_manager.save_preset("B", TTSPreset(language="English"))

    all_presets = preset_manager.get_all_presets()

    assert len(all_presets) == 2
    assert "A" in all_presets
    assert "B" in all_presets
    assert all_presets["A"].language == "Korean"
    assert all_presets["B"].language == "English"


def test_get_all_presets_empty(preset_manager):
    assert preset_manager.get_all_presets() == {}


# ── 엣지 케이스 ──────────────────────────────────────────────────────────────

def test_save_elevenlabs_preset(preset_manager):
    """ElevenLabs 엔진 설정도 정상 저장/로드되어야 한다."""
    preset = TTSPreset(
        engine=TTSEngine.ELEVENLABS,
        language="Korean",
        voice="some_voice_id",
        speed=0.9,
        strategy=SplitStrategy.FIXED_LENGTH.value,
    )
    preset_manager.save_preset("EL", preset)

    loaded = preset_manager.load_preset("EL")
    assert loaded.engine == TTSEngine.ELEVENLABS
    assert loaded.voice == "some_voice_id"
    assert loaded.strategy == SplitStrategy.FIXED_LENGTH.value


def test_speed_boundary_values(preset_manager):
    """속도 경계값(0.5, 2.0)이 손실 없이 저장/로드되어야 한다."""
    preset_manager.save_preset("Slow", TTSPreset(speed=0.5))
    preset_manager.save_preset("Fast", TTSPreset(speed=2.0))

    assert preset_manager.load_preset("Slow").speed == pytest.approx(0.5)
    assert preset_manager.load_preset("Fast").speed == pytest.approx(2.0)
