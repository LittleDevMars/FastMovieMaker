"""QUndoCommand subclasses for subtitle and video clip editing operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand
from src.utils.i18n import tr

if TYPE_CHECKING:
    from src.models.project import ProjectState
    from src.models.style import SubtitleStyle
    from src.models.subtitle import SubtitleSegment, SubtitleTrack
    from src.models.video_clip import VideoClip, VideoClipTrack
    from src.models.video_clip import VideoClipTrack  # Runtime import for AddVideoTrackCommand
    from src.models.image_overlay import ImageOverlay, ImageOverlayTrack
    from src.models.text_overlay import TextOverlay, TextOverlayTrack
    from src.models.audio import AudioClip, AudioTrack


class EditTextCommand(QUndoCommand):
    """Change the text of a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int, old_text: str, new_text: str):
        super().__init__(f"Edit text (segment {index + 1})")
        self._track = track
        self._index = index
        self._old_text = old_text
        self._new_text = new_text

    def redo(self) -> None:
        self._track.update_segment_text(self._index, self._new_text)

    def undo(self) -> None:
        self._track.update_segment_text(self._index, self._old_text)


class EditTimeCommand(QUndoCommand):
    """Change the start/end times of a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int,
                 old_start: int, old_end: int, new_start: int, new_end: int):
        super().__init__(f"Edit time (segment {index + 1})")
        self._track = track
        self._index = index
        self._old_start = old_start
        self._old_end = old_end
        self._new_start = new_start
        self._new_end = new_end

    def redo(self) -> None:
        self._track.update_segment_time(self._index, self._new_start, self._new_end)

    def undo(self) -> None:
        self._track.update_segment_time(self._index, self._old_start, self._old_end)


class AddSegmentCommand(QUndoCommand):
    """Add a new subtitle segment."""

    def __init__(self, track: SubtitleTrack, segment: SubtitleSegment):
        super().__init__("Add subtitle")
        self._track = track
        self._segment = segment

    def redo(self) -> None:
        self._track.add_segment(self._segment)

    def undo(self) -> None:
        # Find and remove the segment by identity
        for i, seg in enumerate(self._track.segments):
            if seg is self._segment:
                self._track.segments.pop(i)
                break


class DeleteSegmentCommand(QUndoCommand):
    """Delete a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int, segment: SubtitleSegment):
        super().__init__(f"Delete subtitle (segment {index + 1})")
        self._track = track
        self._index = index
        self._segment = segment

    def redo(self) -> None:
        self._track.remove_segment(self._index)

    def undo(self) -> None:
        self._track.segments.insert(self._index, self._segment)
        self._track.segments.sort(key=lambda s: s.start_ms)


class MoveSegmentCommand(QUndoCommand):
    """Move a subtitle segment (change start/end via timeline drag)."""

    def __init__(self, track: SubtitleTrack, index: int,
                 old_start: int, old_end: int, new_start: int, new_end: int):
        super().__init__(f"Move segment {index + 1}")
        self._track = track
        self._index = index
        self._old_start = old_start
        self._old_end = old_end
        self._new_start = new_start
        self._new_end = new_end

    def redo(self) -> None:
        self._track.update_segment_time(self._index, self._new_start, self._new_end)

    def undo(self) -> None:
        self._track.update_segment_time(self._index, self._old_start, self._old_end)


class EditStyleCommand(QUndoCommand):
    """Change the style of a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int,
                 old_style: SubtitleStyle | None, new_style: SubtitleStyle | None):
        super().__init__(f"Edit style (segment {index + 1})")
        self._track = track
        self._index = index
        self._old_style = old_style
        self._new_style = new_style

    def redo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].style = self._new_style

    def undo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].style = self._old_style


class EditAnimationCommand(QUndoCommand):
    """Change the animation of a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int,
                 old_anim, new_anim):
        super().__init__(tr("Edit animation"))
        self._track = track
        self._index = index
        self._old = old_anim
        self._new = new_anim

    def redo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].animation = self._new

    def undo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].animation = self._old


class SplitCommand(QUndoCommand):
    """Split a subtitle segment at a given time position."""

    def __init__(self, track: SubtitleTrack, index: int,
                 split_ms: int, original: SubtitleSegment,
                 first: SubtitleSegment, second: SubtitleSegment):
        super().__init__(f"Split segment {index + 1}")
        self._track = track
        self._index = index
        self._original = original
        self._first = first
        self._second = second

    def redo(self) -> None:
        # Remove original, insert two parts
        if self._index < len(self._track.segments):
            self._track.segments.pop(self._index)
        self._track.segments.insert(self._index, self._second)
        self._track.segments.insert(self._index, self._first)

    def undo(self) -> None:
        # Remove the two parts, restore original
        # Find first by identity
        for i, seg in enumerate(self._track.segments):
            if seg is self._first:
                self._track.segments.pop(i)
                break
        for i, seg in enumerate(self._track.segments):
            if seg is self._second:
                self._track.segments.pop(i)
                break
        self._track.segments.insert(self._index, self._original)
        self._track.segments.sort(key=lambda s: s.start_ms)


class MergeCommand(QUndoCommand):
    """Merge two consecutive subtitle segments."""

    def __init__(self, track: SubtitleTrack, index: int,
                 first: SubtitleSegment, second: SubtitleSegment,
                 merged: SubtitleSegment):
        super().__init__(f"Merge segments {index + 1}-{index + 2}")
        self._track = track
        self._index = index
        self._first = first
        self._second = second
        self._merged = merged

    def redo(self) -> None:
        # Remove two segments (second first to preserve index)
        if self._index + 1 < len(self._track.segments):
            self._track.segments.pop(self._index + 1)
        if self._index < len(self._track.segments):
            self._track.segments.pop(self._index)
        self._track.segments.insert(self._index, self._merged)

    def undo(self) -> None:
        for i, seg in enumerate(self._track.segments):
            if seg is self._merged:
                self._track.segments.pop(i)
                break
        self._track.segments.insert(self._index, self._first)
        self._track.segments.insert(self._index + 1, self._second)
        self._track.segments.sort(key=lambda s: s.start_ms)


class EditVolumeCommand(QUndoCommand):
    """Change the volume of a subtitle segment."""

    def __init__(self, track: SubtitleTrack, index: int,
                 old_volume: float, new_volume: float):
        super().__init__(f"Edit volume (segment {index + 1})")
        self._track = track
        self._index = index
        self._old_volume = old_volume
        self._new_volume = new_volume

    def redo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].volume = self._new_volume

    def undo(self) -> None:
        if 0 <= self._index < len(self._track):
            self._track[self._index].volume = self._old_volume

class EditSegmentTTSCommand(QUndoCommand):
    """Update TTS audio, voice, and speed for a segment."""

    def __init__(self, track: SubtitleTrack, index: int, segment: SubtitleSegment, 
                 new_audio_file: str | None, new_voice: str | None, new_speed: float | None):
        super().__init__(f"Edit TTS (segment {index + 1})")
        self._track = track
        self._index = index
        self._old_audio = segment.audio_file
        self._old_voice = segment.voice
        self._old_speed = segment.speed
        self._new_audio = new_audio_file
        self._new_voice = new_voice
        self._new_speed = new_speed

    def redo(self) -> None:
        if 0 <= self._index < len(self._track):
            seg = self._track[self._index]
            seg.audio_file = self._new_audio
            seg.voice = self._new_voice
            seg.speed = self._new_speed

    def undo(self) -> None:
        if 0 <= self._index < len(self._track):
            seg = self._track[self._index]
            seg.audio_file = self._old_audio
            seg.voice = self._old_voice
            seg.speed = self._old_speed


class UpdateSubtitleTrackCommand(QUndoCommand):
    """Replace the active subtitle track (e.g. after Whisper/TTS generation)."""

    def __init__(self, project: ProjectState, new_track: SubtitleTrack, old_track: SubtitleTrack | None = None):
        super().__init__(tr("Update subtitles"))
        self._project = project
        self._new_track = new_track
        self._old_track = old_track
        if self._old_track is None:
            idx = project.active_track_index
            if 0 <= idx < len(project.subtitle_tracks):
                self._old_track = project.subtitle_tracks[idx]

    def redo(self) -> None:
        if 0 <= self._project.active_track_index < len(self._project.subtitle_tracks):
            self._project.subtitle_tracks[self._project.active_track_index] = self._new_track

    def undo(self) -> None:
        if self._old_track is not None and 0 <= self._project.active_track_index < len(self._project.subtitle_tracks):
            self._project.subtitle_tracks[self._project.active_track_index] = self._old_track


class BatchShiftCommand(QUndoCommand):
    """Shift all subtitle times by a given offset."""

    def __init__(self, track: SubtitleTrack, offset_ms: int):
        super().__init__(f"Batch shift {'+'if offset_ms >= 0 else ''}{offset_ms}ms")
        self._track = track
        self._offset_ms = offset_ms

    def redo(self) -> None:
        for seg in self._track.segments:
            seg.start_ms = max(0, seg.start_ms + self._offset_ms)
            seg.end_ms = max(seg.start_ms + 1, seg.end_ms + self._offset_ms)

    def undo(self) -> None:
        for seg in self._track.segments:
            seg.start_ms = max(0, seg.start_ms - self._offset_ms)
            seg.end_ms = max(seg.start_ms + 1, seg.end_ms - self._offset_ms)


# ------------------------------------------------------------------ Video clip commands


class SplitClipCommand(QUndoCommand):
    """Split a video clip into two at a given point on a specific track."""

    def __init__(self, project: ProjectState, track_index: int, clip_index: int,
                 original: VideoClip, first: VideoClip, second: VideoClip):
        super().__init__(f"Split clip {clip_index + 1} on track {track_index + 1}")
        self._project = project
        self._track_index = track_index
        self._index = clip_index
        self._original = original
        self._first = first
        self._second = second

    def redo(self) -> None:
        vt = self._project.video_tracks[self._track_index]
        vt.clips.pop(self._index)
        vt.clips.insert(self._index, self._second)
        vt.clips.insert(self._index, self._first)

    def undo(self) -> None:
        vt = self._project.video_tracks[self._track_index]
        for i, c in enumerate(vt.clips):
            if c is self._first:
                vt.clips.pop(i)
                break
        for i, c in enumerate(vt.clips):
            if c is self._second:
                vt.clips.pop(i)
                break
        vt.clips.insert(self._index, self._original)


class DeleteClipCommand(QUndoCommand):
    """Delete a video clip with subtitle ripple."""

    def __init__(self, project: ProjectState, track_index: int, clip_index: int,
                 removed_clip: VideoClip,
                 subtitle_track: SubtitleTrack,
                 image_overlay_track: ImageOverlayTrack | None,
                 clip_start_tl: int, clip_end_tl: int,
                 ripple: bool = True):
        super().__init__(f"Delete clip {clip_index + 1} on track {track_index + 1}")
        self._project = project
        self._track_index = track_index
        self._clip_index = clip_index
        self._removed_clip = removed_clip
        self._sub_track = subtitle_track
        self._overlay_track = image_overlay_track
        self._clip_start = clip_start_tl
        self._clip_end = clip_end_tl
        self._shift = removed_clip.duration_ms
        self._ripple = ripple

        # Snapshot of affected subtitles for undo
        self._removed_subs: list[tuple[int, SubtitleSegment]] = []
        self._truncated_subs: list[tuple[int, int, int]] = []  # (seg_index, old_start, old_end)
        self._shifted_subs: list[tuple[int, int, int]] = []    # (seg_index, old_start, old_end)
        
        # Snapshot of affected overlays for undo
        self._removed_overlays: list[tuple[int, ImageOverlay]] = []
        self._truncated_overlays: list[tuple[int, int, int]] = []
        self._shifted_overlays: list[tuple[int, int, int]] = []

        # Snapshot of affected audio track (for undo when TTS invalidated)
        self._old_audio_start = subtitle_track.audio_start_ms
        self._old_audio_duration = subtitle_track.audio_duration_ms
        self._old_audio_path = getattr(subtitle_track, "audio_path", "") or ""

        # Snapshot for BGM and text overlay ripple (undo support)
        self._shifted_bgm: list[tuple[int, int, int]] = []    # (track_idx, clip_idx, old_start)
        self._shifted_text: list[tuple[int, int, int]] = []   # (ov_idx, old_start, old_end)

    def redo(self) -> None:
        # 1. Remove the clip
        vt = self._project.video_tracks[self._track_index]
        vt.clips.pop(self._clip_index)

        if not self._ripple:
             return
        # ... (rest stays same, using _sub_track and _overlay_track)

        # 2. Process subtitles (iterate in reverse for safe removal)
        self._removed_subs.clear()
        self._truncated_subs.clear()
        self._shifted_subs.clear()

        to_remove_subs = []
        for i, seg in enumerate(self._sub_track.segments):
            if seg.start_ms >= self._clip_start and seg.end_ms <= self._clip_end:
                to_remove_subs.append(i)
            elif seg.start_ms < self._clip_end and seg.end_ms > self._clip_start:
                self._truncated_subs.append((i, seg.start_ms, seg.end_ms))
                if seg.start_ms < self._clip_start:
                    seg.end_ms = self._clip_start
                else:
                    seg.start_ms = self._clip_start
                    seg.end_ms = seg.end_ms - self._shift
            elif seg.start_ms >= self._clip_end:
                self._shifted_subs.append((i, seg.start_ms, seg.end_ms))
                seg.start_ms -= self._shift
                seg.end_ms -= self._shift

        for i in reversed(to_remove_subs):
            self._removed_subs.append((i, self._sub_track.segments[i]))
            self._sub_track.segments.pop(i)

        # 3. Process overlays
        if self._overlay_track:
            self._removed_overlays.clear()
            self._truncated_overlays.clear()
            self._shifted_overlays.clear()
            
            to_remove_ov = []
            for i, ov in enumerate(self._overlay_track.overlays):
                if ov.start_ms >= self._clip_start and ov.end_ms <= self._clip_end:
                    to_remove_ov.append(i)
                elif ov.start_ms < self._clip_end and ov.end_ms > self._clip_start:
                    self._truncated_overlays.append((i, ov.start_ms, ov.end_ms))
                    if ov.start_ms < self._clip_start:
                         ov.end_ms = self._clip_start
                    else:
                         ov.start_ms = self._clip_start
                         ov.end_ms = ov.end_ms - self._shift
                elif ov.start_ms >= self._clip_end:
                     self._shifted_overlays.append((i, ov.start_ms, ov.end_ms))
                     ov.start_ms -= self._shift
                     ov.end_ms -= self._shift
            
            for i in reversed(to_remove_ov):
                self._removed_overlays.append((i, self._overlay_track.overlays[i]))
                self._overlay_track.overlays.pop(i)

        # 4. Process Audio Track (TTS)
        # 삭제 구역과 TTS 구간이 겹치면 오디오 무효화(재생 안 함, 재생성 필요)
        old_audio_end = self._sub_track.audio_start_ms + self._sub_track.audio_duration_ms
        deleted_overlaps_tts = (
            self._sub_track.audio_duration_ms > 0
            and (self._sub_track.audio_start_ms < self._clip_end and old_audio_end > self._clip_start)
        )
        if deleted_overlaps_tts:
            self._sub_track.audio_path = ""
            self._sub_track.audio_duration_ms = 0
            self._sub_track.audio_start_ms = 0
        elif self._sub_track.audio_start_ms >= self._clip_end:
            self._sub_track.audio_start_ms -= self._shift
        elif self._sub_track.audio_start_ms > self._clip_start:
            self._sub_track.audio_start_ms = self._clip_start

        # 5. BGM clips: 삭제 구간 이후 시작하는 클립을 당김
        self._shifted_bgm.clear()
        for t_idx, bgm_track in enumerate(self._project.bgm_tracks):
            if bgm_track.locked:
                continue
            for c_idx, clip in enumerate(bgm_track.clips):
                if clip.start_ms >= self._clip_end:
                    self._shifted_bgm.append((t_idx, c_idx, clip.start_ms))
                    clip.start_ms -= self._shift

        # 6. Text overlays: 삭제 구간 이후 오버레이를 당김
        self._shifted_text.clear()
        tt = self._project.text_overlay_track
        if tt and not tt.locked:
            for ov_idx, ov in enumerate(tt.overlays):
                if ov.start_ms >= self._clip_end:
                    self._shifted_text.append((ov_idx, ov.start_ms, ov.end_ms))
                    ov.start_ms -= self._shift
                    ov.end_ms -= self._shift

    def undo(self) -> None:
        if self._ripple:
            # 1. Restore removed subtitles
            for i, seg in self._removed_subs:
                self._sub_track.segments.insert(i, seg)

            # 2. Restore truncated subtitles
            for i, old_start, old_end in self._truncated_subs:
                if i < len(self._sub_track.segments):
                    self._sub_track.segments[i].start_ms = old_start
                    self._sub_track.segments[i].end_ms = old_end

            # 3. Unshift moved subtitles
            for i, old_start, old_end in self._shifted_subs:
                if i < len(self._sub_track.segments):
                    self._sub_track.segments[i].start_ms = old_start
                    self._sub_track.segments[i].end_ms = old_end

            # 4. Restore overlays
            if self._overlay_track is not None:
                for i, ov in self._removed_overlays:
                    self._overlay_track.overlays.insert(i, ov)
                for i, old_start, old_end in self._truncated_overlays:
                    if i < len(self._overlay_track.overlays):
                        self._overlay_track.overlays[i].start_ms = old_start
                        self._overlay_track.overlays[i].end_ms = old_end
                for i, old_start, old_end in self._shifted_overlays:
                    if i < len(self._overlay_track.overlays):
                        self._overlay_track.overlays[i].start_ms = old_start
                        self._overlay_track.overlays[i].end_ms = old_end

            # 5. Restore audio track
            self._sub_track.audio_start_ms = self._old_audio_start
            self._sub_track.audio_duration_ms = self._old_audio_duration
            self._sub_track.audio_path = self._old_audio_path

            # 6. Restore BGM clips
            for t_idx, c_idx, old_start in self._shifted_bgm:
                tracks = self._project.bgm_tracks
                if t_idx < len(tracks) and c_idx < len(tracks[t_idx].clips):
                    tracks[t_idx].clips[c_idx].start_ms = old_start

            # 7. Restore text overlays
            tt = self._project.text_overlay_track
            if tt:
                for ov_idx, old_start, old_end in self._shifted_text:
                    if ov_idx < len(tt.overlays):
                        tt.overlays[ov_idx].start_ms = old_start
                        tt.overlays[ov_idx].end_ms = old_end

        # 8. Restore the clip
        vt = self._project.video_tracks[self._track_index]
        vt.clips.insert(self._clip_index, self._removed_clip)

        self._sub_track.segments.sort(key=lambda s: s.start_ms)
        if self._overlay_track:
            self._overlay_track.overlays.sort(key=lambda o: o.start_ms)


class TrimClipCommand(QUndoCommand):
    """Trim a video clip edge with ripple."""

    def __init__(self, project: ProjectState, track_index: int, clip_index: int,
                 old_in: int, old_out: int, new_in: int, new_out: int,
                 subtitle_track: SubtitleTrack,
                 image_overlay_track: ImageOverlayTrack | None,
                 ripple: bool = True):
        super().__init__(f"Trim clip {clip_index + 1} on track {track_index + 1}")
        self._project = project
        self._track_index = track_index
        self._index = clip_index
        self._old_in = old_in
        self._old_out = old_out
        self._new_in = new_in
        self._new_out = new_out
        self._sub_track = subtitle_track
        self._overlay_track = image_overlay_track
        self._ripple = ripple

        old_duration = old_out - old_in
        new_duration = new_out - new_in
        self._delta = new_duration - old_duration

        self._clip_track = project.video_tracks[track_index]

        # 트림 전 클립의 타임라인 끝 위치 = 리플 기준점
        # 클립 i 이후의 모든 항목이 delta만큼 이동한다
        self._clip_start_tl = 0
        for i in range(self._index):
            self._clip_start_tl += self._clip_track.clips[i].duration_ms

        self._ripple_point = self._clip_start_tl + old_duration

        # Snapshot for Audio (TTS) — 트림 시 TTS 무효화 후 undo에서 복원
        self._old_audio_start = subtitle_track.audio_start_ms
        self._old_audio_duration = subtitle_track.audio_duration_ms
        self._old_audio_path = getattr(subtitle_track, "audio_path", "") or ""

    def redo(self) -> None:
        if 0 <= self._index < len(self._clip_track.clips):
            clip = self._clip_track.clips[self._index]
            
            # Preserve volume point sync when trimming left
            if self._new_in != self._old_in:
                delta_src = self._new_in - self._old_in
                delta_visual = -int(delta_src / clip.speed)
                clip.shift_volume_points(delta_visual)
                
            clip.source_in_ms = self._new_in
            clip.source_out_ms = self._new_out
            
            if self._ripple and self._delta != 0:
                self._apply_shift(self._delta)
                # 타임라인 길이 변경 시 TTS 오디오 무효화(삭제 구간 음성 제거)
                if self._sub_track.audio_duration_ms > 0:
                    self._sub_track.audio_path = ""
                    self._sub_track.audio_duration_ms = 0
                    self._sub_track.audio_start_ms = 0

    def undo(self) -> None:
        if 0 <= self._index < len(self._clip_track.clips):
            clip = self._clip_track.clips[self._index]
            
            # Reverse volume point shift
            if self._new_in != self._old_in:
                delta_src = self._old_in - self._new_in
                delta_visual = -int(delta_src / clip.speed)
                clip.shift_volume_points(delta_visual)
                
            clip.source_in_ms = self._old_in
            clip.source_out_ms = self._old_out

            if self._ripple and self._delta != 0:
                self._apply_shift(-self._delta, threshold=self._ripple_point + self._delta)
                # TTS 오디오 복원 (_apply_shift가 audio를 건드린 뒤 덮어씀)
                self._sub_track.audio_start_ms = self._old_audio_start
                self._sub_track.audio_duration_ms = self._old_audio_duration
                self._sub_track.audio_path = self._old_audio_path
                
    def _apply_shift(self, delta: int, threshold: int | None = None) -> None:
        threshold = threshold if threshold is not None else self._ripple_point
        # Shift subtitles (active track)
        for seg in self._sub_track.segments:
            if seg.start_ms >= threshold:
                seg.start_ms += delta
                seg.end_ms += delta

        # Shift image overlays
        if self._overlay_track:
            for ov in self._overlay_track.overlays:
                if ov.start_ms >= threshold:
                    ov.start_ms += delta
                    ov.end_ms += delta

        # Shift text overlays
        tt = self._project.text_overlay_track
        if tt and not tt.locked:
            for ov in tt.overlays:
                if ov.start_ms >= threshold:
                    ov.start_ms += delta
                    ov.end_ms += delta

        # Shift BGM clips
        for bgm_track in self._project.bgm_tracks:
            if bgm_track.locked:
                continue
            for clip in bgm_track.clips:
                if clip.start_ms >= threshold:
                    clip.start_ms += delta

        # Shift Audio (TTS)
        if self._sub_track.audio_start_ms >= threshold:
            self._sub_track.audio_start_ms += delta


class AddVideoClipCommand(QUndoCommand):
    """Insert a video clip into a specific track with ripple."""

    def __init__(self, project: ProjectState, track_index: int, clip: VideoClip,
                 subtitle_track: SubtitleTrack,
                 image_overlay_track: ImageOverlayTrack | None,
                 insert_index: int | None = None,
                 ripple: bool = True):
        from pathlib import Path
        name = Path(clip.source_path).stem if clip.source_path else "clip"
        super().__init__(f"Add video clip ({name}) to track {track_index + 1}")
        self._project = project
        self._track_index = track_index
        self._clip = clip
        self._sub_track = subtitle_track
        self._overlay_track = image_overlay_track
        self._index = insert_index
        self._ripple = ripple
        self._shift = clip.duration_ms

        vt = project.video_tracks[track_index]
        self._resolved_index = insert_index if insert_index is not None else len(vt.clips)
        
        self._ripple_point = 0
        for i in range(self._resolved_index):
            if i < len(vt.clips):
                 self._ripple_point += vt.clips[i].duration_ms
        
        # Audio snapshot
        self._old_audio_start = subtitle_track.audio_start_ms
        self._old_audio_duration = subtitle_track.audio_duration_ms

    def redo(self) -> None:
        vt = self._project.video_tracks[self._track_index]
        if self._index is not None and 0 <= self._index <= len(vt.clips):
            vt.clips.insert(self._index, self._clip)
        else:
            vt.clips.append(self._clip)
            self._index = len(vt.clips) - 1
            
        if self._ripple:
             self._apply_shift(self._shift)

    def undo(self) -> None:
        try:
            vt = self._project.video_tracks[self._track_index]
            if self._index is not None and self._index < len(vt.clips) and vt.clips[self._index] is self._clip:
                 vt.clips.pop(self._index)
            else:
                 vt.clips.remove(self._clip)
                 
            if self._ripple:
                 self._apply_shift(-self._shift, threshold=self._ripple_point + self._shift)
                 
            # Restore audio exactly to avoid drift
            self._sub_track.audio_start_ms = self._old_audio_start
            self._sub_track.audio_duration_ms = self._old_audio_duration
            
        except ValueError:
            pass

    def _apply_shift(self, delta: int, threshold: int | None = None) -> None:
        threshold = threshold if threshold is not None else self._ripple_point
        # Shift subtitles (active track)
        for seg in self._sub_track.segments:
            if seg.start_ms >= threshold:
                seg.start_ms += delta
                seg.end_ms += delta

        # Shift image overlays
        if self._overlay_track:
            for ov in self._overlay_track.overlays:
                if ov.start_ms >= threshold:
                    ov.start_ms += delta
                    ov.end_ms += delta

        # Shift text overlays
        tt = self._project.text_overlay_track
        if tt and not tt.locked:
            for ov in tt.overlays:
                if ov.start_ms >= threshold:
                    ov.start_ms += delta
                    ov.end_ms += delta

        # Shift BGM clips
        for bgm_track in self._project.bgm_tracks:
            if bgm_track.locked:
                continue
            for clip in bgm_track.clips:
                if clip.start_ms >= threshold:
                    clip.start_ms += delta

        # Shift Audio (TTS)
        if self._sub_track.audio_start_ms >= threshold:
            self._sub_track.audio_start_ms += delta


class EditSpeedCommand(QUndoCommand):
    """Change the playback speed of a video clip with subtitle ripple."""

    def __init__(self, project: ProjectState, track_index: int, clip_index: int,
                 old_speed: float, new_speed: float,
                 subtitle_track: SubtitleTrack,
                 image_overlay_track: ImageOverlayTrack | None,
                 ripple: bool = True):
        super().__init__(f"Edit speed (clip {clip_index + 1} on track {track_index + 1})")
        self._project = project
        self._track_index = track_index
        self._index = clip_index
        self._old_speed = old_speed
        self._new_speed = new_speed
        self._sub_track = subtitle_track
        self._overlay_track = image_overlay_track
        self._ripple = ripple

        vt = project.video_tracks[track_index]
        clip = vt.clips[clip_index]
        raw_dur = clip.source_out_ms - clip.source_in_ms
        old_dur = int(raw_dur / old_speed)
        new_dur = int(raw_dur / new_speed)
        self._delta = new_dur - old_dur

        # Calculate ripple point
        self._clip_start_tl = 0
        for i in range(self._index):
            self._clip_start_tl += vt.clips[i].duration_ms
        self._ripple_point = self._clip_start_tl + old_dur

        # Snapshot for Audio (TTS)
        self._old_audio_start = subtitle_track.audio_start_ms

    def redo(self) -> None:
        vt = self._project.video_tracks[self._track_index]
        if 0 <= self._index < len(vt.clips):
            vt.clips[self._index].speed = self._new_speed
            if self._ripple and self._delta != 0:
                self._apply_shift(self._delta)

    def undo(self) -> None:
        vt = self._project.video_tracks[self._track_index]
        if 0 <= self._index < len(vt.clips):
            vt.clips[self._index].speed = self._old_speed
            if self._ripple and self._delta != 0:
                self._apply_shift(-self._delta, threshold=self._ripple_point + self._delta)

    def _apply_shift(self, delta: int, threshold: int | None = None) -> None:
        threshold = threshold if threshold is not None else self._ripple_point
        # Shift subtitles (active track)
        for seg in self._sub_track.segments:
            if seg.start_ms >= threshold:
                seg.start_ms += delta
                seg.end_ms += delta

        # Shift image overlays
        if self._overlay_track:
            for ov in self._overlay_track.overlays:
                if ov.start_ms >= threshold:
                    ov.start_ms += delta
                    ov.end_ms += delta

        # Shift text overlays
        tt = self._project.text_overlay_track
        if tt and not tt.locked:
            for ov in tt.overlays:
                if ov.start_ms >= threshold:
                    ov.start_ms += delta
                    ov.end_ms += delta

        # Shift BGM clips
        for bgm_track in self._project.bgm_tracks:
            if bgm_track.locked:
                continue
            for clip in bgm_track.clips:
                if clip.start_ms >= threshold:
                    clip.start_ms += delta

        # Shift Audio (TTS)
        if self._sub_track.audio_start_ms >= threshold:
            self._sub_track.audio_start_ms += delta


class EditTransitionCommand(QUndoCommand):
    """Command to add or modify a video transition with ripples."""

    def __init__(self, project, track_index, clip_index, new_info, ripple=True):
        super().__init__(tr("Edit Transition"))
        self._project = project
        self._track_index = track_index
        self._index = clip_index
        self._new_info = new_info
        self._ripple = ripple

        vt = project.video_tracks[track_index]
        self._clip = vt.clips[clip_index]
        self._old_info = self._clip.transition_out

        # Calculate duration delta (overlap increases = total duration decreases)
        old_overlap = self._old_info.duration_ms if self._old_info else 0
        new_overlap = new_info.duration_ms if new_info else 0
        self._delta = -(new_overlap - old_overlap)

        # Ripple point: start of the NEXT clip
        start_ms = 0
        for i in range(self._index + 1):
            start_ms += vt.clips[i].duration_ms
            if vt.clips[i].transition_out and i < self._index:
                start_ms -= vt.clips[i].transition_out.duration_ms
        self._ripple_point = start_ms

        self._sub_track = project.subtitle_track
        self._overlay_track = project.image_overlay_track

    def redo(self) -> None:
        self._clip.transition_out = self._new_info
        if self._ripple and self._delta != 0:
            self._apply_shift(self._delta)

    def undo(self) -> None:
        self._clip.transition_out = self._old_info
        if self._ripple and self._delta != 0:
            self._apply_shift(-self._delta, threshold=self._ripple_point + self._delta)

    def _apply_shift(self, delta: int, threshold: int | None = None) -> None:
        target = threshold if threshold is not None else self._ripple_point
        # Subtitles (active track)
        for seg in self._sub_track.segments:
            if seg.start_ms >= target:
                seg.start_ms += delta
                seg.end_ms += delta
        # Image overlays
        if self._overlay_track:
            for ov in self._overlay_track.overlays:
                if ov.start_ms >= target:
                    ov.start_ms += delta
                    ov.end_ms += delta
        # Text overlays
        tt = self._project.text_overlay_track
        if tt and not tt.locked:
            for ov in tt.overlays:
                if ov.start_ms >= target:
                    ov.start_ms += delta
                    ov.end_ms += delta
        # BGM clips
        for bgm_track in self._project.bgm_tracks:
            if bgm_track.locked:
                continue
            for clip in bgm_track.clips:
                if clip.start_ms >= target:
                    clip.start_ms += delta
        # Audio (TTS)
        if self._sub_track.audio_start_ms >= target:
            self._sub_track.audio_start_ms += delta


class EditClipPropertiesCommand(QUndoCommand):
    """Adjust video clip properties (volume, brightness, contrast, saturation)."""

    def __init__(self, clip: VideoClip, old_values: dict, new_values: dict):
        super().__init__(tr("Edit clip properties"))
        self._clip = clip
        self._old = old_values
        self._new = new_values

    def redo(self) -> None:
        self._apply(self._new)

    def undo(self) -> None:
        self._apply(self._old)

    def _apply(self, values: dict) -> None:
        self._clip.volume = values.get("volume", self._clip.volume)
        self._clip.brightness = values.get("brightness", self._clip.brightness)
        self._clip.contrast = values.get("contrast", self._clip.contrast)
        self._clip.saturation = values.get("saturation", self._clip.saturation)


class AddVideoTrackCommand(QUndoCommand):
    """Add a new video track."""

    def __init__(self, project: ProjectState):
        super().__init__(tr("Add Video Track"))
        self._project = project
        # Import here to avoid circular imports if any, or ensure it's available
        from src.models.video_clip import VideoClipTrack
        self._track = VideoClipTrack()

    def redo(self) -> None:
        self._project.video_tracks.append(self._track)

    def undo(self) -> None:
        if self._project.video_tracks:
            self._project.video_tracks.pop()


class RemoveVideoTrackCommand(QUndoCommand):
    """Remove a video track."""

    def __init__(self, project: ProjectState, index: int):
        super().__init__(tr("Remove Video Track"))
        self._project = project
        self._index = index
        self._track = project.video_tracks[index]

    def redo(self) -> None:
        if 0 <= self._index < len(self._project.video_tracks):
            self._project.video_tracks.pop(self._index)

    def undo(self) -> None:
        self._project.video_tracks.insert(self._index, self._track)


class MoveVideoClipCommand(QUndoCommand):
    """Move a video clip from one track/position to another."""

    def __init__(self, project: ProjectState,
                 src_track_idx: int, src_clip_idx: int,
                 dst_track_idx: int, dst_insert_idx: int,
                 subtitle_track: SubtitleTrack | None = None,
                 image_overlay_track: ImageOverlayTrack | None = None,
                 move_linked: bool = False):
        super().__init__(tr("Move Video Clip"))
        self._project = project
        self._src_track_idx = src_track_idx
        self._src_clip_idx = src_clip_idx
        self._dst_track_idx = dst_track_idx
        self._dst_insert_idx = dst_insert_idx
        self._sub_track = subtitle_track
        self._overlay_track = image_overlay_track
        self._move_linked = move_linked

        # Calculate original start time for linked move
        src_track = project.video_tracks[src_track_idx]
        self._old_start_ms = src_track.clip_timeline_start(src_clip_idx)
        self._clip_duration = src_track.clips[src_clip_idx].duration_ms

    def redo(self) -> None:
        src_track = self._project.video_tracks[self._src_track_idx]
        dst_track = self._project.video_tracks[self._dst_track_idx]
        
        clip = src_track.clips.pop(self._src_clip_idx)
        
        # Adjust insertion index if moving within the same track
        insert_idx = self._dst_insert_idx
        if self._src_track_idx == self._dst_track_idx and self._src_clip_idx < self._dst_insert_idx:
            insert_idx -= 1
            
        dst_track.clips.insert(insert_idx, clip)
        
        # Handle linked items
        if self._move_linked:
            # Calculate new start time
            new_start_ms = dst_track.clip_timeline_start(insert_idx)
            delta = new_start_ms - self._old_start_ms
            self._shift_linked_items(delta)

    def undo(self) -> None:
        # To undo, move it back. We need to calculate the new index of the clip.
        # However, since we know where we inserted it, we can just reverse the operation.
        # But wait, if same track, indices shifted.
        # Let's just use the inverse logic.
        
        # Current location:
        curr_track_idx = self._dst_track_idx
        curr_clip_idx = self._dst_insert_idx
        if self._src_track_idx == self._dst_track_idx and self._src_clip_idx < self._dst_insert_idx:
            curr_clip_idx -= 1
            
        # Target location (original):
        target_track_idx = self._src_track_idx
        target_insert_idx = self._src_clip_idx
        
        src_track = self._project.video_tracks[curr_track_idx]
        dst_track = self._project.video_tracks[target_track_idx]
        
        clip = src_track.clips.pop(curr_clip_idx)
        dst_track.clips.insert(target_insert_idx, clip)
        
        if self._move_linked:
            # Reverse shift
            # We know the delta from redo, but we can re-calculate or store it.
            # The clip is now back at _old_start_ms.
            # The position it was at before undo was... we need to calculate it or store delta.
            # Let's calculate delta again based on where it was.
            # Actually, simpler: we know we moved it back to _old_start_ms.
            # So we just need to find where it WAS.
            # But wait, we just moved it.
            # Let's just store delta in redo.
            # Or re-calculate:
            # The clip was at `src_track.clip_timeline_start(curr_clip_idx)` before pop.
            # But we already popped it.
            # Let's assume redo logic is deterministic.
            # We can just shift items back by checking what overlaps the "new" position (which is now old).
            # Actually, simpler:
            # We moved items that were at [old_start, old_end]. They are now at [new_start, new_end].
            # We want to move them back.
            # But wait, if we use the same logic, we need to know the "source" range to find items.
            # The items are currently at the "new" position.
            # So we find items at [new_start, new_end] and shift by -delta.
            
            # However, calculating new_start here is tricky because we just modified the track.
            # Let's store delta in self.
            pass
            
        # Re-implementing linked move undo properly requires storing the delta from redo
        # Since QUndoCommand doesn't persist state easily between redo/undo calls unless we store it in self.
        # Let's modify redo to store self._applied_delta

    def _shift_linked_items(self, delta: int):
        if delta == 0:
            return
            
        # Define the source range.
        # If we are in redo(), we are moving FROM old_start.
        # If we are in undo(), we are moving FROM new_start (which is old_start + delta).
        # Wait, undo() calls this? No, I need to handle undo explicitly.
        
        # Let's refine:
        # Items to move are those that were within [self._old_start_ms, self._old_start_ms + self._clip_duration]
        # But wait, if we already moved them in redo, they are now at [new_start, ...].
        # So in undo, we should look at [new_start, ...] and move back.
        
        # Actually, simpler approach:
        # Identify items based on the *original* range (before move).
        # But we don't have persistent IDs for subtitles.
        # So we must rely on current positions.
        
        # In Redo:
        # Find items in [old_start, old_end]. Shift by delta.
        # In Undo:
        # Find items in [old_start + delta, old_end + delta]. Shift by -delta.
        
        pass 
        
        # Real implementation in redo/undo below
        
    def redo(self) -> None:
        src_track = self._project.video_tracks[self._src_track_idx]
        dst_track = self._project.video_tracks[self._dst_track_idx]
        
        clip = src_track.clips.pop(self._src_clip_idx)
        
        insert_idx = self._dst_insert_idx
        if self._src_track_idx == self._dst_track_idx and self._src_clip_idx < self._dst_insert_idx:
            insert_idx -= 1
            
        dst_track.clips.insert(insert_idx, clip)
        
        if self._move_linked:
            new_start_ms = dst_track.clip_timeline_start(insert_idx)
            self._delta = new_start_ms - self._old_start_ms
            if self._delta != 0:
                self._apply_shift(self._old_start_ms, self._old_start_ms + self._clip_duration, self._delta)

    def undo(self) -> None:
        curr_track_idx = self._dst_track_idx
        curr_clip_idx = self._dst_insert_idx
        if self._src_track_idx == self._dst_track_idx and self._src_clip_idx < self._dst_insert_idx:
            curr_clip_idx -= 1
            
        target_track_idx = self._src_track_idx
        target_insert_idx = self._src_clip_idx
        
        src_track = self._project.video_tracks[curr_track_idx]
        dst_track = self._project.video_tracks[target_track_idx]
        
        clip = src_track.clips.pop(curr_clip_idx)
        dst_track.clips.insert(target_insert_idx, clip)
        
        if self._move_linked and hasattr(self, '_delta') and self._delta != 0:
            # Shift back items that are currently at the new position
            new_start = self._old_start_ms + self._delta
            new_end = new_start + self._clip_duration
            self._apply_shift(new_start, new_end, -self._delta)

    def _apply_shift(self, start_range: int, end_range: int, delta: int) -> None:
        # Shift subtitles that start within the range
        if self._sub_track:
            for seg in self._sub_track.segments:
                # Check if segment starts within the clip's range
                # Using a slight tolerance or strict containment?
                # Let's use strict start time containment.
                if start_range <= seg.start_ms < end_range:
                    seg.start_ms += delta
                    seg.end_ms += delta
                    if seg.audio_file:
                        seg.audio_start_ms += delta
        
        # Shift overlays
        if self._overlay_track:
            for ov in self._overlay_track.overlays:
                if start_range <= ov.start_ms < end_range:
                    ov.start_ms += delta
                    ov.end_ms += delta


class DuplicateVideoClipCommand(QUndoCommand):
    """Duplicate a video clip to another track/position."""

    def __init__(self, project: ProjectState,
                 src_track_idx: int, src_clip_idx: int,
                 dst_track_idx: int, dst_insert_idx: int):
        super().__init__(tr("Duplicate Video Clip"))
        self._project = project
        self._src_track_idx = src_track_idx
        self._src_clip_idx = src_clip_idx
        self._dst_track_idx = dst_track_idx
        self._dst_insert_idx = dst_insert_idx
        self._new_clip = None

    def redo(self) -> None:
        src_track = self._project.video_tracks[self._src_track_idx]
        dst_track = self._project.video_tracks[self._dst_track_idx]
        
        if self._new_clip is None:
            original = src_track.clips[self._src_clip_idx]
            self._new_clip = original.clone()
            
        dst_track.clips.insert(self._dst_insert_idx, self._new_clip)

    def undo(self) -> None:
        dst_track = self._project.video_tracks[self._dst_track_idx]
        dst_track.clips.pop(self._dst_insert_idx)


# ============================================================================
# Text Overlay Commands
# ============================================================================

class AddTextOverlayCommand(QUndoCommand):
    """Add a new text overlay to the project."""

    def __init__(self, track: TextOverlayTrack, overlay: TextOverlay):
        super().__init__(tr("Add text overlay"))
        self._track = track
        self._overlay = overlay

    def redo(self) -> None:
        self._track.add_overlay(self._overlay)

    def undo(self) -> None:
        # Find and remove by identity
        for i, ov in enumerate(self._track.overlays):
            if ov is self._overlay:
                self._track.overlays.pop(i)
                break


class DeleteTextOverlayCommand(QUndoCommand):
    """Delete a text overlay from the project."""

    def __init__(self, project: ProjectState, index: int, overlay: TextOverlay):
        super().__init__(tr("Delete text overlay"))
        self._project = project
        self._index = index
        self._overlay = overlay

    def redo(self) -> None:
        self._project.text_overlay_track.remove_overlay(self._index)

    def undo(self) -> None:
        self._project.text_overlay_track.overlays.insert(self._index, self._overlay)
        self._project.text_overlay_track.overlays.sort(key=lambda o: o.start_ms)


class MoveTextOverlayCommand(QUndoCommand):
    """Move a text overlay in time (change start/end)."""

    def __init__(self, overlay: TextOverlay, old_start: int, old_end: int, new_start: int, new_end: int):
        super().__init__(tr("Move text overlay"))
        self._overlay = overlay
        self._old_start = old_start
        self._old_end = old_end
        self._new_start = new_start
        self._new_end = new_end

    def redo(self) -> None:
        self._overlay.start_ms = self._new_start
        self._overlay.end_ms = self._new_end

    def undo(self) -> None:
        self._overlay.start_ms = self._old_start
        self._overlay.end_ms = self._old_end


class UpdateTextOverlayCommand(QUndoCommand):
    """Update text overlay content, style, or position."""

    def __init__(self, overlay: TextOverlay, old_data: dict, new_data: dict):
        super().__init__(tr("Edit text overlay"))
        self._overlay = overlay
        self._old_data = old_data
        self._new_data = new_data

    def redo(self) -> None:
        self._apply_data(self._new_data)

    def undo(self) -> None:
        self._apply_data(self._old_data)

    def _apply_data(self, data: dict) -> None:
        """Apply the given data to the overlay."""
        if "text" in data:
            self._overlay.text = data["text"]
        if "x_percent" in data:
            self._overlay.x_percent = data["x_percent"]
        if "y_percent" in data:
            self._overlay.y_percent = data["y_percent"]
        if "alignment" in data:
            self._overlay.alignment = data["alignment"]
        if "v_alignment" in data:
            self._overlay.v_alignment = data["v_alignment"]
        if "opacity" in data:
            self._overlay.opacity = data["opacity"]
        if "style" in data:
            self._overlay.style = data["style"]


# ============================================================================
# Audio Clip (BGM) Commands
# ============================================================================

class AddAudioClipCommand(QUndoCommand):
    """Add a new background music clip."""

    def __init__(self, project: ProjectState, track_index: int, clip: AudioClip):
        super().__init__(tr("Add BGM clip"))
        self._project = project
        self._track_index = track_index
        self._clip = clip

    def redo(self) -> None:
        if 0 <= self._track_index < len(self._project.bgm_tracks):
            self._project.bgm_tracks[self._track_index].add_clip(self._clip)

    def undo(self) -> None:
        if 0 <= self._track_index < len(self._project.bgm_tracks):
            self._project.bgm_tracks[self._track_index].remove_clip(self._clip)


class MoveAudioClipCommand(QUndoCommand):
    """Move an audio clip (change start position)."""

    def __init__(self, clip: AudioClip, old_start: int, new_start: int):
        super().__init__(tr("Move BGM clip"))
        self._clip = clip
        self._old_start = old_start
        self._new_start = new_start

    def redo(self) -> None:
        self._clip.start_ms = self._new_start

    def undo(self) -> None:
        self._clip.start_ms = self._old_start


class TrimAudioClipCommand(QUndoCommand):
    """Trim an audio clip (change start/duration)."""

    def __init__(self, clip: AudioClip, old_start: int, old_duration: int,
                 new_start: int, new_duration: int):
        super().__init__(tr("Trim BGM clip"))
        self._clip = clip
        self._old_start = old_start
        self._old_duration = old_duration
        self._new_start = new_start
        self._new_duration = new_duration

    def redo(self) -> None:
        self._clip.start_ms = self._new_start
        self._clip.duration_ms = self._new_duration

    def undo(self) -> None:
        self._clip.start_ms = self._old_start
        self._clip.duration_ms = self._old_duration


class DeleteAudioClipCommand(QUndoCommand):
    """Delete a BGM clip."""

    def __init__(self, project: ProjectState, track_index: int, clip_index: int, clip: AudioClip):
        super().__init__(tr("Delete BGM clip"))
        self._project = project
        self._track_index = track_index
        self._clip_index = clip_index
        self._clip = clip

    def redo(self) -> None:
        if 0 <= self._track_index < len(self._project.bgm_tracks):
            track = self._project.bgm_tracks[self._track_index]
            if 0 <= self._clip_index < len(track.clips):
                track.clips.pop(self._clip_index)

    def undo(self) -> None:
        if 0 <= self._track_index < len(self._project.bgm_tracks):
            track = self._project.bgm_tracks[self._track_index]
            track.clips.insert(self._clip_index, self._clip)
            track.clips.sort(key=lambda c: c.start_ms)


class AutoAlignSubtitlesCommand(QUndoCommand):
    """겹치는 자막 자동 정렬."""

    def __init__(
        self,
        track: SubtitleTrack,
        old_times: list[tuple[int, int]],
        new_times: list[tuple[int, int]],
    ):
        super().__init__(tr("Auto-align subtitles"))
        self._track = track
        self._old_times = old_times
        self._new_times = new_times

    def redo(self) -> None:
        self._apply(self._new_times)

    def undo(self) -> None:
        self._apply(self._old_times)

    def _apply(self, times: list[tuple[int, int]]) -> None:
        for i, (s, e) in enumerate(times):
            self._track.segments[i].start_ms = s
            self._track.segments[i].end_ms = e
