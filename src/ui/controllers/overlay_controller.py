"""OverlayController — 이미지/텍스트 오버레이 로직."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from src.models.image_overlay import ImageOverlay
from src.utils.i18n import tr

if TYPE_CHECKING:
    from src.ui.controllers.app_context import AppContext


class OverlayController:
    """이미지/텍스트 오버레이 CRUD Controller."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # ---- 이미지 오버레이 ----

    def on_insert_image_overlay(self, position_ms: int) -> None:
        ctx = self.ctx
        path, _ = QFileDialog.getOpenFileName(
            ctx.window, "Select Image for Overlay", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not path:
            return
        duration = 5000
        end_ms = position_ms + duration
        if ctx.project.duration_ms > 0:
            end_ms = min(end_ms, ctx.project.duration_ms)
        overlay = ImageOverlay(start_ms=position_ms, end_ms=end_ms, image_path=str(Path(path).resolve()))
        ctx.project.image_overlay_track.add_overlay(overlay)
        io_track = ctx.project.image_overlay_track
        ctx.ensure_timeline_duration()
        ctx.timeline.set_image_overlay_track(io_track)
        ctx.video_widget.set_image_overlay_track(io_track)
        ctx.autosave.notify_edit()
        ctx.status_bar().showMessage(f"Image overlay inserted: {Path(path).name}")

    def on_image_overlay_moved(self, index: int, new_start: int, new_end: int) -> None:
        ctx = self.ctx
        io_track = ctx.project.image_overlay_track
        if 0 <= index < len(io_track):
            ov = io_track[index]
            ov.start_ms = new_start
            ov.end_ms = new_end
            ctx.ensure_timeline_duration()
            ctx.timeline.update()
            ctx.autosave.notify_edit()
            ctx.status_bar().showMessage(f"Image overlay {index + 1} moved")

    def on_image_overlay_selected(self, index: int) -> None:
        self.ctx.video_widget.select_pip(index)
        self.ctx.status_bar().showMessage(f"Image overlay {index + 1} selected")

    def on_image_overlay_resize(self, index: int, mode: str) -> None:
        """이미지 오버레이 프리셋 리사이즈."""
        ctx = self.ctx
        io_track = ctx.project.image_overlay_track
        if not (0 <= index < len(io_track)):
            return
        ov = io_track[index]
        vw = ctx.video_widget.viewport().width() or 1920
        vh = ctx.video_widget.viewport().height() or 1080
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap(ov.image_path)
        if pixmap.isNull():
            return
        iw, ih = pixmap.width(), pixmap.height()

        if mode == "fit":
            scale = min(vw / iw, vh / ih)
            ov.scale_percent = scale * iw / vw * 100
            ov.x_percent = (vw - iw * scale) / 2 / vw * 100
            ov.y_percent = (vh - ih * scale) / 2 / vh * 100
        elif mode == "fit_width":
            ov.scale_percent = 100.0
            ov.x_percent = 0.0
            ov.y_percent = (vh - ih * vw / iw) / 2 / vh * 100
        elif mode == "fit_height":
            scale = vh / ih
            ov.scale_percent = scale * iw / vw * 100
            ov.x_percent = (vw - iw * scale) / 2 / vw * 100
            ov.y_percent = 0.0
        elif mode == "full":
            scale = max(vw / iw, vh / ih)
            ov.scale_percent = scale * iw / vw * 100
            ov.x_percent = -(iw * scale - vw) / 2 / vw * 100
            ov.y_percent = -(ih * scale - vh) / 2 / vh * 100
        elif mode == "16:9":
            box_h = vw * 9 / 16
            scale = min(vw / iw, box_h / ih)
            ov.scale_percent = scale * iw / vw * 100
            ov.x_percent = (vw - iw * scale) / 2 / vw * 100
            ov.y_percent = (vh - ih * scale) / 2 / vh * 100
        elif mode == "9:16":
            box_w = vh * 9 / 16
            scale = min(box_w / iw, vh / ih)
            ov.scale_percent = scale * iw / vw * 100
            ov.x_percent = (vw - iw * scale) / 2 / vw * 100
            ov.y_percent = (vh - ih * scale) / 2 / vh * 100

        ctx.video_widget.set_image_overlay_track(io_track)
        ctx.timeline.update()
        ctx.autosave.notify_edit()
        ctx.status_bar().showMessage(f"Image overlay {index + 1}: {mode}")

    def on_delete_image_overlay(self, index: int) -> None:
        ctx = self.ctx
        io_track = ctx.project.image_overlay_track
        if 0 <= index < len(io_track):
            io_track.remove_overlay(index)
            ctx.timeline.set_image_overlay_track(io_track if len(io_track) > 0 else None)
            ctx.video_widget.set_image_overlay_track(io_track if len(io_track) > 0 else None)
            ctx.autosave.notify_edit()
            ctx.status_bar().showMessage(tr("Image overlay deleted"))

    def on_pip_position_changed(self, index: int, x_pct: float, y_pct: float, scale_pct: float) -> None:
        ctx = self.ctx
        io_track = ctx.project.image_overlay_track
        if 0 <= index < len(io_track):
            ov = io_track[index]
            ov.x_percent = round(x_pct, 2)
            ov.y_percent = round(y_pct, 2)
            ov.scale_percent = round(scale_pct, 2)
            ctx.autosave.notify_edit()

    # ---- 텍스트 오버레이 ----

    def on_add_text_overlay(self, position_ms: int = -1) -> None:
        ctx = self.ctx
        if not ctx.project.has_video:
            QMessageBox.warning(ctx.window, tr("No Video"), tr("Please open a video file first."))
            return
        if position_ms < 0:
            position_ms = ctx.timeline.get_playhead()
        from src.models.text_overlay import TextOverlay
        from src.ui.dialogs.text_overlay_dialog import TextOverlayDialog
        dialog = TextOverlayDialog(parent=ctx.window, text="New Text", style=None)
        dialog.set_position(50.0, 50.0)
        dialog.set_opacity(1.0)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text = dialog.get_text()
        style = dialog.get_style()
        x_percent, y_percent = dialog.get_position()
        opacity = dialog.get_opacity()
        duration = 5000
        end_ms = position_ms + duration
        if ctx.project.duration_ms > 0:
            end_ms = min(end_ms, ctx.project.duration_ms)
        overlay = TextOverlay(
            start_ms=position_ms, end_ms=end_ms, text=text,
            x_percent=x_percent, y_percent=y_percent, opacity=opacity, style=style,
        )
        from src.ui.commands import AddTextOverlayCommand
        cmd = AddTextOverlayCommand(ctx.project.text_overlay_track, overlay)
        ctx.undo_stack.push(cmd)
        ctx.ensure_timeline_duration()
        ctx.timeline.set_text_overlay_track(ctx.project.text_overlay_track)
        ctx.video_widget.set_text_overlay_track(ctx.project.text_overlay_track)
        ctx.autosave.notify_edit()
        ctx.status_bar().showMessage(f"Text overlay added: {overlay.text[:20]}...")

    def on_text_overlay_moved(self, index: int, new_start: int, new_end: int) -> None:
        ctx = self.ctx
        text_track = ctx.project.text_overlay_track
        if 0 <= index < len(text_track.overlays):
            ov = text_track.overlays[index]
            from src.ui.commands import MoveTextOverlayCommand
            cmd = MoveTextOverlayCommand(ov, ov.start_ms, ov.end_ms, new_start, new_end)
            ctx.undo_stack.push(cmd)
            ctx.ensure_timeline_duration()
            ctx.timeline.update()
            ctx.video_widget.update()
            ctx.autosave.notify_edit()
            ctx.status_bar().showMessage(f"Text overlay {index + 1} moved")

    def on_text_overlay_selected(self, index: int) -> None:
        self.ctx.video_widget.select_text(index)
        self.ctx.status_bar().showMessage(f"Text overlay {index + 1} selected")

    def on_text_overlay_edit_requested(self, index: int) -> None:
        ctx = self.ctx
        text_track = ctx.project.text_overlay_track
        if not (text_track and 0 <= index < len(text_track.overlays)):
            return
        ov = text_track.overlays[index]
        from src.ui.dialogs.text_overlay_dialog import TextOverlayDialog
        dialog = TextOverlayDialog(parent=ctx.window, text=ov.text, style=ov.style)
        dialog.set_position(ov.x_percent, ov.y_percent)
        dialog.set_alignment(ov.alignment, ov.v_alignment)
        dialog.set_opacity(ov.opacity)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        old_data = {
            "text": ov.text, "style": ov.style,
            "x_percent": ov.x_percent, "y_percent": ov.y_percent,
            "alignment": ov.alignment, "v_alignment": ov.v_alignment, "opacity": ov.opacity,
        }
        h_align, v_align = dialog.get_alignment()
        new_data = {
            "text": dialog.get_text(), "style": dialog.get_style(),
            "x_percent": dialog.get_position()[0], "y_percent": dialog.get_position()[1],
            "alignment": h_align, "v_alignment": v_align, "opacity": dialog.get_opacity(),
        }
        from src.ui.commands import UpdateTextOverlayCommand
        cmd = UpdateTextOverlayCommand(ov, old_data, new_data)
        ctx.undo_stack.push(cmd)
        ctx.timeline.update()
        ctx.video_widget.update()
        ctx.autosave.notify_edit()
        ctx.status_bar().showMessage(f"Text overlay {index + 1} updated")

    def on_text_overlay_delete_requested(self, index: int) -> None:
        ctx = self.ctx
        text_track = ctx.project.text_overlay_track
        if not (text_track and 0 <= index < len(text_track.overlays)):
            return
        from src.ui.commands import DeleteTextOverlayCommand
        cmd = DeleteTextOverlayCommand(text_track, index)
        ctx.undo_stack.push(cmd)
        ctx.timeline.update()
        ctx.video_widget.update()
        ctx.autosave.notify_edit()
        ctx.status_bar().showMessage(f"Text overlay {index + 1} deleted")

    def on_text_overlay_position_changed(self, index: int, x_pct: float, y_pct: float) -> None:
        ctx = self.ctx
        track = ctx.project.text_overlay_track
        if track and 0 <= index < len(track.overlays):
            ov = track.overlays[index]
            ov.x_percent = round(x_pct, 2)
            ov.y_percent = round(y_pct, 2)
            ctx.autosave.notify_edit()

    # ---- 드래그 앤 드롭 ----

    def on_image_file_dropped(self, file_paths: list[str], position_ms: int) -> None:
        ctx = self.ctx
        duration = 5000
        for file_path in file_paths:
            end_ms = position_ms + duration
            if ctx.project.duration_ms > 0:
                end_ms = min(end_ms, ctx.project.duration_ms)
            overlay = ImageOverlay(start_ms=position_ms, end_ms=end_ms, image_path=str(Path(file_path).resolve()))
            ctx.project.image_overlay_track.add_overlay(overlay)
            
        io_track = ctx.project.image_overlay_track
        ctx.ensure_timeline_duration()
        ctx.timeline.set_image_overlay_track(io_track)
        ctx.video_widget.set_image_overlay_track(io_track)
        ctx.autosave.notify_edit()
        ctx.status_bar().showMessage(f"{len(file_paths)} image overlays dropped")

    def on_media_image_insert_to_timeline(self, file_path: str) -> None:
        ctx = self.ctx
        position_ms = ctx.player.position()
        duration = 5000
        end_ms = position_ms + duration
        if ctx.project.duration_ms > 0:
            end_ms = min(end_ms, ctx.project.duration_ms)
        overlay = ImageOverlay(start_ms=position_ms, end_ms=end_ms, image_path=str(Path(file_path).resolve()))
        ctx.project.image_overlay_track.add_overlay(overlay)
        io_track = ctx.project.image_overlay_track
        ctx.ensure_timeline_duration()
        ctx.timeline.set_image_overlay_track(io_track)
        ctx.video_widget.set_image_overlay_track(io_track)
        ctx.autosave.notify_edit()
        ctx.status_bar().showMessage(f"Image overlay inserted from library: {Path(file_path).name}")
