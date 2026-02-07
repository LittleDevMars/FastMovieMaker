"""Tests for StylePresetManager."""

import os
import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from src.models.style import SubtitleStyle
from src.services.style_preset_manager import StylePresetManager


@pytest.fixture
def preset_manager():
    """Create a fresh preset manager with test settings."""
    # Initialize QCoreApplication if not already done
    if not QCoreApplication.instance():
        app = QCoreApplication([])

    # Use a unique organization/app name for testing
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    settings = QSettings("FastMovieMakerTest", "StylePresetTest")
    settings.clear()
    settings.sync()

    manager = StylePresetManager()
    # Clear any existing presets
    for preset in manager.list_presets():
        manager.delete_preset(preset)

    yield manager

    # Cleanup
    settings.clear()
    settings.sync()


def test_save_and_load_preset(preset_manager):
    """Test saving and loading a preset."""
    style = SubtitleStyle(
        font_family="Arial",
        font_size=24,
        font_bold=True,
        font_color="#FFFF00",
    )

    preset_manager.save_preset("Test Preset", style)

    loaded_style = preset_manager.load_preset("Test Preset")
    assert loaded_style is not None
    assert loaded_style.font_family == "Arial"
    assert loaded_style.font_size == 24
    assert loaded_style.font_bold is True
    assert loaded_style.font_color == "#FFFF00"


def test_load_nonexistent_preset(preset_manager):
    """Test loading a preset that doesn't exist."""
    result = preset_manager.load_preset("Nonexistent")
    assert result is None


def test_list_presets(preset_manager):
    """Test listing all presets."""
    style1 = SubtitleStyle(font_family="Arial")
    style2 = SubtitleStyle(font_family="Times")

    preset_manager.save_preset("Preset A", style1)
    preset_manager.save_preset("Preset B", style2)

    presets = preset_manager.list_presets()
    assert "Preset A" in presets
    assert "Preset B" in presets
    assert len(presets) == 2


def test_delete_preset(preset_manager):
    """Test deleting a preset."""
    style = SubtitleStyle()
    preset_manager.save_preset("To Delete", style)

    assert preset_manager.preset_exists("To Delete")

    preset_manager.delete_preset("To Delete")

    assert not preset_manager.preset_exists("To Delete")
    assert preset_manager.load_preset("To Delete") is None


def test_rename_preset(preset_manager):
    """Test renaming a preset."""
    style = SubtitleStyle(font_family="Arial", font_size=20)
    preset_manager.save_preset("Old Name", style)

    success = preset_manager.rename_preset("Old Name", "New Name")
    assert success

    assert not preset_manager.preset_exists("Old Name")
    assert preset_manager.preset_exists("New Name")

    loaded = preset_manager.load_preset("New Name")
    assert loaded is not None
    assert loaded.font_family == "Arial"
    assert loaded.font_size == 20


def test_rename_nonexistent_preset(preset_manager):
    """Test renaming a preset that doesn't exist."""
    success = preset_manager.rename_preset("Nonexistent", "New Name")
    assert not success


def test_rename_to_existing_name(preset_manager):
    """Test renaming to a name that already exists."""
    style1 = SubtitleStyle(font_family="Arial")
    style2 = SubtitleStyle(font_family="Times")

    preset_manager.save_preset("Preset 1", style1)
    preset_manager.save_preset("Preset 2", style2)

    success = preset_manager.rename_preset("Preset 1", "Preset 2")
    assert not success


def test_preset_exists(preset_manager):
    """Test checking if preset exists."""
    style = SubtitleStyle()
    preset_manager.save_preset("Existing", style)

    assert preset_manager.preset_exists("Existing")
    assert not preset_manager.preset_exists("Nonexistent")


def test_get_all_presets(preset_manager):
    """Test getting all presets as a dictionary."""
    style1 = SubtitleStyle(font_family="Arial", font_size=20)
    style2 = SubtitleStyle(font_family="Times", font_size=24)

    preset_manager.save_preset("Preset A", style1)
    preset_manager.save_preset("Preset B", style2)

    all_presets = preset_manager.get_all_presets()

    assert len(all_presets) == 2
    assert "Preset A" in all_presets
    assert "Preset B" in all_presets
    assert all_presets["Preset A"].font_family == "Arial"
    assert all_presets["Preset B"].font_family == "Times"


def test_create_default_presets(preset_manager):
    """Test creating default presets."""
    assert len(preset_manager.list_presets()) == 0

    preset_manager.create_default_presets()

    presets = preset_manager.list_presets()
    assert len(presets) > 0
    assert "YouTube" in presets
    assert "Cinema" in presets
    assert "Karaoke" in presets
    assert "Minimal" in presets


def test_create_default_presets_only_once(preset_manager):
    """Test that default presets are only created if none exist."""
    preset_manager.create_default_presets()
    count_after_first = len(preset_manager.list_presets())

    # Call again - should not create duplicates
    preset_manager.create_default_presets()
    count_after_second = len(preset_manager.list_presets())

    assert count_after_first == count_after_second


def test_overwrite_preset(preset_manager):
    """Test overwriting an existing preset."""
    style1 = SubtitleStyle(font_family="Arial", font_size=20)
    style2 = SubtitleStyle(font_family="Times", font_size=24)

    preset_manager.save_preset("Test", style1)

    loaded = preset_manager.load_preset("Test")
    assert loaded.font_family == "Arial"

    # Overwrite with new style
    preset_manager.save_preset("Test", style2)

    loaded = preset_manager.load_preset("Test")
    assert loaded.font_family == "Times"
    assert loaded.font_size == 24


def test_preset_persistence(preset_manager):
    """Test that presets persist across manager instances."""
    style = SubtitleStyle(font_family="Arial", font_size=20)
    preset_manager.save_preset("Persistent", style)

    # Create a new manager instance
    new_manager = StylePresetManager()

    loaded = new_manager.load_preset("Persistent")
    assert loaded is not None
    assert loaded.font_family == "Arial"
    assert loaded.font_size == 20
