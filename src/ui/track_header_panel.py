"""Track Header Panel for Timeline control (Mute, Lock, Hide)."""

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent
from PySide6.QtWidgets import QWidget, QMenu
from src.utils.i18n import tr


class TrackHeaderPanel(QWidget):
    """Left-side panel for timeline tracks.
    
    Provides Mute, Lock, and Hide controls for each track.
    Y-positions must match TimelineWidget's track offsets.
    """
    
    # Signals for state changes
    state_changed = Signal()
    track_add_requested = Signal()
    track_remove_requested = Signal(int)
    track_rename_requested = Signal(int)
    subtitle_rename_requested = Signal()
    
    # Constants matching TimelineWidget
    _RULER_H = 14
    _CLIP_Y = 16
    _CLIP_H = 32
    _SEG_Y = 52
    _SEG_H = 40
    _AUDIO_Y = 96
    _AUDIO_H = 34
    _WAVEFORM_Y = 134
    _WAVEFORM_H = 45
    _IMG_BASE_Y = 184
    _BGM_H = 34
    _TRACK_GAP = 4
    _IMG_ROW_H = 40
    _TEXT_ROW_H = 28
    
    # Colors
    _BG_COLOR = QColor(25, 25, 25)
    _TEXT_COLOR = QColor(180, 180, 180)
    _BORDER_COLOR = QColor(50, 50, 50)
    _ACTIVE_COLOR = QColor(100, 220, 255)
    _INACTIVE_COLOR = QColor(60, 60, 60)

    def __init__(self, timeline=None, parent=None):
        super().__init__(parent)
        self.setFixedWidth(120)
        self._timeline = timeline
        self._project = None

    def set_project(self, project):
        self._project = project
        self.update()

    def _get_tracks_layout(self):
        """Compute dynamic Y positions for all tracks."""
        if not self._project or not self._timeline:
            return []
            
        tracks = []
        
        # Video tracks
        num_v = len(self._project.video_tracks)
        for i in range(num_v):
            y = self._timeline._video_track_y(i)
            t_name = self._project.video_tracks[i].name or f"Video {i+1}"
            tracks.append({
                "y": y, "h": self._CLIP_H, 
                "name": t_name,
                "controls": "LMH", "track_type": "video", "index": i
            })
        
        # Subtitle track (Simplified: only active track shown or grouped)
        y = self._timeline._subtitle_track_y()
        sub_name = "Subtitles"
        if self._project and self._project.subtitle_track:
            sub_name = self._project.subtitle_track.name or "Subtitles"
        tracks.append({
            "y": y, "h": self._SEG_H, 
            "name": sub_name, "controls": "LMH", "track_type": "subtitle"
        })
        
        # Audio track (if any)
        y = self._timeline._audio_track_y()
        tracks.append({
            "y": y, "h": self._AUDIO_H, 
            "name": "TTS Audio", "controls": "LMH", "track_type": "audio"
        })
        
        # Image Overlays
        y = self._timeline._img_overlay_base_y()
        next_y = self._timeline._text_overlay_base_y()
        h = max(self._IMG_ROW_H, next_y - y - self._TRACK_GAP)
        tracks.append({
            "y": y, "h": h, "name": "Images", "controls": "LH", "track_type": "overlay"
        })

        # Text Overlays
        y = next_y
        next_y = self._timeline._bgm_track_base_y()
        h = max(self._TEXT_ROW_H, next_y - y - self._TRACK_GAP)
        tracks.append({
            "y": y, "h": h, "name": "Text", "controls": "LH", "track_type": "text"
        })

        # BGM Tracks
        if hasattr(self._project, "bgm_tracks"):
            for i, track in enumerate(self._project.bgm_tracks):
                y = self._timeline._bgm_track_y(i)
                tracks.append({
                    "y": y, "h": self._BGM_H,
                    "name": track.name or f"BGM {i+1}",
                    "controls": "LM", "track_type": "bgm", "index": i
                })
        
        return tracks

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.fillRect(self.rect(), self._BG_COLOR)
        painter.fillRect(0, 0, self.width(), self._RULER_H, QColor(35, 35, 35))
        painter.setPen(self._BORDER_COLOR)
        painter.drawLine(0, self._RULER_H, self.width(), self._RULER_H)

        if not self._project:
            painter.end()
            return

        for track_info in self._get_tracks_layout():
            self._draw_track_header(painter, track_info)
            
        painter.setPen(self._BORDER_COLOR)
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.end()

    def _get_track_state(self, info):
        if not self._project:
            return False, False, False
        
        tt = info["track_type"]
        if tt == "video":
            t = self._project.video_tracks[info["index"]]
            return t.locked, t.muted, t.hidden
        elif tt == "subtitle":
            t = self._project.subtitle_track
            return t.locked, t.muted, t.hidden
        elif tt == "audio":
            t = self._project.subtitle_track
            if t is None:
                return False, False, False
            return getattr(t, "locked", False), getattr(t, "muted", False), getattr(t, "hidden", False)
        elif tt == "overlay":
            t = self._project.image_overlay_track
            return t.locked, False, t.hidden
        elif tt == "text":
            t = self._project.text_overlay_track
            return t.locked, False, t.hidden
        elif tt == "bgm":
            t = self._project.bgm_tracks[info["index"]]
            return t.locked, t.muted, False
        return False, False, False

    def _draw_track_header(self, painter, info):
        y, h, name = info["y"], info["h"], info["name"]
        
        # BG for track
        painter.setPen(self._BORDER_COLOR)
        painter.drawLine(0, int(y + h), self.width(), int(y + h))

        # Track Name
        painter.setPen(self._TEXT_COLOR)
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        painter.drawText(6, int(y) + 14, name)
        
        # Controls
        locked, muted, hidden = self._get_track_state(info)
        
        ctrl_x = int(self.width()) - 80
        ctrl_y = int(y) + 12
        
        controls_str = str(info["controls"])
        if "L" in controls_str:
            self._draw_btn(painter, ctrl_x, ctrl_y, "L", "Locked" if locked else "Unlocked", locked)
            ctrl_x += 24
        if "M" in controls_str:
            self._draw_btn(painter, ctrl_x, ctrl_y, "M", "Muted" if muted else "Unmuted", muted)
            ctrl_x += 24
        if "H" in controls_str:
            self._draw_btn(painter, ctrl_x, ctrl_y, "V", "Visible" if not hidden else "Hidden", hidden)

    def _draw_btn(self, painter, x, y, label, tooltip, active):
        rect = QRect(x, y, 20, 20)
        if active:
            painter.setBrush(QBrush(QColor(100, 220, 255, 60)))
            painter.setPen(QPen(self._ACTIVE_COLOR, 1))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self._INACTIVE_COLOR, 1))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(self._TEXT_COLOR if not active else Qt.GlobalColor.white)
        painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    def mousePressEvent(self, event: QMouseEvent):
        if not self._project:
            return

        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event)
            return
            
        x, y = event.position().x(), event.position().y()
        
        for info in self._get_tracks_layout():
            ty = info["y"]
            ctrl_x = self.width() - 80
            ctrl_y = ty + 12
            
            if "L" in info["controls"]:
                if QRect(ctrl_x, ctrl_y, 20, 20).contains(int(x), int(y)):
                    self._toggle_state(info, "locked")
                    return
                ctrl_x += 24
            if "M" in info["controls"]:
                if QRect(ctrl_x, ctrl_y, 20, 20).contains(int(x), int(y)):
                    self._toggle_state(info, "muted")
                    return
                ctrl_x += 24
            if "H" in info["controls"]:
                if QRect(ctrl_x, ctrl_y, 20, 20).contains(int(x), int(y)):
                    self._toggle_state(info, "hidden")
                    return

    def _show_context_menu(self, event):
        menu = QMenu(self)
        add_act = menu.addAction(tr("Add Video Track"))
        
        y = event.position().y()
        clicked_index = -1
        
        for info in self._get_tracks_layout():
            if info["track_type"] == "video":
                ty = info["y"]
                th = info["h"]
                if ty <= y < ty + th:
                    clicked_index = info["index"]
                    break
        
        remove_act = None
        if clicked_index >= 0 and len(self._project.video_tracks) > 1:
            remove_act = menu.addAction(tr("Remove Video Track"))
            
        action = menu.exec(event.globalPos())
        if action == add_act:
            self.track_add_requested.emit()
        elif remove_act and action == remove_act:
            self.track_remove_requested.emit(clicked_index)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if not self._project:
            return
            
        y = event.position().y()
        for info in self._get_tracks_layout():
            ty = info["y"]
            th = info["h"]
            if ty <= y < ty + th:
                if info["track_type"] == "video":
                    self.track_rename_requested.emit(info["index"])
                elif info["track_type"] in ("subtitle", "audio"):
                    # Audio track in header currently represents TTS audio of the subtitle track
                    self.subtitle_rename_requested.emit()
                return

    def _toggle_state(self, info, field):
        if not self._project: return
        
        tt = info["track_type"]
        target = None
        if tt == "video":
            target = self._project.video_tracks[info["index"]]
        elif tt == "subtitle":
            target = self._project.subtitle_track
        elif tt == "audio":
            target = self._project.subtitle_track # fallback
        elif tt == "overlay":
            target = self._project.image_overlay_track
        elif tt == "text":
            target = self._project.text_overlay_track
        elif tt == "bgm":
            target = self._project.bgm_tracks[info["index"]]
            
        if target is not None:
            current = getattr(target, field)
            setattr(target, field, not current)
            self.state_changed.emit()
            self.update()
