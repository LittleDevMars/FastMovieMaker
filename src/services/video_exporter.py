"""Export video with hard-burned subtitles via FFmpeg."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from src.models.subtitle import SubtitleTrack
from src.models.style import SubtitleStyle
from src.models.video_clip import VideoClipTrack
from src.models.text_overlay import TextOverlay
from src.services.settings_manager import SettingsManager
from src.services.subtitle_exporter import export_srt
from src.services.ffmpeg_logger import log_ffmpeg_command, log_ffmpeg_line
from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner


def _build_concat_filter(
    clips: list,
    source_index_map: dict | None = None,
    out_w: int = 0,
    out_h: int = 0,
) -> tuple[list[str], str, str]:
    """Build FFmpeg trim+concat filter parts for video clips.

    Args:
        clips: List of VideoClip objects.
        source_index_map: Maps ``source_path`` → FFmpeg input index.
            When ``None``, all clips use input 0 (single-source mode).
        out_w, out_h: Output resolution for multi-source normalization.
            When > 0, each clip is scaled+padded to match.

    Returns:
        (filter_parts, video_label, audio_label) where labels are
        e.g. ``"[concatv]"``, ``"[concata]"``.
    """
    parts: list[str] = []
    v_labels = []
    a_labels = []
    need_scale = out_w > 0 and out_h > 0 and source_index_map is not None

    for i, clip in enumerate(clips):
        if source_index_map is not None:
            idx = source_index_map.get(str(clip.source_path) if clip.source_path else None, 0)
        else:
            idx = 0
        
        start_s = clip.source_in_ms / 1000.0
        end_s = clip.source_out_ms / 1000.0
        vl = f"cv{i}"
        al = f"ca{i}"

        # 리스트 + join 패턴 (HPP Ch.11 — O(n) vs O(n²) 문자열 연결)
        v_chain: list[str] = [f"[{idx}:v]trim=start={start_s:.3f}:end={end_s:.3f}", "setpts=PTS-STARTPTS"]

        # Apply visual filters (Brightness, Contrast, Saturation, Hue)
        clip_hue = getattr(clip, "hue", 0.0)
        if clip.brightness != 1.0 or clip.contrast != 1.0 or clip.saturation != 1.0:
            f_bri = clip.brightness - 1.0
            v_chain.append(f"eq=brightness={f_bri:.2f}:contrast={clip.contrast:.2f}:saturation={clip.saturation:.2f}")
        if clip_hue != 0.0:
            v_chain.append(f"hue=h={clip_hue:.2f}")

        settings = SettingsManager()
        pitch_shift_enabled = settings.get_audio_speed_pitch_shift()

        if hasattr(clip, "speed") and clip.speed != 1.0:
            v_chain.append(f"setpts=PTS/{clip.speed:.3f}") # Video speed always changes timing
        if need_scale:
            v_chain.append(f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease")
            v_chain.append(f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2")
            v_chain.append("format=yuv420p")
        parts.append(",".join(v_chain) + f"[{vl}]")

        a_chain: list[str] = [f"[{idx}:a]atrim=start={start_s:.3f}:end={end_s:.3f}"]
        if not pitch_shift_enabled: # Pitch-preserving, so reset timestamps before atempo
            a_chain.append("asetpts=PTS-STARTPTS")
        if hasattr(clip, "speed") and clip.speed != 1.0:
            if pitch_shift_enabled:
                a_chain.append(f"asetpts=PTS/{clip.speed:.3f}") # Change audio timing and pitch
            else: # Pitch-preserving
                speed = clip.speed
                while speed > 2.0:
                    a_chain.append("atempo=2.0")
                    speed /= 2.0
                while speed < 0.5:
                    a_chain.append("atempo=0.5")
                    speed /= 0.5
                a_chain.append(f"atempo={speed:.3f}")
        
        if hasattr(clip, "volume_points") and clip.volume_points:
            pts = sorted(clip.volume_points, key=lambda p: p.offset_ms)
            if pts:
                expr = f"{pts[-1].volume:.3f}"
                for j in range(len(pts) - 1, 0, -1):
                    p1 = pts[j-1]
                    p2 = pts[j]
                    t1, v1 = p1.offset_ms / 1000.0, p1.volume
                    t2, v2 = p2.offset_ms / 1000.0, p2.volume
                    if t2 > t1:
                        seg_expr = f"{v1:.3f}+({v2-v1:.3f})*(t-{t1:.3f})/({t2-t1:.3f})"
                        expr = f"if(lte(t,{t2:.3f}),{seg_expr},{expr})"
                
                t0, v0 = pts[0].offset_ms / 1000.0, pts[0].volume
                expr = f"if(lte(t,{t0:.3f}),{v0:.3f},{expr})"
                a_chain.append(f"volume='{expr}'")
        elif hasattr(clip, "volume") and clip.volume != 1.0:
            a_chain.append(f"volume={clip.volume:.3f}")
            
        parts.append(",".join(a_chain) + f"[{al}]")
        v_labels.append(f"{vl}")
        a_labels.append(f"{al}")

    if len(clips) == 1:
        parts.append(f"[{v_labels[0]}]copy[concatv]")
        parts.append(f"[{a_labels[0]}]acopy[concata]")
        return parts, "[concatv]", "[concata]"

    # Chain clips with transitions or simple concat
    curr_v = v_labels[0]
    curr_a = a_labels[0]
    curr_total_ms = clips[0].duration_ms
    
    for i in range(len(clips) - 1):
        clip_a = clips[i]
        clip_b = clips[i+1]
        next_v = v_labels[i+1]
        next_a = a_labels[i+1]
        
        out_v = f"vchain{i}"
        out_a = f"achain{i}"
        
        trans = getattr(clip_a, "transition_out", None)
        if trans and trans.duration_ms > 0:
            # 트랜지션 길이가 클립보다 길면 offset이 음수가 되어 FFmpeg 오류 발생 → 클램핑
            max_dur_ms = min(trans.duration_ms,
                             curr_total_ms - 1,
                             clip_b.duration_ms - 1)
            max_dur_ms = max(1, max_dur_ms)  # 최소 1ms 보장
            dur_s = max_dur_ms / 1000.0
            # xfade: offset is when the transition STARTS
            offset_s = (curr_total_ms - max_dur_ms) / 1000.0
            parts.append(f"[{curr_v}][{next_v}]xfade=transition={trans.type}:duration={dur_s:.3f}:offset={offset_s:.3f}[{out_v}]")
            # acrossfade: d is duration
            parts.append(f"[{curr_a}][{next_a}]acrossfade=d={dur_s:.3f}:c1=tri:c2=tri[{out_a}]")
            curr_total_ms += clip_b.duration_ms - max_dur_ms
        else:
            # Simple concat for this pair
            # FFmpeg doesn't have a simple 2-input concat filter that works like this easily in a chain
            # without creating a new concat. Let's use xfade with duration 0 or very small if possible.
            # Actually, we can just use "fade" with duration=0.001 at the very end of clip A.
            offset_s = curr_total_ms / 1000.0
            parts.append(f"[{curr_v}][{next_v}]xfade=transition=fade:duration=0.001:offset={offset_s:.3f}[{out_v}]")
            parts.append(f"[{curr_a}][{next_a}]acrossfade=d=0.01:c1=tri:c2=tri[{out_a}]")
            curr_total_ms += clip_b.duration_ms
            
        curr_v = out_v
        curr_a = out_a

    parts.append(f"[{curr_v}]copy[concatv]")
    parts.append(f"[{curr_a}]acopy[concata]")
    return parts, "[concatv]", "[concata]"


def _flags_for_encoder(
    encoder: str,
    codec: str,
    preset: str,
    crf: int,
    output_suffix: str,
) -> list[str]:
    """Resolve encoder flags with export-specific quality values."""
    if output_suffix == ".webm":
        return ["-crf", str(crf), "-b:v", "0"]

    if "videotoolbox" in encoder:
        quality = int(max(0, min(100, 100 - (crf * 1.5))))
        flags = ["-q:v", str(quality), "-realtime", "0"]
    elif "nvenc" in encoder:
        flags = ["-preset", "p4", "-cq", str(crf)]
    elif "qsv" in encoder:
        flags = ["-global_quality", str(crf), "-look_ahead", "1"]
    elif "amf" in encoder:
        flags = ["-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf), "-qp_b", str(crf)]
    elif "vaapi" in encoder:
        flags = ["-rc_mode", "CQP", "-global_quality", str(crf)]
    elif encoder in ("libx264", "libx265"):
        flags = ["-preset", preset, "-crf", str(crf)]
    elif encoder == "libvpx-vp9":
        flags = ["-crf", str(crf), "-b:v", "0"]
    else:
        # Unknown encoders default to software profile.
        fallback = "libx265" if codec == "hevc" else "libx264"
        if encoder != fallback:
            return _flags_for_encoder(fallback, codec, preset, crf, output_suffix)
        flags = ["-preset", preset, "-crf", str(crf)]

    if "-pix_fmt" not in flags and encoder != "libvpx-vp9":
        flags.extend(["-pix_fmt", "yuv420p"])
    return flags


def _is_hardware_encoder(encoder: str) -> bool:
    return any(token in encoder for token in ("videotoolbox", "nvenc", "qsv", "amf", "vaapi"))


def _build_encoder_plan(
    codec: str,
    preset: str,
    crf: int,
    use_gpu: bool,
    output_suffix: str,
) -> list[tuple[str, list[str], bool]]:
    """Build ordered encoder attempts (HW candidates -> software fallback)."""
    if output_suffix == ".webm":
        return [("libvpx-vp9", _flags_for_encoder("libvpx-vp9", codec, preset, crf, output_suffix), False)]

    if not use_gpu:
        sw_encoder = "libx265" if codec == "hevc" else "libx264"
        return [(sw_encoder, _flags_for_encoder(sw_encoder, codec, preset, crf, output_suffix), False)]

    from src.utils.hw_accel import get_encoder_candidates

    plan: list[tuple[str, list[str], bool]] = []
    seen: set[str] = set()
    for item in get_encoder_candidates(codec):
        encoder = item["encoder"]
        if encoder in seen:
            continue
        seen.add(encoder)
        plan.append(
            (
                encoder,
                _flags_for_encoder(encoder, codec, preset, crf, output_suffix),
                bool(item.get("is_hardware", _is_hardware_encoder(encoder))),
            )
        )

    sw_encoder = "libx265" if codec == "hevc" else "libx264"
    if sw_encoder not in seen:
        plan.append((sw_encoder, _flags_for_encoder(sw_encoder, codec, preset, crf, output_suffix), False))
    return plan


def _looks_like_hw_failure(stderr: str) -> bool:
    """Best-effort detection of hardware encoder init/device failures."""
    text = (stderr or "").lower()
    needles = (
        "nvenc",
        "videotoolbox",
        "qsv",
        "amf",
        "vaapi",
        "device",
        "no capable devices found",
        "cannot load",
        "failed to initialise",
        "failed to initialize",
        "hardware device",
        "hardware acceleration",
        "init_hw_device",
        "no device",
        "unsupported device",
        "error initializing output stream",
        "invalid argument",
    )
    return any(n in text for n in needles)


def _status_event_to_message(event: dict[str, Any]) -> str:
    event_type = event.get("type", "")
    if event_type == "probe":
        return f"Trying GPU encoder: {event.get('encoder', 'unknown')}"
    if event_type == "retry":
        reason = event.get("reason", "unknown error")
        return (
            f"GPU failed ({reason}), retrying with {event.get('next_encoder', 'software encoder')}..."
        )
    if event_type == "final_encoder":
        return f"Export completed with {event.get('encoder', 'unknown')}"
    if event_type == "fallback":
        return event.get("message", "")
    return event.get("message", "")


def export_video(
    video_path: Path,
    track: SubtitleTrack,
    output_path: Path,
    on_progress: callable | None = None,
    on_status: callable | None = None,
    audio_path: Path | None = None,
    scale_width: int = 0,
    scale_height: int = 0,
    codec: str = "h264",
    preset: str = "medium",
    crf: int = 23,
    overlay_path: Path | None = None,
    image_overlays: list | None = None,
    video_tracks: list[VideoClipTrack] | None = None,
    text_overlays: list[TextOverlay] | None = None,
    use_gpu: bool = False,
    mix_with_original_audio: bool = False,
    video_volume: float = 1.0,
    audio_volume: float = 1.0,
    audio_bitrate: str = "192k",
) -> None:
    """Burn subtitles into video using FFmpeg's subtitles filter.

    Args:
        video_path: Source video file.
        track: Subtitle track to burn.
        output_path: Destination video file.
        on_progress: Optional callback(duration_sec, current_sec) for progress.
        on_status: Optional callback(status). Structured dict events are sent when
            callback declares structured mode; otherwise legacy strings are sent.
        audio_path: Optional path to replacement audio file (e.g. TTS mixed audio).
        scale_width: Target width in pixels (0 = keep original).
        scale_height: Target height in pixels (0 = keep original).
        codec: Video codec - "h264" or "hevc".
        preset: Encoder preset (e.g., "fast", "medium", "slow").
        crf: Constant Rate Factor (quality, lower is better).
        overlay_path: Optional path to overlay PNG image.
        image_overlays: Optional list of ImageOverlay objects.
        video_tracks: Optional list of video tracks to composite.
        text_overlays: Optional list of TextOverlay objects to render.
        use_gpu: Prefer hardware encoder when available.
        mix_with_original_audio: If True, mix audio_path with video audio instead of replacing it.
        video_volume: Volume multiplier for the original video audio (0.0-1.0+).
        audio_volume: Volume multiplier for the external audio_path (0.0-1.0+).
    """
    runner = get_ffmpeg_runner()
    if not runner.is_available():
        raise RuntimeError("FFmpeg not found")

    # Use .ass for advanced styling support (colors, fonts, positioning)
    # We need to know video resolution to generate correct ASS
    # If scaling is requested, use that. Otherwise probe input.
    if scale_width > 0 and scale_height > 0:
        ass_w, ass_h = scale_width, scale_height
    else:
        # Probe primary video
        vw, vh = _get_video_resolution(runner, video_path)
        ass_w, ass_h = (vw, vh) if vw > 0 and vh > 0 else (1920, 1080)

    from src.services.subtitle_exporter import export_ass
    tmp_subs = Path(tempfile.mktemp(suffix=".ass"))
    try:
        export_ass(track, tmp_subs, video_width=ass_w, video_height=ass_h)

        # Escape path for FFmpeg subtitles filter
        subs_str = str(tmp_subs).replace("\\", "/")
        if sys.platform == "win32":
            subs_str = subs_str.replace(":", "\\:")
            # ASS filter syntax: subtitles='path'
            subs_filter = f"ass='{subs_str}'"
        else:
            subs_str = subs_str.replace(":", "\\:")
            # ASS filter syntax: ass=path
            subs_filter = f"ass={subs_str}"

        output_suffix = output_path.suffix.lower()
        encoder_plan = _build_encoder_plan(
            codec=codec,
            preset=preset,
            crf=crf,
            use_gpu=use_gpu,
            output_suffix=output_suffix,
        )
        video_encoder, encoder_flags, _ = encoder_plan[0]
        if output_suffix == ".webm":
            audio_codec_flags = ["-c:a", "libvorbis", "-b:a", audio_bitrate]
        else:
            audio_codec_flags = ["-c:a", "aac", "-b:a", audio_bitrate]

        # Determine if overlay / PIP is used
        use_overlay = overlay_path and overlay_path.exists()
        valid_image_overlays = [
            ov for ov in (image_overlays or [])
            if Path(ov.image_path).exists()
        ]
        # Multi-clip also needs filter_complex for concat
        multi_track = (
            video_tracks is not None
            and len(video_tracks) > 0
        )
        multi_source = False
        if multi_track and video_tracks:
            for vt in video_tracks:
                if vt.has_multiple_sources():
                    multi_source = True
                    break
                # Also check if any track has source different from primary
                for c in vt.clips:
                    if c.source_path and str(c.source_path) != str(video_path):
                        multi_source = True
                        break
        
        use_filter_complex = use_overlay or bool(valid_image_overlays) or multi_track or bool(text_overlays) or (audio_path and mix_with_original_audio)
        
        # NOTE: If we use filter_complex, we add subtitles at the end of the chain.
        # If simple -vf, we just use subs_filter.

        if use_filter_complex:
            # ---- Collect all inputs (multi-source: one per unique source) ----
            source_index_map: dict[str | None, int] = {}
            if multi_source and video_tracks:
                # Primary video is input 0 (source_path=None)
                input_args: list[str] = ["-i", str(video_path)]
                source_index_map[None] = 0
                next_idx = 1
                
                # Collect all unique sources from all tracks
                unique_paths = set()
                for vt in video_tracks:
                    for c in vt.clips:
                        if c.source_path:
                            unique_paths.add(str(c.source_path))
                
                for sp in sorted(list(unique_paths)):
                    if sp != str(video_path):
                        input_args.extend(["-i", sp])
                        source_index_map[sp] = next_idx
                        next_idx += 1
            else:
                input_args = ["-i", str(video_path)]
                source_index_map[None] = 0
                next_idx = 1

            template_idx = -1
            if use_overlay:
                input_args.extend(["-i", str(overlay_path)])
                template_idx = next_idx
                next_idx += 1

            img_inputs: list[tuple[int, object]] = []
            for ov in valid_image_overlays:
                input_args.extend(["-i", ov.image_path])
                img_inputs.append((next_idx, ov))
                next_idx += 1

            audio_idx = -1
            if audio_path and audio_path.exists():
                input_args.extend(["-i", str(audio_path)])
                audio_idx = next_idx
                next_idx += 1

            # ---- Build filter_complex ----
            fc_parts: list[str] = []
            
            # 1. Process each track
            track_v_labels: list[str] = []
            track_a_labels: list[str] = []
            
            norm_w = scale_width if scale_width > 0 else 0
            norm_h = scale_height if scale_height > 0 else 0
            if norm_w == 0 or norm_h == 0:
                norm_w, norm_h = _get_video_resolution(runner, video_path)
                if norm_w <= 0 or norm_h <= 0:
                    norm_w, norm_h = 1920, 1080

            # hidden 트랙 제외
            effective_tracks = [
                (i, vt) for i, vt in enumerate(video_tracks or []) if not vt.hidden
            ]

            if effective_tracks:
                for t_idx, vt in effective_tracks:
                    if not vt.clips:
                        continue

                    # Concat clips in this track
                    prefix = f"t{t_idx}"
                    parts, v_label, a_label = _build_concat_filter(
                        vt.clips, source_index_map if multi_source else None,
                        norm_w, norm_h
                    )
                    # Rename labels to avoid collisions between tracks
                    new_v = f"[{prefix}v]"
                    new_a = f"[{prefix}a]"
                    for p in parts:
                        p_mod = p.replace("[concatv]", new_v).replace("[concata]", new_a)
                        fc_parts.append(p_mod)

                    track_v_labels.append(new_v)
                    track_a_labels.append(new_a)
            else:
                fc_parts.append(f"[0:v]scale={norm_w}:{norm_h}:force_original_aspect_ratio=decrease,pad={norm_w}:{norm_h}:(ow-iw)/2:(oh-ih)/2[basev]")
                track_v_labels.append("[basev]")
                track_a_labels.append("[0:a]")
                effective_tracks = []

            # 2. Composite video tracks (블렌드 모드 + 크로마키 지원)
            current = track_v_labels[0]
            for i in range(1, len(track_v_labels)):
                _, vt = effective_tracks[i] if effective_tracks else (None, None)
                next_label = f"[comp{i}]"
                bm = getattr(vt, "blend_mode", "normal") if vt else "normal"
                if bm == "chroma_key" and vt:
                    keyed = f"[keyed{i}]"
                    color = vt.chroma_color.lstrip("#")
                    fc_parts.append(
                        f"{track_v_labels[i]}chromakey=color=0x{color}"
                        f":similarity={vt.chroma_similarity:.2f}:blend={vt.chroma_blend:.2f}{keyed}"
                    )
                    fc_parts.append(f"{current}{keyed}overlay=format=auto{next_label}")
                elif bm in ("screen", "multiply", "lighten", "darken"):
                    fc_parts.append(
                        f"{current}{track_v_labels[i]}blend=all_mode={bm}{next_label}"
                    )
                else:  # "normal"
                    fc_parts.append(f"{current}{track_v_labels[i]}overlay=format=auto{next_label}")
                current = next_label

            # 3. Mix audio tracks (muted 트랙 제외)
            unmuted_a_labels = [
                track_a_labels[i]
                for i, (_, vt) in enumerate(effective_tracks)
                if not vt.muted
            ] if effective_tracks else track_a_labels
            if not unmuted_a_labels:
                unmuted_a_labels = track_a_labels[:1]  # 최소 1개 유지

            if len(unmuted_a_labels) > 1:
                amix_in = "".join(unmuted_a_labels)
                fc_parts.append(f"{amix_in}amix=inputs={len(unmuted_a_labels)}[track_outa]")
                final_a_label = "[track_outa]"
            else:
                final_a_label = unmuted_a_labels[0]

            # Template overlay — scale to fill canvas exactly (template is designed for this ratio)
            if template_idx >= 0:
                fc_parts.append(
                    f"[{template_idx}:v]scale={norm_w}:{norm_h},format=rgba[ovr]"
                )
                fc_parts.append(f"{current}[ovr]overlay=0:0[comp]")
                current = "[comp]"

            # PIP image overlays
            if img_inputs:
                vid_w, vid_h = _get_video_resolution(runner, video_path)
                render_w = scale_width if scale_width > 0 else vid_w
                render_h = scale_height if scale_height > 0 else vid_h
                if render_w <= 0 or render_h <= 0:
                    render_w, render_h = 1920, 1080  # safe fallback

                for i, (inp_idx, ov) in enumerate(img_inputs):
                    img_w = max(16, int(render_w * ov.scale_percent / 100))
                    x = int(render_w * ov.x_percent / 100)
                    y = int(render_h * ov.y_percent / 100)
                    start_s = ov.start_ms / 1000.0
                    end_s = ov.end_ms / 1000.0

                    img_label = f"img{i}"
                    pip_label = f"pip{i}"

                    alpha_filter = ""
                    if ov.opacity < 1.0:
                        alpha_filter = f",colorchannelmixer=aa={ov.opacity:.2f}"

                    fc_parts.append(
                        f"[{inp_idx}:v]scale={img_w}:-1,format=rgba"
                        f"{alpha_filter}[{img_label}]"
                    )
                    fc_parts.append(
                        f"{current}[{img_label}]overlay={x}:{y}"
                        f":enable='between(t,{start_s:.3f},{end_s:.3f})'"
                        f"[{pip_label}]"
                    )
                    current = f"[{pip_label}]"

            # Subtitles - USING ASS FILTER
            fc_parts.append(f"{current}{subs_filter}[subbed]")
            current = "[subbed]"

            # Text overlays (after subtitles)
            if text_overlays:
                vid_w = scale_width if scale_width > 0 else 0
                vid_h = scale_height if scale_height > 0 else 0
                if vid_w <= 0 or vid_h <= 0:
                    vid_w, vid_h = _get_video_resolution(runner, video_path)
                    if vid_w <= 0 or vid_h <= 0:
                        vid_w, vid_h = 1920, 1080

                for i, to in enumerate(text_overlays):
                    # Build drawtext filter
                    text_escaped = to.text.replace("'", "'\\\\\\''")
                    text_escaped = text_escaped.replace(":", "\\:")
                    text_escaped = text_escaped.replace("%", "\\%")
                    
                    # Calculate base pixel position from percentage
                    base_x = int(vid_w * to.x_percent / 100)
                    base_y = int(vid_h * to.y_percent / 100)
                    
                    # Adjust for alignment using FFmpeg's tw (text width) and th (text height)
                    if to.alignment == "center":
                        draw_x = f"{base_x}-tw/2"
                    elif to.alignment == "right":
                        draw_x = f"{base_x}-tw"
                    else: # left
                        draw_x = str(base_x)
                        
                    if to.v_alignment == "middle":
                        draw_y = f"{base_y}-th/2"
                    elif to.v_alignment == "bottom":
                        draw_y = f"{base_y}-th"
                    else: # top
                        draw_y = str(base_y)
                    
                    # Get style properties
                    style = to.style if to.style else SubtitleStyle()
                    font_size = style.font_size
                    font_color = style.font_color.lstrip('#')
                    
                    # Convert hex color to 0xRRGGBB format
                    if len(font_color) == 6:
                        font_color = f"0x{font_color}"
                    else:
                        font_color = "0xFFFFFF"
                    
                    # Build drawtext parameters
                    start_s = to.start_ms / 1000.0
                    end_s = to.end_ms / 1000.0
                    
                    drawtext_filter = (
                        f"drawtext=text='{text_escaped}'"
                        f":fontfile=/System/Library/Fonts/Supplemental/Arial.ttf"
                        f":fontsize={font_size}"
                        f":fontcolor={font_color}"
                        f":x={draw_x}"
                        f":y={draw_y}"
                        f":alpha={to.opacity}"
                        f":enable='between(t,{start_s:.3f},{end_s:.3f})'"
                    )
                    
                    text_label = f"txt{i}"
                    fc_parts.append(f"{current}{drawtext_filter}[{text_label}]")
                    current = f"[{text_label}]"

            # Mix with external audio if present
            if audio_idx >= 0:
                # Apply volume to external audio
                fc_parts.append(f"[{audio_idx}:a]volume={audio_volume:.2f}[ext_a]")
                
                if mix_with_original_audio and final_a_label:
                    # Apply volume to video audio
                    fc_parts.append(f"{final_a_label}volume={video_volume:.2f}[vid_a]")
                    # Mix: normalize=0 prevents auto-attenuation, respecting user volumes
                    fc_parts.append(f"[vid_a][ext_a]amix=inputs=2:duration=first:normalize=0[outa]")
                    final_a_label = "[outa]"
                else:
                    final_a_label = "[ext_a]"

            # Final output
            fc_parts.append(f"{current}copy[out]")
            filter_complex = ";".join(fc_parts)

            # ---- Build command ----
            args = [*input_args,
                   "-filter_complex", filter_complex,
                   "-map", "[out]"]

            if final_a_label:
                args.extend(["-map", final_a_label,
                            "-c:v", video_encoder, *encoder_flags,
                            *audio_codec_flags])
            else:
                args.extend(["-map", "0:a?",
                            "-c:v", video_encoder, *encoder_flags,
                            "-c:a", "copy"])

            args.extend(["-y", "-progress", "pipe:1", str(output_path)])
            
            log_ffmpeg_command(args)

        else:
            # simple -vf filter chain
            vf_parts: list[str] = []
            if scale_width > 0 and scale_height > 0:
                vf_parts.append(
                    f"scale={scale_width}:{scale_height}"
                    f":force_original_aspect_ratio=decrease,"
                    f"pad={scale_width}:{scale_height}:(ow-iw)/2:(oh-ih)/2"
                )
            vf_parts.append(subs_filter)
            vf_string = ",".join(vf_parts)

            if audio_path and audio_path.exists():
                args = [
                    "-i", str(video_path),
                    "-i", str(audio_path),
                    "-vf", vf_string,
                    "-map", "0:v",
                    "-map", "1:a",
                    "-c:v", video_encoder,
                    *encoder_flags,
                    *audio_codec_flags,
                    "-y",
                    "-progress", "pipe:1",
                    str(output_path),
                ]
            else:
                args = [
                    "-i", str(video_path),
                    "-vf", vf_string,
                    "-c:v", video_encoder,
                    *encoder_flags,
                    "-c:a", "copy",
                    "-y",
                    "-progress", "pipe:1",
                    str(output_path),
                ]

        def _replace_video_encoder_args(
            command: list[str],
            new_encoder: str,
            new_flags: list[str],
        ) -> list[str]:
            updated = list(command)
            idx = updated.index("-c:v")
            updated[idx + 1] = new_encoder
            try:
                end_idx = updated.index("-c:a", idx + 2)
            except ValueError:
                end_idx = updated.index("-y", idx + 2)
            updated[idx + 2:end_idx] = new_flags
            return updated

        def _emit_status(event: dict[str, Any]) -> None:
            if not on_status:
                return
            wants_structured = bool(getattr(on_status, "__fmm_status_format__", "") == "structured")
            payload: Any = event if wants_structured else _status_event_to_message(event)
            try:
                on_status(payload)
            except Exception:
                pass

        # Parse -progress output against target duration
        if multi_track and video_tracks:
            total_duration = max((vt.output_duration_ms for vt in video_tracks), default=0) / 1000.0
        else:
            total_duration = _get_video_duration(runner, video_path)

        def _run_once(command: list[str]) -> tuple[int, str]:
            log_ffmpeg_command(command)
            process = runner.run_async(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            stderr_chunks: list[str] = []

            def _drain_stderr():
                try:
                    for line in process.stderr:
                        log_ffmpeg_line(line)
                        stderr_chunks.append(line)
                except Exception:
                    pass

            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            if process.stdout:
                for line in process.stdout:
                    line = line.strip()
                    if line.startswith("out_time_us="):
                        try:
                            us = int(line.split("=")[1])
                            current_sec = us / 1_000_000
                            if on_progress and total_duration > 0:
                                on_progress(total_duration, current_sec)
                        except (ValueError, IndexError):
                            pass

            process.wait()
            stderr_thread.join(timeout=10)
            return process.returncode, "".join(stderr_chunks)

        current_args = list(args)
        last_stderr = ""
        return_code = 1

        for idx, (candidate_encoder, candidate_flags, is_hw_encoder) in enumerate(encoder_plan):
            if idx == 0:
                current_args = _replace_video_encoder_args(args, candidate_encoder, candidate_flags)
            else:
                current_args = _replace_video_encoder_args(current_args, candidate_encoder, candidate_flags)

            if use_gpu and is_hw_encoder:
                _emit_status({"type": "probe", "encoder": candidate_encoder})

            return_code, stderr = _run_once(current_args)
            last_stderr = stderr
            if return_code == 0:
                _emit_status({"type": "final_encoder", "encoder": candidate_encoder})
                break

            if not use_gpu or not is_hw_encoder:
                break

            if not _looks_like_hw_failure(stderr):
                break

            output_path.unlink(missing_ok=True)
            next_encoder = encoder_plan[idx + 1][0] if idx + 1 < len(encoder_plan) else None
            if next_encoder:
                _emit_status(
                    {
                        "type": "retry",
                        "encoder": candidate_encoder,
                        "reason": (stderr or "").splitlines()[0][:120] if stderr else "unknown error",
                        "next_encoder": next_encoder,
                    }
                )
                continue
            break

        if return_code != 0:
            raise RuntimeError(f"FFmpeg failed (code {return_code}): {last_stderr[:500]}")

    finally:
        tmp_subs.unlink(missing_ok=True)


def _get_video_resolution(runner: "FFmpegRunner", video_path: Path) -> tuple[int, int]:
    """Get video width and height using ffprobe."""
    try:
        result = runner.run_ffprobe(
            [
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                str(video_path),
            ],
            timeout=10,
        )
        if result.stdout:
            parts = result.stdout.strip().split("x")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 0, 0


def _get_video_duration(runner: "FFmpegRunner", video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        result = runner.run_ffprobe(
            [
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            timeout=10,
        )
        if result.stdout:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0
