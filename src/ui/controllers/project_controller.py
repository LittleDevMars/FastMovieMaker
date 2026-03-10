"""ProjectController — 저장/로드/복구/최근파일/내보내기 로직."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMessageBox

from src.services.project_sync_service import (
    ProjectSyncService,
    SyncPolicy,
    SyncResult,
    SyncResultCode,
)
from src.services.settings_manager import SettingsManager
from src.utils.config import APP_NAME, find_ffmpeg
from src.utils.i18n import tr

if TYPE_CHECKING:
    from src.ui.controllers.app_context import AppContext


class ProjectController:
    """프로젝트 저장/로드/복구/내보내기 Controller."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # ---- 저장 / 로드 ----

    def on_save_project(self) -> None:
        ctx = self.ctx
        if not ctx.project.has_video:
            QMessageBox.warning(ctx.window, tr("No Video"), tr("Please open a video file first."))
            return
        path, _ = QFileDialog.getSaveFileName(
            ctx.window, tr("Save Project"), "", "FastMovieMaker Project (*.fmm *.fmm.json);;All Files (*)"
        )
        if not path:
            return
        try:
            from src.services.project_io import save_project
            path = Path(path)
            save_project(ctx.project, path)
            ctx.current_project_path = path
            ctx.autosave.set_active_file(path)
            self.update_recent_menu()
            ctx.status_bar().showMessage(f"{tr('Project saved')}: {path}")
            self._maybe_auto_push_on_save(path)
        except Exception as e:
            QMessageBox.critical(ctx.window, tr("Save Error"), str(e))

    def on_load_project(self, path=None) -> None:
        ctx = self.ctx
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                ctx.window, tr("Load Project"), "", "FastMovieMaker Project (*.fmm *.fmm.json);;All Files (*)"
            )
            if not path:
                return
        try:
            from src.services.project_io import load_project
            path = Path(path)
            project = load_project(path)
            ctx.project = project
            ctx.current_project_path = path
            ctx.autosave.set_project(project)
            ctx.autosave.set_active_file(path)
            ctx.undo_stack.clear()
            ctx.timeline.set_project(project)

            # Waveform service 설정
            from src.services.timeline_waveform_service import TimelineWaveformService
            waveform_svc = getattr(ctx.window, "_waveform_service", None)
            if waveform_svc:
                ctx.timeline.set_waveform_service(waveform_svc)

            track_headers = getattr(ctx.window, "_track_headers", None)
            if track_headers:
                track_headers.set_project(project)

            ctx.refresh_all()

            if project.video_path and project.video_path.is_file():
                ctx.current_playback_source = str(project.video_path)
                ctx.current_clip_index = 0
                ctx.player.setSource(QUrl.fromLocalFile(str(project.video_path)))
                ctx.player.play()
                ctx.window.setWindowTitle(f"{project.video_path.name} – {APP_NAME}")

            ctx.timeline.refresh()
            ctx.media_ctrl.start_frame_cache_generation()
            self.update_recent_menu()
            ctx.status_bar().showMessage(f"{tr('Project loaded')}: {path}")
        except Exception as e:
            QMessageBox.critical(ctx.window, tr("Load Error"), str(e))

    def on_sync_project(self) -> None:
        """Manually sync the current project with the configured sync folder."""
        ctx = self.ctx
        current_path = ctx.current_project_path
        if current_path is None:
            QMessageBox.warning(ctx.window, tr("No Project"), tr("Please save or load a project file first."))
            return
        if not current_path.is_file():
            QMessageBox.warning(ctx.window, tr("File Not Found"), tr("Project file does not exist."))
            return

        # Keep sync source aligned with current in-memory edits.
        try:
            from src.services.project_io import save_project

            save_project(ctx.project, current_path)
        except Exception as exc:
            QMessageBox.critical(
                ctx.window,
                tr("Sync Failed"),
                tr("Failed to save project before sync.") + f"\n{exc}",
            )
            return

        settings = SettingsManager()
        sync_service = ProjectSyncService(settings=settings)
        result = sync_service.sync(current_path, policy=SyncPolicy.AUTO)
        if result.code == SyncResultCode.CONFLICT:
            choice = self._prompt_sync_conflict(result)
            if choice is None:
                ctx.status_bar().showMessage(tr("Sync canceled."), 3000)
                return
            result = sync_service.sync(current_path, policy=choice)
            if result.code == SyncResultCode.SUCCESS and choice == SyncPolicy.USE_REMOTE:
                self.on_load_project(path=current_path)
            if choice == SyncPolicy.USE_LOCAL:
                self._show_sync_result(result, success_message=tr("Project synced using local version."))
                return
            if choice == SyncPolicy.USE_REMOTE:
                self._show_sync_result(result, success_message=tr("Project synced using remote version."))
                return
        self._show_sync_result(result)

    def _maybe_auto_push_on_save(self, project_path: Path) -> None:
        settings = SettingsManager()
        if not settings.get_project_sync_auto_push_on_save():
            return
        sync_service = ProjectSyncService(settings=settings)
        result = sync_service.sync(project_path, policy=SyncPolicy.USE_LOCAL)
        if result.code == SyncResultCode.SUCCESS:
            self.ctx.status_bar().showMessage(tr("Project saved and synced."), 3000)
            return
        if result.code == SyncResultCode.NO_CHANGES:
            self.ctx.status_bar().showMessage(tr("Project saved and sync is up to date."), 3000)
            return
        detail = f"\n{result.detail}" if result.detail else ""
        QMessageBox.warning(
            self.ctx.window,
            tr("Sync Failed"),
            tr("Auto sync failed after save.") + detail,
        )

    # ---- 내보내기 ----

    def on_export_video(self) -> None:
        ctx = self.ctx
        if not ctx.project.has_video:
            QMessageBox.warning(ctx.window, tr("No Video"), tr("Please open a video file first."))
            return
        if not find_ffmpeg():
            QMessageBox.critical(ctx.window, tr("FFmpeg Missing"), tr("FFmpeg is required for video export."))
            return
        from src.ui.dialogs.export_dialog import ExportDialog
        overlay_template = getattr(ctx.window, "_overlay_template", None)
        overlay_path = Path(overlay_template.image_path) if overlay_template else None
        io_track = ctx.project.image_overlay_track
        img_overlays = list(io_track.overlays) if len(io_track) > 0 else None
        video_tracks = list(ctx.project.video_tracks)
        text_overlays = (
            list(ctx.project.text_overlay_track.overlays) if len(ctx.project.text_overlay_track) > 0 else None
        )
        dialog = ExportDialog(
            ctx.project.video_path, ctx.project.subtitle_track, parent=ctx.window,
            video_has_audio=ctx.project.video_has_audio, overlay_path=overlay_path,
            overlay_template=overlay_template,
            image_overlays=img_overlays, video_tracks=video_tracks, text_overlays=text_overlays,
        )
        dialog.exec()

    def on_batch_export(self) -> None:
        ctx = self.ctx
        if not ctx.project.has_video:
            QMessageBox.warning(ctx.window, tr("No Video"), tr("Please open a video file first."))
            return
        if not find_ffmpeg():
            QMessageBox.critical(ctx.window, tr("FFmpeg Missing"), tr("FFmpeg is required for video export."))
            return
        overlay_template = getattr(ctx.window, "_overlay_template", None)
        overlay_path = Path(overlay_template.image_path) if overlay_template else None
        io_track = ctx.project.image_overlay_track
        img_overlays = list(io_track.overlays) if len(io_track) > 0 else None
        text_overlays = (
            list(ctx.project.text_overlay_track.overlays) if len(ctx.project.text_overlay_track) > 0 else None
        )
        from src.ui.dialogs.batch_export_dialog import BatchExportDialog
        dialog = BatchExportDialog(
            ctx.project.video_path, ctx.project.subtitle_track, parent=ctx.window,
            video_has_audio=ctx.project.video_has_audio, overlay_path=overlay_path,
            image_overlays=img_overlays, text_overlays=text_overlays,
        )
        dialog.exec()

    # ---- 복구 ----

    def check_recovery(self) -> None:
        ctx = self.ctx
        recovery_path = ctx.autosave.check_for_recovery()
        if not recovery_path:
            return
        from src.ui.dialogs.recovery_dialog import RecoveryDialog
        dialog = RecoveryDialog([recovery_path], ctx.window)
        result = dialog.exec()
        if result == 1:
            try:
                recovery_file = dialog.get_selected_file()
                recovered_project = ctx.autosave.load_recovery(recovery_file)
                ctx.project = recovered_project
                if recovered_project.video_path and recovered_project.video_path.is_file():
                    ctx.player.setSource(QUrl.fromLocalFile(str(recovered_project.video_path)))
                    ctx.window.setWindowTitle(f"{recovered_project.video_path.name} – {APP_NAME} (Recovered)")
                if recovered_project.has_subtitles:
                    ctx.video_widget.set_default_style(recovered_project.default_style)
                    track = recovered_project.subtitle_track
                    ctx.video_widget.set_subtitle_track(track)
                    ctx.subtitle_panel.set_track(track)
                    ctx.timeline.set_track(track)
                    ctx.refresh_track_selector()
                ctx.status_bar().showMessage(tr("Project recovered successfully"))
            except Exception as e:
                QMessageBox.critical(ctx.window, tr("Recovery Error"), str(e))
        ctx.autosave.cleanup_recovery_files()

    # ---- 최근 파일 ----

    def update_recent_menu(self) -> None:
        ctx = self.ctx
        recent_menu = getattr(ctx.window, "_recent_menu", None)
        if not recent_menu:
            return
        recent_menu.clear()
        recent_files = ctx.autosave.get_recent_files()
        if not recent_files:
            no_recent = QAction(tr("No Recent Projects"), ctx.window)
            no_recent.setEnabled(False)
            recent_menu.addAction(no_recent)
            return
        for i, p in enumerate(recent_files):
            action = QAction(f"{i + 1}. {p.name}", ctx.window)
            action.setData(str(p))
            action.triggered.connect(self.on_open_recent)
            recent_menu.addAction(action)
        recent_menu.addSeparator()
        clear_action = QAction(tr("Clear Recent Projects"), ctx.window)
        clear_action.triggered.connect(self.on_clear_recent)
        recent_menu.addAction(clear_action)

    def on_open_recent(self) -> None:
        ctx = self.ctx
        action = ctx.window.sender()
        if action and action.data():
            path = Path(action.data())
            if path.is_file():
                self.on_load_project(path)
            else:
                QMessageBox.warning(
                    ctx.window, tr("File Not Found"),
                    f"{tr('The file')} {path} {tr('no longer exists.')}"
                )
                ctx.autosave.get_recent_files()
                self.update_recent_menu()

    def on_clear_recent(self) -> None:
        self.ctx.autosave.clear_recent_files()
        self.update_recent_menu()

    # ---- 오토세이브 / 편집 ----

    def on_autosave_completed(self, path: Path) -> None:
        self.ctx.status_bar().showMessage(f"{tr('Autosaved')}: {path.name}", 2000)

    def on_document_edited(self) -> None:
        self.ctx.autosave.notify_edit()

    def _prompt_sync_conflict(self, result: SyncResult) -> SyncPolicy | None:
        box = QMessageBox(self.ctx.window)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("Sync Conflict"))
        box.setText(tr("Both local and synced versions changed. Choose which one to keep."))
        box.setInformativeText(tr("Review local and remote summaries before choosing."))
        box.setDetailedText(self._build_conflict_summary(result))
        local_btn = box.addButton(tr("Use Local"), QMessageBox.ButtonRole.AcceptRole)
        remote_btn = box.addButton(tr("Use Remote"), QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == local_btn:
            return SyncPolicy.USE_LOCAL
        if clicked == remote_btn:
            return SyncPolicy.USE_REMOTE
        if clicked == cancel_btn:
            return None
        return None

    def _show_sync_result(self, result: SyncResult, success_message: str | None = None) -> None:
        if result.code == SyncResultCode.SUCCESS:
            self.ctx.status_bar().showMessage(success_message or tr("Project sync completed."), 3000)
            return
        if result.code == SyncResultCode.NO_CHANGES:
            self.ctx.status_bar().showMessage(tr("Project is already up to date."), 3000)
            return
        if result.code == SyncResultCode.CONFLICT:
            QMessageBox.warning(self.ctx.window, tr("Sync Conflict"), tr(result.message))
            return
        detail = f"\n{result.detail}" if result.detail else ""
        QMessageBox.critical(self.ctx.window, tr("Sync Failed"), tr(result.message) + detail)

    def _build_conflict_summary(self, result: SyncResult) -> str:
        local_summary = self._format_sync_file_info(tr("Local"), result.local_info)
        remote_summary = self._format_sync_file_info(tr("Remote"), result.remote_info)
        lines = [local_summary, "", remote_summary]
        if result.conflict_reason:
            lines.extend(["", f"{tr('Reason')}: {self._friendly_conflict_reason(result.conflict_reason)}"])
        return "\n".join(lines)

    @staticmethod
    def _format_sync_file_info(label: str, info) -> str:
        if info is None:
            return f"{label}: {tr('Unavailable')}"
        hash_short = info.sha256[:8] if info.sha256 else "-"
        modified = info.modified_at or "-"
        return (
            f"{label}: {info.path}\n"
            f"{tr('Modified')}: {modified}\n"
            f"{tr('Size')}: {info.size_bytes} {tr('bytes')}\n"
            f"{tr('Hash')}: {hash_short}"
        )

    @staticmethod
    def _friendly_conflict_reason(reason: str) -> str:
        if reason == "local_and_remote_changed":
            return tr("Local and remote changed since last sync.")
        return reason
