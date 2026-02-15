"""ClipController — 비디오 클립 편집 로직."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QInputDialog, QMessageBox

from src.models.video_clip import VideoClipTrack
from src.ui.commands import (
    AddVideoClipCommand,
    DeleteClipCommand,
    EditSpeedCommand,
    EditTransitionCommand,
    SplitClipCommand,
    TrimClipCommand,
)
from src.utils.i18n import tr

if TYPE_CHECKING:
    from src.models.video_clip import VideoClip
    from src.ui.controllers.app_context import AppContext


class ClipController:
    """비디오 클립 분할/삭제/트림/속도/트랜지션 Controller."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # ---- 클립 인덱스 동기화 ----

    def sync_clip_index_from_position(self) -> None:
        """Recalculate current track and clip index from timeline position."""
        res = self.get_top_clip_at(self.ctx.timeline.get_playhead())
        if res:
            self.ctx.current_track_index, self.ctx.current_clip_index, _ = res

    def get_top_clip_at(self, timeline_ms: int) -> tuple[int, int, VideoClip] | None:
        """Find the clip on the highest visible track at the given timeline position."""
        ctx = self.ctx
        if not ctx.project:
            return None
        for v_idx in reversed(range(len(ctx.project.video_tracks))):
            vt = ctx.project.video_tracks[v_idx]
            if vt.hidden:
                continue
            res = vt.clip_at_timeline(timeline_ms)
            if res:
                return v_idx, res[0], res[1]
        return None

    # ---- 클립 선택 ----

    def on_clip_selected(self, track_index: int, clip_index: int) -> None:
        self.ctx.timeline.select_clip(track_index, clip_index)

    # ---- 클립 분할 ----

    def on_split_clip(self, timeline_ms: int) -> None:
        ctx = self.ctx
        res = self.get_top_clip_at(timeline_ms)
        if not res:
            ctx.status_bar().showMessage(tr("No video clips to split"), 3000)
            return

        v_idx, clip_idx, clip = res
        vt = ctx.project.video_tracks[v_idx]
        offset = sum(c.duration_ms for c in vt.clips[:clip_idx])
        local_ms = timeline_ms - offset
        split_source = clip.source_in_ms + int(local_ms * clip.speed)

        if split_source <= clip.source_in_ms + 100 or split_source >= clip.source_out_ms - 100:
            ctx.status_bar().showMessage(tr("Cannot split: too close to clip edge"), 3000)
            return

        was_playing = ctx.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if was_playing:
            ctx.player.pause()

        original = clip
        first, second = clip.split_at(local_ms)
        cmd = SplitClipCommand(ctx.project, v_idx, clip_idx, original, first, second)
        ctx.undo_stack.push(cmd)

        ctx.refresh_all()
        self.sync_clip_index_from_position()
        ctx.timeline.select_clip(v_idx, clip_idx + 1)

        if was_playing:
            ctx.player.play()
        ctx.status_bar().showMessage(f"{tr('Split clip')} {clip_idx + 1} at {timeline_ms}ms", 3000)

    # ---- 클립 삭제 ----

    def on_delete_clip(self, track_index: int, clip_index: int) -> None:
        ctx = self.ctx
        if not ctx.project or track_index >= len(ctx.project.video_tracks):
            return
        vt = ctx.project.video_tracks[track_index]
        if clip_index < 0 or clip_index >= len(vt.clips):
            return
        if len(vt.clips) <= 1 and len(ctx.project.video_tracks) == 1:
            ctx.status_bar().showMessage(tr("Cannot delete the last clip"), 3000)
            return

        clip = vt.clips[clip_index]
        clip_start_tl = sum(c.duration_ms for c in vt.clips[:clip_index])
        clip_end_tl = clip_start_tl + clip.duration_ms

        ctx.player.pause()
        sub_track = ctx.project.subtitle_track
        overlay_track = ctx.project.image_overlay_track
        cmd = DeleteClipCommand(
            ctx.project, track_index, clip_index, clip, sub_track, overlay_track,
            clip_start_tl, clip_end_tl, ripple=ctx.timeline.is_ripple_mode()
        )
        ctx.undo_stack.push(cmd)
        ctx.timeline.select_clip(-1, -1)
        ctx.project.duration_ms = ctx.project.video_tracks[track_index].output_duration_ms

        ctx.current_clip_index = -1
        ctx.current_playback_source = None

        safe_pos = 0
        if len(vt.clips) > 0:
            if clip_index == 0:
                safe_pos = 0
            elif clip_index < len(vt.clips):
                safe_pos = sum(c.duration_ms for c in vt.clips[:clip_index])
            else:
                safe_pos = sum(c.duration_ms for c in vt.clips[:clip_index - 1])

        ctx.timeline.set_playhead(safe_pos)
        ctx.controls.set_output_position(safe_pos)

        if len(vt.clips) > 0:
            first_clip = vt.clips[0]
            first_source = first_clip.source_path or str(ctx.project.video_path)
            if first_source != ctx.current_playback_source:
                ctx.media_ctrl.switch_player_source(first_source, first_clip.source_in_ms, auto_play=False)
            else:
                ctx.player.setPosition(first_clip.source_in_ms)
            ctx.current_clip_index = 0

        ctx.refresh_all()
        ctx.status_bar().showMessage(f"{tr('Deleted clip')} {clip_index + 1}", 3000)

    # ---- 클립 트림 ----

    def on_clip_trimmed(self, track_index: int, clip_index: int, new_source_in: int, new_source_out: int) -> None:
        ctx = self.ctx
        if not ctx.project or track_index >= len(ctx.project.video_tracks):
            return
        vt = ctx.project.video_tracks[track_index]
        if clip_index < 0 or clip_index >= len(vt.clips):
            return

        clip = vt.clips[clip_index]
        old_in = clip.source_in_ms
        old_out = clip.source_out_ms
        sub_track = ctx.project.subtitle_track
        overlay_track = ctx.project.image_overlay_track
        cmd = TrimClipCommand(
            ctx.project, track_index, clip_index, old_in, old_out, new_source_in, new_source_out,
            sub_track, overlay_track, ripple=ctx.timeline.is_ripple_mode()
        )
        ctx.undo_stack.push(cmd)
        ctx.project.duration_ms = ctx.project.video_tracks[track_index].output_duration_ms
        ctx.refresh_all()

    # ---- 클립 속도 ----

    def on_edit_clip_speed(self, track_index: int, clip_index: int) -> None:
        ctx = self.ctx
        if not ctx.project or track_index >= len(ctx.project.video_tracks):
            return
        vt = ctx.project.video_tracks[track_index]
        if clip_index < 0 or clip_index >= len(vt.clips):
            return
        clip = vt.clips[clip_index]
        old_speed = clip.speed
        speed, ok = QInputDialog.getDouble(
            ctx.window, tr("Clip Speed"), tr("Speed (0.25x - 4.0x):"),
            old_speed, 0.25, 4.0, 2
        )
        if ok and speed != old_speed:
            sub_track = ctx.project.subtitle_track
            overlay_track = ctx.project.image_overlay_track
            cmd = EditSpeedCommand(
                ctx.project, track_index, clip_index, old_speed, speed,
                sub_track, overlay_track, ripple=ctx.timeline.is_ripple_mode()
            )
            ctx.undo_stack.push(cmd)
            ctx.refresh_all()

    # ---- 트랜지션 ----

    def on_transition_requested(self, track_idx: int, clip_idx: int) -> None:
        ctx = self.ctx
        if not ctx.project:
            return
        vt = ctx.project.video_tracks[track_idx]
        if clip_idx < 0 or clip_idx >= len(vt.clips):
            return
        clip = vt.clips[clip_idx]
        from src.models.video_clip import TransitionInfo
        from src.ui.dialogs.transition_dialog import TransitionDialog
        initial_type = clip.transition_out.type if clip.transition_out else "fade"
        initial_dur = clip.transition_out.duration_ms if clip.transition_out else 500
        dialog = TransitionDialog(ctx.window, initial_type, initial_dur)
        if dialog.exec():
            trans_type, trans_dur = dialog.get_data()
            new_info = TransitionInfo(type=trans_type, duration_ms=trans_dur)
            ripple = ctx.timeline.is_ripple_mode()
            command = EditTransitionCommand(ctx.project, track_idx, clip_idx, new_info, ripple=ripple)
            ctx.undo_stack.push(command)
            ctx.project.duration_ms = ctx.project.video_clip_track.output_duration_ms
            ctx.timeline.set_duration(ctx.project.duration_ms)
            ctx.refresh_all()

    # ---- 클립 볼륨/속성 ----

    def on_clip_volume_requested(self, track_idx: int, clip_idx: int) -> None:
        ctx = self.ctx
        if not ctx.project:
            return
        from src.ui.dialogs.clip_properties_dialog import ClipPropertiesDialog
        from src.ui.commands import EditClipPropertiesCommand
        vt = ctx.project.video_tracks[track_idx]
        clip = vt.clips[clip_idx]
        dialog = ClipPropertiesDialog(
            ctx.window,
            initial_volume=clip.volume,
            initial_brightness=clip.brightness,
            initial_contrast=clip.contrast,
            initial_saturation=clip.saturation
        )
        if dialog.exec():
            new_values = dialog.get_values()
            old_values = {
                "volume": clip.volume, "brightness": clip.brightness,
                "contrast": clip.contrast, "saturation": clip.saturation,
            }
            if any(new_values[k] != old_values[k] for k in new_values):
                cmd = EditClipPropertiesCommand(clip, old_values, new_values)
                ctx.undo_stack.push(cmd)
                ctx.project_ctrl.on_document_edited()
                ctx.refresh_all()

    # ---- 비디오 파일 드롭 → 타임라인 추가 ----

    def on_video_file_dropped(self, path_str: str, position_ms: int) -> None:
        path = Path(path_str)
        if not self.ctx.project.has_video:
            self.ctx.media_ctrl.load_video(path)
        else:
            self.add_video_to_timeline(path, position_ms)

    def add_video_to_timeline(self, path: Path, position_ms: int) -> None:
        """외부 비디오 파일을 클립으로 추가."""
        from src.models.video_clip import VideoClip
        from src.services.video_probe import probe_video
        ctx = self.ctx

        info = probe_video(path)
        if info.duration_ms <= 0:
            QMessageBox.warning(
                ctx.window, tr("Error"),
                tr("Could not read video duration.") + f"\n{path.name}",
            )
            return

        clip = VideoClip(source_in_ms=0, source_out_ms=info.duration_ms, source_path=str(path.resolve()))
        clip_track = ctx.project.video_clip_track
        if clip_track is None:
            if ctx.project.video_path and ctx.project.duration_ms > 0:
                clip_track = VideoClipTrack.from_full_video(ctx.project.duration_ms)
                ctx.project.video_clip_track = clip_track
            else:
                return

        result = clip_track.clip_at_timeline(position_ms)
        if result is not None:
            idx, existing_clip = result
            clip_start = clip_track.clip_timeline_start(idx)
            local_offset = position_ms - clip_start
            if local_offset > existing_clip.duration_ms * 0.8:
                insert_index = idx + 1
            elif local_offset < existing_clip.duration_ms * 0.2:
                insert_index = idx
            else:
                from src.models.video_clip import VideoClip as VC
                source_split = existing_clip.source_in_ms + local_offset
                first = VC(existing_clip.source_in_ms, source_split, source_path=existing_clip.source_path)
                second = VC(source_split, existing_clip.source_out_ms, source_path=existing_clip.source_path)
                clip_track.clips[idx] = first
                clip_track.clips.insert(idx + 1, second)
                insert_index = idx + 1
        else:
            insert_index = len(clip_track.clips)

        sub_track = ctx.project.subtitle_track
        overlay_track = ctx.project.image_overlay_track
        v_idx = ctx.current_track_index
        cmd = AddVideoClipCommand(
            ctx.project, v_idx, clip, sub_track, overlay_track, insert_index,
            ripple=ctx.timeline.is_ripple_mode()
        )
        ctx.undo_stack.push(cmd)

        if ctx.use_proxies:
            ctx.media_ctrl.start_proxy_generation(path)

        ctx.project.duration_ms = ctx.project.video_tracks[v_idx].output_duration_ms
        ctx.timeline.set_duration(ctx.project.duration_ms, has_video=True)
        ctx.timeline.set_clip_track(ctx.project.video_tracks[v_idx])
        ctx.timeline.refresh()
        ctx.controls.set_output_duration(ctx.project.duration_ms)
        ctx.autosave.notify_edit()
        ctx.status_bar().showMessage(
            f"{tr('Added video clip')}: {path.name} ({info.duration_ms // 1000}s)"
        )
        ctx.media_ctrl.start_frame_cache_generation()

        current_timeline_pos = ctx.timeline.get_playhead()
        if current_timeline_pos == 0 or not ctx.current_playback_source:
            ctx.playback_ctrl.on_timeline_seek(0)
        else:
            ctx.playback_ctrl.on_timeline_seek(current_timeline_pos)
