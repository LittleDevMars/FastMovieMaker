
import pytest
from src.models.text_overlay import TextOverlay, TextOverlayTrack
from src.models.style import SubtitleStyle

def test_text_overlay_initialization():
    """Test standard initialization and property defaults."""
    ov = TextOverlay(start_ms=1000, end_ms=2000, text="Hello World")
    assert ov.start_ms == 1000
    assert ov.end_ms == 2000
    assert ov.text == "Hello World"
    assert ov.x_percent == 50.0
    assert ov.y_percent == 50.0
    assert ov.alignment == "center"
    assert ov.v_alignment == "middle"
    assert ov.opacity == 1.0
    assert ov.duration_ms == 1000

def test_text_overlay_custom_position():
    """Test custom position and alignment."""
    ov = TextOverlay(
        start_ms=0, end_ms=1000, text="Top Left",
        x_percent=0.0, y_percent=0.0,
        alignment="left", v_alignment="top"
    )
    assert ov.x_percent == 0.0
    assert ov.y_percent == 0.0
    assert ov.alignment == "left"
    assert ov.v_alignment == "top"

def test_text_overlay_serialization():
    """Test to_dict and from_dict including new alignment fields."""
    style = SubtitleStyle(font_family="Arial", font_size=40, font_color="#FF0000")
    ov = TextOverlay(
        start_ms=500, end_ms=1500, text="Styled Text",
        x_percent=25.0, y_percent=75.0,
        alignment="right", v_alignment="bottom",
        opacity=0.8, style=style
    )
    
    data = ov.to_dict()
    assert data["start_ms"] == 500
    assert data["end_ms"] == 1500
    assert data["text"] == "Styled Text"
    assert data["x_percent"] == 25.0
    assert data["y_percent"] == 75.0
    assert data["alignment"] == "right"
    assert data["v_alignment"] == "bottom"
    assert data["opacity"] == 0.8
    assert data["style"]["font_family"] == "Arial"
    
    # Deserialization
    ov2 = TextOverlay.from_dict(data)
    assert ov2.start_ms == 500
    assert ov2.alignment == "right"
    assert ov2.v_alignment == "bottom"
    assert ov2.style.font_family == "Arial"

def test_text_overlay_track_operations():
    """Test adding, removal, and filtering in TextOverlayTrack."""
    track = TextOverlayTrack()
    ov1 = TextOverlay(start_ms=1000, end_ms=2000, text="One")
    ov2 = TextOverlay(start_ms=500, end_ms=1500, text="Two") # Earlier start
    
    track.add_overlay(ov1)
    track.add_overlay(ov2)
    
    # Check sorting
    assert track.overlays[0].text == "Two"
    assert track.overlays[1].text == "One"
    
    # Check overlays_at
    active = track.overlays_at(1200)
    assert len(active) == 2
    
    active = track.overlays_at(600)
    assert len(active) == 1
    assert active[0].text == "Two"
    
    # Check removal
    track.remove_overlay(0)
    assert len(track.overlays) == 1
    assert track.overlays[0].text == "One"

def test_text_overlay_from_dict_defaults():
    """Test backward compatibility with dicts missing alignment fields."""
    legacy_data = {
        "start_ms": 0,
        "end_ms": 1000,
        "text": "Legacy",
        "x_percent": 10.0,
        "y_percent": 20.0
        # alignment and v_alignment are missing
    }
    ov = TextOverlay.from_dict(legacy_data)
    assert ov.x_percent == 10.0
    assert ov.alignment == "center" # Default
    assert ov.v_alignment == "middle" # Default
