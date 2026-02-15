"""SubtitleController — 자막 CRUD/임포트/익스포트/Whisper/TTS 로직."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from src.models.subtitle import SubtitleSegment, SubtitleTrack
from src.services.subtitle_exporter import export_srt, import_smi, import_srt
from src.ui.commands import (
    AddSegmentCommand,
    BatchShiftCommand,
    DeleteSegmentCommand,
    EditStyleCommand,
    EditTextCommand,
    EditTimeCommand,
    EditVolumeCommand,
    MergeCommand,
    MoveSegmentCommand,
    SplitCommand,
)
from src.utils.config import find_ffmpeg
from src.utils.i18n import tr

if TYPE_CHECKING:
    from src.ui.controllers.app_context import AppContext


class SubtitleController:
    """자막 편집, 임포트/익스포트, Whisper/TTS 통합 Controller."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        # Whisper 실시간 미리보기 상태
        self._whisper_preview_active: bool = False
        self._whisper_original_segments: list | None = None
        self._whisper_dialog_cancelled: bool = False

    # ---- 기본 편집 (Undo 지원) ----

    def on_text_edited(self, index: int, new_text: str) -> None:
        track = self.ctx.project.subtitle_track
        if 0 <= index < len(track):
            old_text = track[index].text
            cmd = EditTextCommand(track, index, old_text, new_text)
            self.ctx.undo_stack.push(cmd)
            self.ctx.status_bar().showMessage(f"{tr('Text updated')} ({tr('segment')} {index + 1})")

    def on_time_edited(self, index: int, start_ms: int, end_ms: int) -> None:
        track = self.ctx.project.subtitle_track
        if 0 <= index < len(track):
            seg = track[index]
            cmd = EditTimeCommand(track, index, seg.start_ms, seg.end_ms, start_ms, end_ms)
            self.ctx.undo_stack.push(cmd)
            self.ctx.status_bar().showMessage(f"{tr('Time updated')} ({tr('segment')} {index + 1})")

    def on_segment_volume_edited(self, index: int, volume: float) -> None:
        track = self.ctx.project.subtitle_track
        if 0 <= index < len(track):
            old_volume = track[index].volume
            cmd = EditVolumeCommand(track, index, old_volume, volume)
            self.ctx.undo_stack.push(cmd)
            self.ctx.status_bar().showMessage(
                f"{tr('Volume updated')}: {int(volume * 100)}% ({tr('segment')} {index + 1})"
            )

    def on_segment_add(self, start_ms: int, end_ms: int) -> None:
        seg = SubtitleSegment(start_ms, end_ms, "New subtitle")
        cmd = AddSegmentCommand(self.ctx.project.subtitle_track, seg)
        self.ctx.undo_stack.push(cmd)
        self.ctx.status_bar().showMessage(tr("Subtitle added"))

    def on_segment_delete(self, index: int) -> None:
        track = self.ctx.project.subtitle_track
        if 0 <= index < len(track):
            seg = track[index]
            cmd = DeleteSegmentCommand(track, index, seg)
            self.ctx.undo_stack.push(cmd)
            self.ctx.status_bar().showMessage(tr("Subtitle deleted"))

    # ---- 타임라인 연동 ----

    def on_timeline_segment_selected(self, index: int) -> None:
        ctx = self.ctx
        if ctx.project.has_subtitles and 0 <= index < len(ctx.project.subtitle_track):
            ctx.subtitle_panel._table.selectRow(index)
            seg = ctx.project.subtitle_track[index]
            if seg.audio_file and Path(seg.audio_file).exists():
                ctx.tts_player.setSource(QUrl.fromLocalFile(seg.audio_file))
                ctx.tts_player.play()

    def on_timeline_segment_moved(self, index: int, new_start: int, new_end: int) -> None:
        ctx = self.ctx
        track = ctx.project.subtitle_track
        if 0 <= index < len(track):
            seg = track[index]
            cmd = MoveSegmentCommand(track, index, seg.start_ms, seg.end_ms, new_start, new_end)
            ctx.undo_stack.push(cmd)
            ctx.video_widget.set_subtitle_track(track)
            ctx.subtitle_panel.set_track(track)
            ctx.status_bar().showMessage(f"{tr('segment')} {index + 1} {tr('moved')}")

    def on_timeline_audio_moved(self, new_start_ms: int, new_duration_ms: int) -> None:
        """오디오 트랙 이동/리사이즈."""
        track = self.ctx.project.subtitle_track
        if track and track.audio_path:
            track.audio_start_ms = new_start_ms
            track.audio_duration_ms = new_duration_ms
            self.ctx.status_bar().showMessage(
                f"Audio track adjusted: {new_start_ms}ms ~ {new_start_ms + new_duration_ms}ms"
            )

    # ---- 분할 / 병합 / 일괄 시프트 ----

    def on_split_subtitle(self) -> None:
        ctx = self.ctx
        if not ctx.project.has_subtitles:
            QMessageBox.warning(ctx.window, tr("No Subtitles"), tr("No subtitles to split."))
            return
        rows = ctx.subtitle_panel._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(ctx.window, tr("No Selection"), tr("Select a subtitle to split."))
            return
        index = rows[0].row()
        track = ctx.project.subtitle_track
        if index < 0 or index >= len(track):
            return
        seg = track[index]
        split_ms = ctx.player.position()
        if split_ms <= seg.start_ms or split_ms >= seg.end_ms:
            QMessageBox.warning(
                ctx.window, tr("Invalid Position"),
                tr("Move the playhead inside the selected subtitle to split it.")
            )
            return
        words = seg.text.split()
        mid = max(1, len(words) // 2)
        text1 = " ".join(words[:mid])
        text2 = " ".join(words[mid:])
        if not text1:
            text1 = seg.text
        if not text2:
            text2 = seg.text
        first = SubtitleSegment(seg.start_ms, split_ms, text1, style=seg.style)
        second = SubtitleSegment(split_ms, seg.end_ms, text2, style=seg.style)
        cmd = SplitCommand(track, index, split_ms, seg, first, second)
        ctx.undo_stack.push(cmd)
        ctx.status_bar().showMessage(f"{tr('segment')} {index + 1} {tr('split at')} {split_ms}ms")

    def on_merge_subtitles(self) -> None:
        ctx = self.ctx
        if not ctx.project.has_subtitles:
            QMessageBox.warning(ctx.window, tr("No Subtitles"), tr("No subtitles to merge."))
            return
        rows = ctx.subtitle_panel._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(ctx.window, tr("No Selection"), tr("Select a subtitle to merge with the next one."))
            return
        index = rows[0].row()
        track = ctx.project.subtitle_track
        if index < 0 or index + 1 >= len(track):
            QMessageBox.warning(ctx.window, tr("Cannot Merge"), tr("Select a subtitle that has a following subtitle."))
            return
        first = track[index]
        second = track[index + 1]
        merged_text = first.text + " " + second.text
        merged = SubtitleSegment(first.start_ms, second.end_ms, merged_text, style=first.style)
        cmd = MergeCommand(track, index, first, second, merged)
        ctx.undo_stack.push(cmd)
        ctx.status_bar().showMessage(f"{tr('Segments')} {index + 1}-{index + 2} {tr('merged')}")

    def on_batch_shift(self) -> None:
        ctx = self.ctx
        if not ctx.project.has_subtitles:
            QMessageBox.warning(ctx.window, tr("No Subtitles"), tr("No subtitles to shift."))
            return
        offset, ok = QInputDialog.getInt(
            ctx.window, tr("Batch Shift"), tr("Offset (ms, negative=earlier):"), 0, -60000, 60000, 100
        )
        if not ok or offset == 0:
            return
        cmd = BatchShiftCommand(ctx.project.subtitle_track, offset)
        ctx.undo_stack.push(cmd)
        ctx.status_bar().showMessage(f"All subtitles shifted by {offset:+d}ms")

    # ---- 스타일 ----

    def on_edit_default_style(self) -> None:
        from src.ui.dialogs.style_dialog import StyleDialog
        ctx = self.ctx
        dialog = StyleDialog(ctx.project.default_style, parent=ctx.window, title=tr("Default Subtitle Style"))
        if dialog.exec():
            ctx.project.default_style = dialog.result_style()
            ctx.video_widget.set_default_style(ctx.project.default_style)
            ctx.status_bar().showMessage(tr("Default style updated"))

    def on_edit_segment_style(self, index: int) -> None:
        ctx = self.ctx
        if not ctx.project.has_subtitles or index < 0 or index >= len(ctx.project.subtitle_track):
            return
        from src.ui.dialogs.style_dialog import StyleDialog
        seg = ctx.project.subtitle_track[index]
        current_style = seg.style if seg.style is not None else ctx.project.default_style
        dialog = StyleDialog(current_style, parent=ctx.window, title=f"{tr('Style')} - {tr('Segment')} {index + 1}")
        if dialog.exec():
            old_style = seg.style
            new_style = dialog.result_style()
            cmd = EditStyleCommand(ctx.project.subtitle_track, index, old_style, new_style)
            ctx.undo_stack.push(cmd)
            ctx.video_widget.set_default_style(ctx.project.default_style)
            ctx.status_bar().showMessage(f"{tr('Style updated')} ({tr('segment')} {index + 1})")

    def on_toggle_position_edit(self, checked: bool) -> None:
        """자막 위치 편집 모드 토글."""
        ctx = self.ctx
        ctx.video_widget.set_subtitle_edit_mode(checked)
        if checked:
            ctx.status_bar().showMessage(tr("Edit Mode: Drag subtitle to reposition. Press Ctrl+E again to save."))
        else:
            position = ctx.video_widget.get_subtitle_position()
            if position:
                x, y = position
                current_track = ctx.project.subtitle_track
                if current_track and len(current_track) > 0:
                    ctx.project.default_style.custom_x = x
                    ctx.project.default_style.custom_y = y
                    ctx.video_widget.set_default_style(ctx.project.default_style)
                    ctx.video_widget.set_subtitle_track(current_track)
                    current_pos = ctx.player.position()
                    ctx.playback_ctrl.on_player_position_changed(current_pos)
                    ctx.status_bar().showMessage(f"{tr('Subtitle position saved')}: ({x}, {y})")
                    ctx.project_ctrl.on_document_edited()
            else:
                ctx.status_bar().showMessage(tr("Edit Mode OFF"))

    # ---- 임포트 / 익스포트 ----

    def on_import_srt(self, path=None) -> None:
        ctx = self.ctx
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                ctx.window, tr("Import SRT"), "", "SRT Files (*.srt);;All Files (*)"
            )
            if not path:
                return
        try:
            path = Path(path) if isinstance(path, str) else path
            track = import_srt(path)
            track.name = ctx.project.subtitle_track.name
            self.apply_subtitle_track(track)
            ctx.autosave.notify_edit()
        except Exception as e:
            QMessageBox.critical(ctx.window, tr("Import Error"), str(e))

    def on_import_srt_new_track(self, path: Path) -> None:
        """SRT를 새 트랙으로 임포트."""
        ctx = self.ctx
        try:
            track = import_srt(path)
            ctx.project.subtitle_tracks.append(track)
            ctx.refresh_track_selector()
            ctx.track_selector.blockSignals(True)
            ctx.track_selector.setCurrentIndex(len(ctx.project.subtitle_tracks) - 1)
            ctx.track_selector.blockSignals(False)
            ctx.project.active_track_index = len(ctx.project.subtitle_tracks) - 1
            self.on_track_changed(ctx.project.active_track_index)
            QMessageBox.information(ctx.window, tr("Import Complete"), tr("Subtitle track imported successfully."))
        except Exception as e:
            QMessageBox.critical(ctx.window, tr("Import Error"), f"{tr('Failed to import SRT')}: {e}")

    def on_import_subtitle(self, file_path: str) -> None:
        """미디어 라이브러리에서 자막 임포트."""
        path = Path(file_path)
        if path.suffix.lower() == ".srt":
            self.on_import_srt_new_track(path)
        elif path.suffix.lower() == ".smi":
            self.on_import_smi(path)

    def on_import_smi(self, path: Path) -> None:
        """SMI 파일을 새 트랙으로 임포트."""
        ctx = self.ctx
        try:
            track = import_smi(path)
            if not track:
                QMessageBox.warning(ctx.window, tr("Import Empty"), tr("No subtitles found in SMI file."))
                return
            ctx.project.subtitle_tracks.append(track)
            ctx.refresh_track_selector()
            new_idx = len(ctx.project.subtitle_tracks) - 1
            ctx.track_selector.blockSignals(True)
            ctx.track_selector.setCurrentIndex(new_idx)
            ctx.track_selector.blockSignals(False)
            ctx.project.active_track_index = new_idx
            self.on_track_changed(new_idx)
            QMessageBox.information(ctx.window, tr("Import Complete"), tr("SMI subtitle track imported successfully."))
        except Exception as e:
            QMessageBox.critical(ctx.window, tr("Import Error"), f"{tr('Failed to import SMI')}: {e}")

    def on_export_srt(self) -> None:
        ctx = self.ctx
        if not ctx.project.has_subtitles:
            QMessageBox.warning(ctx.window, tr("No Subtitles"), tr("There are no subtitles to export."))
            return
        path, _ = QFileDialog.getSaveFileName(
            ctx.window, tr("Export SRT"), "", "SRT Files (*.srt);;All Files (*)"
        )
        if not path:
            return
        try:
            export_srt(ctx.project.subtitle_track, Path(path))
            ctx.status_bar().showMessage(f"{tr('Exported')}: {path}")
        except OSError as e:
            QMessageBox.critical(ctx.window, tr("Export Error"), str(e))

    # ---- Whisper 자막 생성 ----

    def on_generate_subtitles(self) -> None:
        """원본 영상에서 자막 생성."""
        ctx = self.ctx
        if not ctx.project.has_video:
            QMessageBox.warning(ctx.window, tr("No Video"), tr("Please open a video file first."))
            return
        if not find_ffmpeg():
            QMessageBox.critical(ctx.window, tr("FFmpeg Missing"),
                                 tr("FFmpeg is required for subtitle generation but was not found."))
            return
        from src.ui.dialogs.whisper_dialog import WhisperDialog
        dialog = WhisperDialog(video_path=ctx.project.video_path, parent=ctx.window)
        self._whisper_dialog_cancelled = False
        dialog.segment_ready.connect(self.on_whisper_segment_ready)
        if dialog.exec():
            new_track = dialog.result_track()
            if new_track:
                from src.ui.commands import UpdateSubtitleTrackCommand
                old_track = self._create_track_from_whisper_backup()
                ctx.undo_stack.push(UpdateSubtitleTrackCommand(ctx.project, new_track, old_track))
                ctx.subtitle_panel.set_track(new_track)
                ctx.video_widget.set_subtitle_track(new_track)
                ctx.timeline.set_track(new_track)
                ctx.status_bar().showMessage(tr("Subtitles generated successfully"))
            self._whisper_preview_active = False
            self._whisper_original_segments = None
        else:
            self._whisper_dialog_cancelled = True
            self._restore_whisper_on_cancel()

    def on_generate_subtitles_from_timeline(self) -> None:
        """편집된 타임라인에서 자막 생성."""
        ctx = self.ctx
        if not ctx.project.video_clip_track or not ctx.project.video_clip_track.clips:
            QMessageBox.warning(ctx.window, tr("No Clips"), tr("Timeline is empty. Please add video clips first."))
            return
        if not find_ffmpeg():
            QMessageBox.critical(ctx.window, tr("FFmpeg Missing"),
                                 tr("FFmpeg is required for subtitle generation but was not found."))
            return
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QProgressDialog
        msg = tr(
            "This will generate subtitles based on the current edited timeline.\n\n"
            "1. Exporting edited audio (this may take a few moments)\n"
            "2. Transcribing with Whisper\n"
            "3. Replacing existing subtitles with new results\n\n"
            "Continue?"
        )
        if QMessageBox.question(ctx.window, tr("Generate from Timeline"), msg) != QMessageBox.StandardButton.Yes:
            return
        progress_dialog = QProgressDialog(tr("Exporting timeline audio..."), tr("Cancel"), 0, 100, ctx.window)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.show()
        audio_path = None
        try:
            from src.services.timeline_audio_exporter import export_timeline_audio
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            audio_path = Path(tmp.name)
            export_timeline_audio(ctx.project.video_clip_track, output_path=audio_path,
                                  on_progress=progress_dialog.setValue)
            if progress_dialog.wasCanceled():
                return
            from src.ui.dialogs.whisper_dialog import WhisperDialog
            dialog = WhisperDialog(audio_path=audio_path, parent=ctx.window)
            self._whisper_dialog_cancelled = False
            dialog.segment_ready.connect(self.on_whisper_segment_ready)
            if dialog.exec():
                new_track = dialog.result_track()
                if new_track:
                    from src.ui.commands import UpdateSubtitleTrackCommand
                    old_track = self._create_track_from_whisper_backup()
                    ctx.undo_stack.push(UpdateSubtitleTrackCommand(ctx.project, new_track, old_track))
                    ctx.subtitle_panel.set_track(new_track)
                    ctx.video_widget.set_subtitle_track(new_track)
                    ctx.timeline.set_track(new_track)
                    ctx.status_bar().showMessage(tr("Subtitles generated from timeline"))
                self._whisper_preview_active = False
                self._whisper_original_segments = None
            else:
                self._whisper_dialog_cancelled = True
                self._restore_whisper_on_cancel()
        except Exception as e:
            QMessageBox.critical(ctx.window, tr("Error"), f"Failed to generate subtitles: {str(e)}")
        finally:
            progress_dialog.close()
            if audio_path and audio_path.exists():
                try:
                    audio_path.unlink()
                except OSError:
                    pass

    def on_whisper_segment_ready(self, segment: SubtitleSegment) -> None:
        """Whisper 실시간 세그먼트 미리보기."""
        try:
            if self._whisper_dialog_cancelled:
                return
            ctx = self.ctx
            if not ctx.project:
                return
            if not (ctx.subtitle_panel and ctx.video_widget and ctx.timeline):
                return
            track = ctx.project.subtitle_track
            if not self._whisper_preview_active:
                self._whisper_preview_active = True
                self._whisper_original_segments = [
                    (s.start_ms, s.end_ms, s.text, s.style, s.audio_file, s.volume)
                    for s in track.segments
                ]
                track.clear()
            track.add_segment(segment)
            ctx.subtitle_panel.set_track(track)
            ctx.subtitle_panel.refresh()
            ctx.video_widget.set_subtitle_track(track)
            ctx.timeline.set_track(track)
            ctx.video_widget._update_subtitle(ctx.timeline.get_playhead())
            ctx.timeline.update()
        except RuntimeError:
            pass
        except Exception:
            import traceback
            traceback.print_exc()

    def _create_track_from_whisper_backup(self) -> SubtitleTrack | None:
        if self._whisper_original_segments is None:
            return None
        track = self.ctx.project.subtitle_track
        restored = SubtitleTrack(name=track.name, language=track.language)
        for t in self._whisper_original_segments:
            restored.add_segment(
                SubtitleSegment(start_ms=t[0], end_ms=t[1], text=t[2], style=t[3], audio_file=t[4], volume=t[5])
            )
        return restored

    def _restore_whisper_on_cancel(self) -> None:
        try:
            if not self._whisper_preview_active:
                return
            self._whisper_preview_active = False
            if self._whisper_original_segments is None:
                return
            ctx = self.ctx
            if not (ctx.project and ctx.subtitle_panel and ctx.video_widget and ctx.timeline):
                return
            track = ctx.project.subtitle_track
            track.clear()
            for t in self._whisper_original_segments:
                track.add_segment(
                    SubtitleSegment(start_ms=t[0], end_ms=t[1], text=t[2], style=t[3], audio_file=t[4], volume=t[5])
                )
            ctx.subtitle_panel.set_track(track)
            ctx.video_widget.set_subtitle_track(track)
            ctx.timeline.set_track(track)
            ctx.video_widget._update_subtitle(ctx.timeline.get_playhead())
            ctx.timeline.update()
        except RuntimeError:
            pass
        finally:
            self._whisper_original_segments = None

    # ---- TTS 생성 ----

    def on_generate_tts(self) -> None:
        ctx = self.ctx
        if not find_ffmpeg():
            QMessageBox.critical(ctx.window, tr("FFmpeg Missing"),
                                 tr("FFmpeg is required for TTS generation but was not found."))
            return
        video_audio_path = ctx.project.video_path if ctx.project.has_video else None
        from src.ui.dialogs.tts_dialog import TTSDialog
        dialog = TTSDialog(video_audio_path=video_audio_path, parent=ctx.window)
        if dialog.exec():
            track = dialog.result_track()
            audio_path = dialog.result_audio_path()
            if track and len(track) > 0:
                from src.services.audio_merger import AudioMerger
                track.name = f"{tr('TTS Track')} {len(ctx.project.subtitle_tracks)}"
                track.audio_path = audio_path
                try:
                    duration_sec = AudioMerger.get_audio_duration(Path(audio_path))
                    track.audio_duration_ms = int(duration_sec * 1000)
                    track.audio_start_ms = 0
                except Exception:
                    if len(track) > 0:
                        track.audio_duration_ms = track[-1].end_ms
                    track.audio_start_ms = 0
                ctx.project.subtitle_tracks.append(track)
                track_names = [t.name for t in ctx.project.subtitle_tracks]
                new_track_index = len(ctx.project.subtitle_tracks) - 1
                ctx.track_selector.set_tracks(track_names, new_track_index)
                ctx.project.active_track_index = new_track_index
                ctx.ensure_timeline_duration()
                ctx.refresh_all()
                ctx.status_bar().showMessage(
                    f"{tr('TTS generated')}: {len(track)} {tr('segments')}"
                )

    def on_play_tts_audio(self) -> None:
        ctx = self.ctx
        current_track = ctx.project.subtitle_track
        if not current_track or not current_track.audio_path:
            QMessageBox.information(
                ctx.window, tr("No TTS Audio"),
                tr("The current track doesn't have TTS audio.") + "\n\n"
                + tr("Generate TTS audio first (Ctrl+T).")
            )
            return
        audio_path = Path(current_track.audio_path)
        if not audio_path.exists():
            QMessageBox.warning(
                ctx.window, tr("Audio File Not Found"),
                f"{tr('TTS audio file not found')}:\n{audio_path}\n\n{tr('It may have been deleted.')}"
            )
            return
        if ctx.tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            ctx.tts_player.stop()
        ctx.tts_player.setSource(QUrl.fromLocalFile(str(audio_path)))
        ctx.tts_player.play()
        ctx.status_bar().showMessage(f"{tr('Playing TTS audio')}: {current_track.name}")

    def on_regenerate_audio(self) -> None:
        from src.services.audio_regenerator import AudioRegenerator
        ctx = self.ctx
        current_track = ctx.project.subtitle_track
        audio_segments = [seg for seg in current_track.segments if seg.audio_file]
        if not audio_segments:
            QMessageBox.information(
                ctx.window, tr("No Audio Segments"),
                tr("The current track doesn't have audio segments.") + "\n\n"
                + tr("Generate TTS audio first (Ctrl+T).")
            )
            return
        reply = QMessageBox.question(
            ctx.window, tr("Regenerate Audio?"),
            f"{tr('Regenerate merged audio based on current timeline positions?')}\n\n"
            f"{tr('This will create a new audio file with segments positioned according to the timeline.')}\n\n"
            f"{tr('Segments')}: {len(audio_segments)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            ctx.status_bar().showMessage(tr("Regenerating audio from timeline..."))
            QApplication.processEvents()
            from src.utils.config import APP_NAME
            import uuid
            user_data_dir = Path.home() / f".{APP_NAME.lower()}"
            user_data_dir.mkdir(parents=True, exist_ok=True)
            output_path = user_data_dir / f"tts_regen_{uuid.uuid4().hex[:8]}.mp3"
            video_audio_path = None
            if ctx.project.video_path and ctx.project.video_has_audio:
                video_audio_path = ctx.project.video_path
            regenerated_audio, total_duration_ms = AudioRegenerator.regenerate_track_audio(
                track=current_track, output_path=output_path,
                video_audio_path=video_audio_path, bg_volume=0.5, tts_volume=1.0
            )
            current_track.audio_path = str(regenerated_audio)
            current_track.audio_start_ms = 0
            current_track.audio_duration_ms = total_duration_ms
            ctx.ensure_timeline_duration()
            ctx.refresh_all()
            ctx.player.pause()
            ctx.tts_player.stop()
            ctx.video_widget.set_subtitle_track(current_track)
            current_pos = ctx.player.position()
            ctx.playback_ctrl.on_player_position_changed(current_pos)
            ctx.status_bar().showMessage(
                f"{tr('Audio regenerated')}: {len(audio_segments)} {tr('segments')}, "
                f"{total_duration_ms / 1000:.1f}s", 5000
            )
            QMessageBox.information(
                ctx.window, tr("Audio Regenerated"),
                f"{tr('Audio has been regenerated successfully!')}\n\n"
                f"{tr('Segments')}: {len(audio_segments)}\n"
                f"{tr('Duration')}: {total_duration_ms / 1000:.1f}s\n\n"
                f"{tr('Play to hear the updated audio.')}"
            )
        except Exception as e:
            QMessageBox.critical(ctx.window, tr("Regeneration Failed"),
                                 f"{tr('Failed to regenerate audio')}:\n\n{e}")
            ctx.status_bar().showMessage(tr("Audio regeneration failed"), 5000)

    # ---- 트랙 관리 ----

    def on_track_changed(self, index: int) -> None:
        ctx = self.ctx
        if 0 <= index < len(ctx.project.subtitle_tracks):
            ctx.project.active_track_index = index
            track = ctx.project.subtitle_track
            ctx.video_widget.set_subtitle_track(track if len(track) > 0 else None)
            ctx.subtitle_panel.set_track(track if len(track) > 0 else None)
            ctx.timeline.set_track(track if len(track) > 0 else None)
            ctx.undo_stack.clear()
            ctx.status_bar().showMessage(f"Switched to track: {track.name or f'Track {index + 1}'}")

    def on_track_added(self, name: str) -> None:
        ctx = self.ctx
        new_track = SubtitleTrack(name=name)
        ctx.project.subtitle_tracks.append(new_track)
        ctx.project.active_track_index = len(ctx.project.subtitle_tracks) - 1
        ctx.refresh_track_selector()
        self.on_track_changed(ctx.project.active_track_index)

    def on_track_removed(self, index: int) -> None:
        ctx = self.ctx
        if len(ctx.project.subtitle_tracks) <= 1:
            QMessageBox.warning(ctx.window, tr("Cannot Remove"), tr("At least one track must remain."))
            return
        if 0 <= index < len(ctx.project.subtitle_tracks):
            ctx.project.subtitle_tracks.pop(index)
            ctx.project.active_track_index = min(
                ctx.project.active_track_index, len(ctx.project.subtitle_tracks) - 1
            )
            ctx.refresh_track_selector()
            self.on_track_changed(ctx.project.active_track_index)

    def on_track_renamed(self, index: int, name: str) -> None:
        ctx = self.ctx
        if 0 <= index < len(ctx.project.subtitle_tracks):
            ctx.project.subtitle_tracks[index].name = name
            ctx.refresh_track_selector()

    # ---- 유틸리티 ----

    def apply_subtitle_track(self, track: SubtitleTrack) -> None:
        ctx = self.ctx
        ctx.project.subtitle_track = track
        ctx.undo_stack.clear()
        ctx.video_widget.set_subtitle_track(track)
        ctx.subtitle_panel.set_track(track)
        ctx.timeline.set_track(track)
        ctx.refresh_track_selector()
        ctx.status_bar().showMessage(f"{tr('Subtitles loaded')}: {len(track)} {tr('segments')}")

    def on_clear_subtitles(self) -> None:
        ctx = self.ctx
        ctx.project.subtitle_track = SubtitleTrack(name=ctx.project.subtitle_track.name)
        ctx.undo_stack.clear()
        ctx.video_widget.set_subtitle_track(None)
        ctx.subtitle_panel.set_track(None)
        ctx.timeline.set_track(None)
        ctx.status_bar().showMessage(tr("Subtitles cleared"))

    def on_translate_track(self) -> None:
        ctx = self.ctx
        if not ctx.project.has_subtitles:
            QMessageBox.warning(ctx.window, tr("No Subtitles"), tr("There are no subtitles to translate."))
            return
        available_langs = [
            "Korean", "English", "Japanese", "Chinese", "Spanish", "French",
            "German", "Russian", "Portuguese", "Italian", "Dutch"
        ]
        from src.ui.dialogs.translate_dialog import TranslateDialog
        dialog = TranslateDialog(ctx.project.subtitle_track, available_langs, ctx.window)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            translated_track = dialog.get_result_track()
            if translated_track:
                if dialog.is_new_track():
                    ctx.project.subtitle_tracks.append(translated_track)
                    ctx.project.active_track_index = len(ctx.project.subtitle_tracks) - 1
                    ctx.refresh_track_selector()
                    self.on_track_changed(ctx.project.active_track_index)
                    ctx.status_bar().showMessage(f"{tr('Added translated track')}: {translated_track.name}")
                else:
                    ctx.project.subtitle_track = translated_track
                    ctx.refresh_all()
                    ctx.status_bar().showMessage(tr("Track translated"))
                ctx.autosave.notify_edit()

    def on_delete_selected(self) -> None:
        """Delete selected subtitle segment or clip."""
        ctx = self.ctx
        rows = ctx.subtitle_panel._table.selectionModel().selectedRows()
        if rows:
            index = rows[0].row()
            self.on_segment_delete(index)
