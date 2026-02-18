"""PlaybackController — 재생/시크/볼륨 관련 로직."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl, Slot
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from src.ui.controllers.app_context import AppContext


class PlaybackController:
    """재생, 시크, 볼륨 제어를 담당하는 Controller."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # ---- 재생 토글 ----

    def toggle_play_pause(self) -> None:
        ctx = self.ctx
        is_playing = (
            ctx.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            or ctx.tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )

        if is_playing:
            ctx.player.pause()
            ctx.tts_player.pause()
            if ctx.pending_seek_ms is not None:
                ctx.pending_auto_play = False
            ctx.play_intent = False
        else:
            ctx.play_intent = True
            if ctx.project.has_video:
                if ctx.pending_seek_ms is not None:
                    ctx.pending_auto_play = True
                    return

                clip_track = ctx.project.video_clip_track
                if clip_track:
                    timeline_ms = ctx.timeline.get_playhead()
                    result = clip_track.clip_at_timeline(timeline_ms)
                    if result is not None:
                        idx, clip = result
                        ctx.current_clip_index = idx
                        self._apply_clip_speed(clip.speed)
                        clip_start = clip_track.clip_timeline_start(idx)
                        local_offset = timeline_ms - clip_start
                        source_ms = clip.source_in_ms + local_offset
                        target_source_raw = clip.source_path or str(ctx.project.video_path)
                        target_source = ctx.media_ctrl.resolve_playback_path(target_source_raw)

                        if target_source != ctx.current_playback_source:
                            ctx.media_ctrl.switch_player_source(target_source, source_ms, auto_play=True)
                            return
                        at_end = ctx.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia
                        if at_end or abs(ctx.player.position() - source_ms) > 10:
                            ctx.player.setPosition(source_ms)

                ctx.player.play()
                self.sync_tts_playback()
            else:
                track = ctx.project.subtitle_track
                if track and track.audio_path and track.audio_duration_ms > 0:
                    audio_path = Path(track.audio_path)
                    if audio_path.exists():
                        if ctx.tts_player.source() != QUrl.fromLocalFile(str(audio_path)):
                            ctx.tts_player.setSource(QUrl.fromLocalFile(str(audio_path)))
                        ctx.tts_player.play()

    def on_stop_all(self) -> None:
        """Stop both video and TTS players."""
        self.ctx.player.stop()
        self.ctx.tts_player.stop()
        self.ctx.play_intent = False

    # ---- TTS 동기화 ----

    def sync_tts_playback(self) -> None:
        """Synchronize TTS audio playback with video position."""
        try:
            ctx = self.ctx
            track = ctx.project.subtitle_track
            if not track or not track.audio_path or track.audio_duration_ms <= 0:
                return
            audio_path = Path(track.audio_path)
            if not audio_path.exists():
                return

            video_is_playing = (
                ctx.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )

            if ctx.project.video_clip_track and len(ctx.project.video_clip_track.clips) > 0:
                current_pos_ms = ctx.timeline.get_playhead()
            else:
                current_pos_ms = ctx.player.position()

            audio_start_ms = track.audio_start_ms
            audio_end_ms = audio_start_ms + track.audio_duration_ms

            if audio_start_ms <= current_pos_ms < audio_end_ms:
                tts_pos_ms = current_pos_ms - audio_start_ms
                current_source = ctx.tts_player.source()
                new_source = QUrl.fromLocalFile(str(audio_path))
                if not current_source.isValid() or current_source != new_source:
                    ctx.tts_player.setSource(new_source)
                ctx.tts_player.setPosition(tts_pos_ms)
                if video_is_playing:
                    if ctx.tts_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                        ctx.tts_player.play()
                else:
                    if ctx.tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                        ctx.tts_player.pause()
            else:
                if ctx.tts_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    ctx.tts_player.pause()
        except Exception:
            pass

    # ---- 시크 ----

    def seek_relative(self, delta_ms: int) -> None:
        pos = max(0, self.ctx.player.position() + delta_ms)
        self.ctx.player.setPosition(pos)
        self.sync_tts_playback()

    def seek_frame_relative(self, frame_delta: int) -> None:
        """프레임 단위 시크."""
        if self.ctx.player.duration() <= 0:
            return
        from src.services.settings_manager import SettingsManager
        from src.utils.time_utils import frame_to_ms
        fps = SettingsManager().get_frame_seek_fps()
        ms_delta = frame_to_ms(frame_delta, fps)
        self.seek_relative(ms_delta)

    def apply_frame_fps(self) -> None:
        """FPS 설정을 타임라인/컨트롤에 적용."""
        from src.services.settings_manager import SettingsManager
        fps = SettingsManager().get_frame_seek_fps()
        self.ctx.timeline.set_snap_fps(fps)
        self.ctx.controls.set_display_fps(fps)

    def on_jump_to_frame(self) -> None:
        """Jump to Frame 다이얼로그."""
        from src.services.settings_manager import SettingsManager
        from src.ui.dialogs.jump_to_frame_dialog import JumpToFrameDialog

        ctx = self.ctx
        fps = SettingsManager().get_frame_seek_fps()
        current_ms = ctx.player.position() if ctx.project.has_video else 0
        duration_ms = (
            ctx.player.duration()
            if ctx.project.has_video
            else ctx.timeline._duration_ms
        )

        dialog = JumpToFrameDialog(current_ms, fps, duration_ms, parent=ctx.window)
        if dialog.exec() == JumpToFrameDialog.DialogCode.Accepted:
            target = dialog.target_ms()
            if target is not None:
                self.on_timeline_seek(target)

    # ---- 타임라인 시크 ----

    def on_timeline_seek(self, position_ms: int) -> None:
        ctx = self.ctx
        if ctx.project.has_video:
            clip_track = ctx.project.video_clip_track
            if clip_track:
                result = clip_track.clip_at_timeline(position_ms)
                if result is not None:
                    idx, clip = result
                    ctx.current_clip_index = idx
                    self._apply_clip_speed(clip.speed)
                    local_offset = position_ms - clip_track.clip_timeline_start(idx)
                    source_ms = clip.source_in_ms + local_offset
                    target_source_raw = clip.source_path or str(ctx.project.video_path)
                    target_source = ctx.media_ctrl.resolve_playback_path(target_source_raw)

                    if target_source != ctx.current_playback_source:
                        ctx.media_ctrl.switch_player_source(
                            target_source, source_ms, auto_play=ctx.play_intent
                        )
                    elif ctx.pending_seek_ms is not None:
                        ctx.pending_seek_ms = source_ms
                    else:
                        ctx.player.setPosition(source_ms)
                        if ctx.play_intent:
                            ctx.player.play()
                    ctx.timeline.set_playhead(position_ms)
                    ctx.controls.set_output_position(position_ms)
                else:
                    ctx.player.setPosition(position_ms)
                    ctx.timeline.set_playhead(position_ms)
                    ctx.controls.set_output_position(position_ms)
            else:
                ctx.player.setPosition(position_ms)
                ctx.timeline.set_playhead(position_ms)
                ctx.controls.set_output_position(position_ms)
            self.sync_tts_playback()
            self.update_playback_volume()
        else:
            track = ctx.project.subtitle_track
            if track and track.audio_path and track.audio_duration_ms > 0:
                audio_start = track.audio_start_ms
                audio_end = audio_start + track.audio_duration_ms
                if audio_start <= position_ms < audio_end:
                    tts_pos = position_ms - audio_start
                    ctx.tts_player.setPosition(tts_pos)
            ctx.timeline.set_playhead(position_ms)

    def on_position_changed_by_user(self, position_ms: int) -> None:
        """Handle position change from playback controls slider."""
        ctx = self.ctx
        clip_track = ctx.project.video_clip_track
        if clip_track:
            result = clip_track.clip_at_timeline(position_ms)
            if result is not None:
                idx, clip = result
                self._apply_clip_speed(clip.speed)
                ctx.current_clip_index = idx
                local_offset = position_ms - clip_track.clip_timeline_start(idx)
                source_ms = clip.source_in_ms + local_offset
                target_source_raw = clip.source_path or str(ctx.project.video_path)
                target_source = ctx.media_ctrl.resolve_playback_path(target_source_raw)
                if target_source != ctx.current_playback_source:
                    ctx.media_ctrl.switch_player_source(
                        target_source, source_ms, auto_play=ctx.play_intent
                    )
                elif ctx.pending_seek_ms is not None:
                    ctx.pending_seek_ms = source_ms
                else:
                    ctx.player.setPosition(source_ms)
                    if ctx.play_intent:
                        ctx.player.play()
            ctx.timeline.set_playhead(position_ms)
            ctx.controls.set_output_position(position_ms)
        else:
            ctx.player.setPosition(position_ms)
            ctx.timeline.set_playhead(position_ms)
        self.sync_tts_playback()

    # ---- QMediaPlayer 포지션 콜백 ----

    def on_player_position_changed(self, position_ms: int) -> None:
        """Handle video player position change (source_ms from QMediaPlayer)."""
        ctx = self.ctx

        # Sync VideoFramePlayer with QMediaPlayer (Audio Master)
        if hasattr(ctx, "frame_player") and ctx.frame_player:
            ctx.frame_player.sync_with_audio(position_ms)

        if not ctx.project.has_video:
            return
        if ctx.pending_seek_ms is not None:
            return
        if not ctx.project.video_tracks:
            return

        t_idx = ctx.current_track_index
        if t_idx >= len(ctx.project.video_tracks):
            t_idx = 0
            ctx.current_track_index = 0

        vt = ctx.project.video_tracks[t_idx]
        clips = vt.clips
        idx = ctx.current_clip_index

        if not (0 <= idx < len(clips)):
            ctx.clip_ctrl.sync_clip_index_from_position()
            return

        current_clip = clips[idx]
        self._apply_clip_speed(current_clip.speed)

        in_range = current_clip.source_in_ms - 100 <= position_ms <= current_clip.source_out_ms + 100
        if in_range:
            clip_start = vt.clip_timeline_start(idx)
            local_offset = (position_ms - current_clip.source_in_ms) / current_clip.speed
            timeline_ms = int(clip_start + local_offset)

            ctx.timeline.set_playhead(timeline_ms)
            ctx.controls.set_output_position(timeline_ms)
            ctx.video_widget._update_subtitle(timeline_ms)
            self.sync_tts_playback()
            self.update_playback_volume()
        elif position_ms < current_clip.source_in_ms - 100:
            # 현재 클립 범위보다 훨씬 앞 → stale index, 올바른 클립 검색
            for ci, c in enumerate(clips):
                if (c.source_path or str(ctx.project.video_path)) == ctx.current_playback_source:
                    if c.source_in_ms - 100 <= position_ms <= c.source_out_ms + 100:
                        ctx.current_clip_index = ci
                        self._apply_clip_speed(c.speed)
                        cs = vt.clip_timeline_start(ci)
                        lo = (position_ms - c.source_in_ms) / c.speed
                        tms = int(cs + lo)
                        ctx.timeline.set_playhead(tms)
                        ctx.controls.set_output_position(tms)
                        ctx.video_widget._update_subtitle(tms)
                        self.sync_tts_playback()
                        self.update_playback_volume()
                        return

        if position_ms >= current_clip.source_out_ms - 30:
            # 현재 클립의 타임라인 끝을 계산하여 playhead를 다음 클립 시작점으로 이동
            clip_end_timeline = vt.clip_timeline_start(idx) + current_clip.duration_ms
            ctx.timeline.set_playhead(clip_end_timeline)
            ctx.clip_ctrl.sync_clip_index_from_position()
            new_v_idx = ctx.current_track_index
            new_c_idx = ctx.current_clip_index

            new_vt = ctx.project.video_tracks[new_v_idx]
            new_clip = new_vt.clips[new_c_idx]

            next_start = new_vt.clip_timeline_start(new_c_idx)
            ctx.timeline.set_playhead(next_start)

            target_source = new_clip.source_path or str(ctx.project.video_path)
            playback_path = ctx.media_ctrl.resolve_playback_path(target_source)

            if playback_path != ctx.current_playback_source:
                ctx.media_ctrl.switch_player_source(
                    playback_path, new_clip.source_in_ms, auto_play=ctx.play_intent
                )
            else:
                ctx.player.setPosition(new_clip.source_in_ms)
                if ctx.play_intent:
                    ctx.player.play()

    def on_tts_position_changed(self, position_ms: int) -> None:
        """Handle TTS player position change."""
        ctx = self.ctx
        track = ctx.project.subtitle_track
        if track and track.audio_path:
            timeline_pos = track.audio_start_ms + position_ms
            slider_vol = ctx.controls.get_tts_volume()
            seg = track.segment_at(timeline_pos)
            if seg:
                ctx.tts_audio_output.setVolume(seg.volume * slider_vol)
            else:
                ctx.tts_audio_output.setVolume(slider_vol)
            if not ctx.project.has_video:
                ctx.timeline.set_playhead(timeline_pos)
                ctx.video_widget._update_subtitle(timeline_pos)

    # ---- 볼륨 ----

    def update_playback_volume(self) -> None:
        """Update QAudioOutput volume based on current clip volume."""
        ctx = self.ctx
        if not ctx.project or not ctx.audio_output:
            return
        master_vol = ctx.controls.get_video_volume()
        timeline_ms = ctx.timeline.get_playhead()
        res = ctx.clip_ctrl.get_top_clip_at(timeline_ms)
        if res:
            v_idx, c_idx, clip = res
            clip_start = ctx.project.video_tracks[v_idx].clip_timeline_start(c_idx)
            offset_ms = timeline_ms - clip_start
            clip_vol = clip.get_volume_at(offset_ms)
            final_vol = max(0.0, min(1.0, master_vol * clip_vol))
            ctx.audio_output.setVolume(final_vol)
        else:
            ctx.audio_output.setVolume(master_vol)

    # ---- 렌더 / 타임아웃 ----

    def on_render_pause(self) -> None:
        """Pause player after play+pause render trick."""
        if self.ctx.pending_seek_ms is None:
            self.ctx.player.pause()

    def on_pending_seek_timeout(self) -> None:
        """Fallback when backend never emits Loaded/Buffered after setSource."""
        ctx = self.ctx
        if ctx.pending_seek_ms is None:
            return
        seek_ms = ctx.pending_seek_ms
        auto_play = ctx.pending_auto_play or ctx.play_intent
        ctx.pending_seek_ms = None
        ctx.pending_auto_play = False
        ctx.player.setPosition(seek_ms)
        if auto_play:
            ctx.player.play()
        else:
            ctx.player.play()
            ctx.render_pause_timer.start()

    def _apply_clip_speed(self, speed: float) -> None:
        """현재 클립의 속도를 플레이어에 적용."""
        ctx = self.ctx
        # QMediaPlayer
        if abs(ctx.player.playbackRate() - speed) > 0.01:
            ctx.player.setPlaybackRate(speed)

        # VideoFramePlayer
        if hasattr(ctx, "frame_player") and ctx.frame_player:
            ctx.frame_player.set_playback_rate(speed)
