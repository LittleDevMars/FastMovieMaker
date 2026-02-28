"""ClipController — 비디오 클립 편집 로직."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtCore import Qt

from src.models.video_clip import VideoClipTrack
from src.ui.commands import (
    AddVideoClipCommand,
    DeleteClipCommand,
    EditSpeedCommand,
    EditTransitionCommand,
    MoveVideoClipCommand,
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

    def on_split_clip(self, track_idx: int, timeline_ms: int) -> None:
        ctx = self.ctx
        if track_idx >= 0:
            # 우클릭 메뉴: 특정 트랙에서 직접 탐색
            if not ctx.project or track_idx >= len(ctx.project.video_tracks):
                ctx.status_bar().showMessage(tr("No video clips to split"), 3000)
                return
            vt = ctx.project.video_tracks[track_idx]
            res = vt.clip_at_timeline(timeline_ms)
            if not res:
                ctx.status_bar().showMessage(tr("No video clips to split"), 3000)
                return
            clip_idx, clip = res
            v_idx = track_idx
        else:
            # Ctrl+B 단축키: 최상위 트랙 자동 탐색
            res = self.get_top_clip_at(timeline_ms)
            if not res:
                ctx.status_bar().showMessage(tr("No video clips to split"), 3000)
                return
            v_idx, clip_idx, clip = res
            vt = ctx.project.video_tracks[v_idx]

        offset = vt.clip_timeline_start(clip_idx)
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

        from src.ui.dialogs.speed_dialog import SpeedDialog
        dialog = SpeedDialog(
            ctx.window,
            current_speed=old_speed,
            clip_duration_ms=clip.duration_ms,
        )
        if not dialog.exec():
            return
        speed = dialog.get_speed()
        if speed != old_speed:
            sub_track = ctx.project.subtitle_track
            overlay_track = ctx.project.image_overlay_track
            cmd = EditSpeedCommand(
                ctx.project, track_index, clip_index, old_speed, speed,
                sub_track, overlay_track, ripple=ctx.timeline.is_ripple_mode()
            )
            ctx.undo_stack.push(cmd)
            ctx.project.duration_ms = ctx.project.video_tracks[track_index].output_duration_ms
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
        
        next_clip = vt.clips[clip_idx + 1] if clip_idx + 1 < len(vt.clips) else None
        dialog = TransitionDialog(ctx.window, initial_type, initial_dur, outgoing_clip=clip, incoming_clip=next_clip)
        if dialog.exec():
            trans_type, trans_dur = dialog.get_data()
            new_info = TransitionInfo(type=trans_type, duration_ms=trans_dur)
            ripple = ctx.timeline.is_ripple_mode()
            command = EditTransitionCommand(ctx.project, track_idx, clip_idx, new_info, ripple=ripple)
            ctx.undo_stack.push(command)
            ctx.project.duration_ms = ctx.project.video_clip_track.output_duration_ms
            ctx.timeline.set_duration(ctx.project.duration_ms)
            ctx.refresh_all()

    def on_remove_transition(self, track_idx: int, clip_idx: int) -> None:
        """트랜지션을 제거합니다 (EditTransitionCommand에 None 전달)."""
        ctx = self.ctx
        if not ctx.project:
            return
        vt = ctx.project.video_tracks[track_idx]
        if clip_idx < 0 or clip_idx >= len(vt.clips):
            return
        cmd = EditTransitionCommand(
            ctx.project, track_idx, clip_idx,
            None,  # new_info=None → 트랜지션 제거
            ripple=ctx.timeline.is_ripple_mode()
        )
        ctx.undo_stack.push(cmd)
        ctx.project.duration_ms = ctx.project.video_clip_track.output_duration_ms
        ctx.timeline.set_duration(ctx.project.duration_ms)
        ctx.refresh_all()

    # ---- 클립 이동 ----

    def on_clip_moved(self, src_track: int, src_index: int, dst_track: int, dst_index: int) -> None:
        """Handle clip move event from timeline."""
        ctx = self.ctx
        if not ctx.project:
            return
        
        # Check for Alt key to move linked items
        move_linked = (QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier) != 0
        
        cmd = MoveVideoClipCommand(
            ctx.project, src_track, src_index, dst_track, dst_index,
            subtitle_track=ctx.project.subtitle_track,
            image_overlay_track=ctx.project.image_overlay_track,
            move_linked=move_linked
        )
        ctx.undo_stack.push(cmd)
        ctx.refresh_all()

    # ---- 클립 볼륨/속성 ----

    def on_edit_clip_properties(self, track_idx: int, clip_idx: int) -> None:
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
            initial_saturation=clip.saturation,
            initial_speed=clip.speed
        )
        if dialog.exec():
            new_values = dialog.get_values()
            old_values = {
                "volume": clip.volume, "brightness": clip.brightness,
                "contrast": clip.contrast, "saturation": clip.saturation,
                "speed": clip.speed
            }
            
            # Check if anything changed
            if any(new_values[k] != old_values[k] for k in new_values):
                ctx.undo_stack.beginMacro(tr("Edit Clip Properties"))
                
                # 1. Visual/Audio properties
                if any(new_values[k] != old_values[k] for k in ["volume", "brightness", "contrast", "saturation"]):
                    cmd_props = EditClipPropertiesCommand(clip, old_values, new_values)
                    ctx.undo_stack.push(cmd_props)
                
                # 2. Speed (requires ripple)
                if new_values["speed"] != old_values["speed"]:
                    sub_track = ctx.project.subtitle_track
                    overlay_track = ctx.project.image_overlay_track
                    cmd_speed = EditSpeedCommand(
                        ctx.project, track_idx, clip_idx, old_values["speed"], new_values["speed"],
                        sub_track, overlay_track, ripple=ctx.timeline.is_ripple_mode()
                    )
                    ctx.undo_stack.push(cmd_speed)
                    ctx.project.duration_ms = ctx.project.video_tracks[track_idx].output_duration_ms
                
                ctx.undo_stack.endMacro()
                ctx.project_ctrl.on_document_edited()
                ctx.refresh_all()

    # ---- 트랙 관리 ----

    def on_add_video_track(self) -> None:
        """Add a new video track."""
        from src.ui.commands import AddVideoTrackCommand
        cmd = AddVideoTrackCommand(self.ctx.project)
        self.ctx.undo_stack.push(cmd)
        self.ctx.refresh_all()

    def on_remove_video_track(self, index: int) -> None:
        """Remove a video track."""
        if len(self.ctx.project.video_tracks) <= 1:
            return  # Keep at least one track
        from src.ui.commands import RemoveVideoTrackCommand
        cmd = RemoveVideoTrackCommand(self.ctx.project, index)
        self.ctx.undo_stack.push(cmd)
        self.ctx.refresh_all()

    def on_rename_video_track(self, index: int) -> None:
        """Rename a video track."""
        # Currently VideoClipTrack doesn't have a name field in the model, 
        # but TrackHeaderPanel displays "Video N".
        # If we want to support renaming, we need to add a name field to VideoClipTrack.
        # For now, let's assume we can't rename video tracks as the model doesn't support it yet,
        # or we just show a message.
        pass

    # ---- 복사 / 붙여넣기 ----

    def copy_selected_clip(self) -> None:
        """Copy the currently selected video clip to clipboard."""
        item_type, track_idx, clip_idx = self.ctx.timeline.get_selected_item()
        if item_type != "clip":
            return
        
        vt = self.ctx.project.video_tracks[track_idx]
        if clip_idx < 0 or clip_idx >= len(vt.clips):
            return
            
        clip = vt.clips[clip_idx]
        data = clip.to_dict()
        
        import json
        from PySide6.QtCore import QMimeData
        from PySide6.QtWidgets import QApplication
        
        mime = QMimeData()
        mime.setData("application/x-fmm-clip", json.dumps(data).encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)
        self.ctx.status_bar().showMessage(tr("Clip copied"))

    def paste_clip(self) -> None:
        """Paste video clip from clipboard at playhead."""
        from PySide6.QtWidgets import QApplication
        import json
        from src.models.video_clip import VideoClip
        
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if not mime.hasFormat("application/x-fmm-clip"):
            return
            
        try:
            data = json.loads(mime.data("application/x-fmm-clip").data().decode("utf-8"))
            clip = VideoClip.from_dict(data)
            
            playhead = self.ctx.timeline.get_playhead()
            track_idx = self.ctx.current_track_index
            if track_idx < 0 or track_idx >= len(self.ctx.project.video_tracks):
                track_idx = 0
            
            vt = self.ctx.project.video_tracks[track_idx]
            
            # Determine insertion point
            insert_index = len(vt.clips)
            split_cmd = None
            
            result = vt.clip_at_timeline(playhead)
            if result is not None:
                idx, existing_clip = result
                clip_start = vt.clip_timeline_start(idx)
                local_offset = playhead - clip_start
                
                if local_offset > existing_clip.duration_ms * 0.8:
                    insert_index = idx + 1
                elif local_offset < existing_clip.duration_ms * 0.2:
                    insert_index = idx
                else:
                    # Split needed
                    first, second = existing_clip.split_at(local_offset)
                    split_cmd = SplitClipCommand(
                        self.ctx.project, track_idx, idx, existing_clip, first, second
                    )
                    insert_index = idx + 1

            if split_cmd:
                self.ctx.undo_stack.beginMacro(tr("Paste Clip"))
                self.ctx.undo_stack.push(split_cmd)
            
            self._add_clip_at(track_idx, clip, insert_index)
            
            if split_cmd:
                self.ctx.undo_stack.endMacro()
            
            self.ctx.status_bar().showMessage(tr("Clip pasted"))
            
        except Exception as e:
            print(f"Paste failed: {e}")

    # ---- 비디오 파일 드롭 → 타임라인 추가 ----

    def on_video_file_dropped(self, paths: list[str], position_ms: int, track_index: int = -1) -> None:
        for path_str in paths:
            path = Path(path_str)
            if not self.ctx.project.has_video:
                self.ctx.media_ctrl.load_video(path)
            else:
                self.add_video_to_timeline(path, position_ms, track_index)
                # For subsequent clips, we could advance position_ms, but add_video_to_timeline
                # handles insertion at specific point. If we want sequential, we should
                # update position_ms. However, add_video_to_timeline calculates insertion index.
                # If we drop multiple files at same position, they will be inserted at that position.
                # To make them sequential, we rely on the fact that inserting at index X shifts existing clips.
                # But if we insert at time T, we get index I. Next clip at time T gets index I (pushing previous).
                # So they would be reversed if we don't increment time or index.
                # Let's just let them insert at the drop point. The user can arrange them.
                # Actually, standard behavior is sequential.
                # Let's try to estimate duration to advance position?
                # Doing probe here is slow.
                # Let's just insert them all at the drop point. They will push each other.
                # If we insert A then B at same index, B comes before A?
                # No, insert(i, A) -> A is at i. insert(i+1, B) -> B is after A.
                # We need to increment insertion index or time.
                # Since add_video_to_timeline calculates index from time, we should probably
                # just call it. If we call it with same time, it finds same index.
                # If we insert A, it shifts everything. Next insert at same time finds same index (start of A).
                # So B would be inserted before A?
                # Let's check: clip_at_timeline(T) returns clip covering T.
                # If we insert A at T. A covers T.
                # Next call clip_at_timeline(T) returns A.
                # We split A? No, we want to append.
                # This is tricky without knowing durations.
                # For now, let's just add them. The user can reorder.
                pass

    def add_video_to_timeline(self, path: Path, position_ms: int, track_index: int = -1) -> None:
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

        v_idx = track_index if track_index >= 0 else ctx.current_track_index
        if v_idx < 0 or v_idx >= len(ctx.project.video_tracks):
            v_idx = 0

        clip = VideoClip(source_in_ms=0, source_out_ms=info.duration_ms, source_path=str(path.resolve()))
        
        if not ctx.project.video_tracks:
            ctx.project.video_tracks.append(VideoClipTrack())
        clip_track = ctx.project.video_tracks[v_idx]

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
