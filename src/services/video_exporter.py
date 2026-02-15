"""Export video with hard-burned subtitles via FFmpeg."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from src.models.subtitle import SubtitleTrack
from src.models.style import SubtitleStyle
from src.models.video_clip import VideoClipTrack
from src.models.text_overlay import TextOverlay
from src.services.subtitle_exporter import export_srt
from src.utils.config import find_ffmpeg


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

        v_filter = f"[{idx}:v]trim=start={start_s:.3f}:end={end_s:.3f},setpts=PTS-STARTPTS"
        
        # Apply visual filters (Brightness, Contrast, Saturation)
        if clip.brightness != 1.0 or clip.contrast != 1.0 or clip.saturation != 1.0:
            # Map model values to FFmpeg eq filter values
            # brightness: model 1.0 -> ffmpeg 0.0
            f_bri = clip.brightness - 1.0
            v_filter += f",eq=brightness={f_bri:.2f}:contrast={clip.contrast:.2f}:saturation={clip.saturation:.2f}"

        if hasattr(clip, "speed") and clip.speed != 1.0:
            v_filter += f",setpts=PTS/{clip.speed:.3f}"
        if need_scale:
            v_filter += (
                f",scale={out_w}:{out_h}:force_original_aspect_ratio=decrease"
                f",pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
            )
        v_filter += f"[{vl}]"
        parts.append(v_filter)

        a_filter = f"[{idx}:a]atrim=start={start_s:.3f}:end={end_s:.3f},asetpts=PTS-STARTPTS"
        if hasattr(clip, "speed") and clip.speed != 1.0:
            speed = clip.speed
            while speed > 2.0:
                a_filter += ",atempo=2.0"
                speed /= 2.0
            while speed < 0.5:
                a_filter += ",atempo=0.5"
                speed /= 0.5
            a_filter += f",atempo={speed:.3f}"
        
        if hasattr(clip, "volume_points") and clip.volume_points:
            pts = sorted(clip.volume_points, key=lambda p: p.offset_ms)
            if pts:
                # Build nested IF expression for linear interpolation
                # volume='if(lte(t,t0), v0, if(lte(t,t1), v0+(v1-v0)*(t-t0)/(t1-t0), ...))'
                expr = f"{pts[-1].volume:.3f}" # Default to last value
                for j in range(len(pts) - 1, 0, -1):
                    p1 = pts[j-1]
                    p2 = pts[j]
                    t1, v1 = p1.offset_ms / 1000.0, p1.volume
                    t2, v2 = p2.offset_ms / 1000.0, p2.volume
                    if t2 > t1:
                        # Interpolation formula: v1 + (v2-v1)*(t-t1)/(t2-t1)
                        seg_expr = f"{v1:.3f}+({v2-v1:.3f})*(t-{t1:.3f})/({t2-t1:.3f})"
                        expr = f"if(lte(t,{t2:.3f}),{seg_expr},{expr})"
                
                # Handling before first point
                t0, v0 = pts[0].offset_ms / 1000.0, pts[0].volume
                expr = f"if(lte(t,{t0:.3f}),{v0:.3f},{expr})"
                
                a_filter += f",volume='{expr}'"
        elif hasattr(clip, "volume") and clip.volume != 1.0:
            a_filter += f",volume={clip.volume:.3f}"
            
        a_filter += f"[{al}]"
        parts.append(a_filter)
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
            dur_s = trans.duration_ms / 1000.0
            # xfade: offset is when the transition STARTS
            offset_s = (curr_total_ms - trans.duration_ms) / 1000.0
            parts.append(f"[{curr_v}][{next_v}]xfade=transition={trans.type}:duration={dur_s:.3f}:offset={offset_s:.3f}[{out_v}]")
            # acrossfade: d is duration
            parts.append(f"[{curr_a}][{next_a}]acrossfade=d={dur_s:.3f}:c1=tri:c2=tri[{out_a}]")
            curr_total_ms += clip_b.duration_ms - trans.duration_ms
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


def export_video(
    video_path: Path,
    track: SubtitleTrack,
    output_path: Path,
    on_progress: callable | None = None,
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
) -> None:
    """Burn subtitles into video using FFmpeg's subtitles filter.

    Args:
        video_path: Source video file.
        track: Subtitle track to burn.
        output_path: Destination video file.
        on_progress: Optional callback(duration_sec, current_sec) for progress.
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
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found")

    # Use .ass for advanced styling support (colors, fonts, positioning)
    # We need to know video resolution to generate correct ASS
    # If scaling is requested, use that. Otherwise probe input.
    if scale_width > 0 and scale_height > 0:
        ass_w, ass_h = scale_width, scale_height
    else:
        # Probe primary video
        vw, vh = _get_video_resolution(ffmpeg, video_path)
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

        # Determine encoder based on output container
        from src.utils.hw_accel import get_hw_encoder

        if output_path.suffix.lower() == ".webm":
            video_encoder = "libvpx-vp9"
            encoder_flags = ["-crf", str(crf), "-b:v", "0"]
            audio_codec_flags = ["-c:a", "libvorbis", "-b:a", "128k"]
        else:
            # Determine encoder and flags based on GPU preference
            from src.utils.hw_accel import get_hw_encoder
            
            if use_gpu:
                hw_encoder, hw_flags = get_hw_encoder(codec)
                video_encoder = hw_encoder
                encoder_flags = hw_flags
                
                # If using HW, we might need to adjust flags based on specific encoder
                if "videotoolbox" in hw_encoder:
                    # VideoToolbox quality is 0-100, where 100 is best.
                    # CRF 23 is roughly 65-70 quality.
                    quality = int(max(0, min(100, 100 - (crf * 1.5)))) # Very loose mapping
                    encoder_flags = ["-q:v", str(int(quality)), "-realtime", "0"]
                elif "nvenc" in hw_encoder:
                    # NVENC supports -cq and -preset
                    encoder_flags = ["-preset", "p4", "-cq", str(crf)]
                elif "vaapi" in hw_encoder or "amf" in hw_encoder:
                    # Standard HW flags from get_hw_encoder
                    pass
            else:
                if codec == "h264":
                    video_encoder = "libx264"
                elif codec == "hevc":
                    video_encoder = "libx265"
                else:
                    video_encoder = "libx264"
                
                encoder_flags = [
                    "-preset", preset,
                    "-crf", str(crf),
                ]

            encoder_flags.extend(["-pix_fmt", "yuv420p"])
            audio_codec_flags = ["-c:a", "aac", "-b:a", "192k"]

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
        
        use_filter_complex = use_overlay or bool(valid_image_overlays) or multi_track
        
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
                norm_w, norm_h = _get_video_resolution(ffmpeg, video_path)
                if norm_w <= 0 or norm_h <= 0:
                    norm_w, norm_h = 1920, 1080

            if video_tracks:
                for t_idx, vt in enumerate(video_tracks):
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
                    # We need to manually adjust label names in parts or just wrap
                    # Actually _build_concat_filter uses [concatv][concata] at the end.
                    for p in parts:
                        p_mod = p.replace("[concatv]", new_v).replace("[concata]", new_a)
                        fc_parts.append(p_mod)
                    
                    track_v_labels.append(new_v)
                    track_a_labels.append(new_a)
            else:
                fc_parts.append(f"[0:v]scale={norm_w}:{norm_h}:force_original_aspect_ratio=decrease,pad={norm_w}:{norm_h}:(ow-iw)/2:(oh-ih)/2[basev]")
                track_v_labels.append("[basev]")
                track_a_labels.append("[0:a]")

            # 2. Composite video tracks (overlay)
            current = track_v_labels[0]
            for i in range(1, len(track_v_labels)):
                next_label = f"[comp{i}]"
                fc_parts.append(f"{current}{track_v_labels[i]}overlay=format=auto{next_label}")
                current = next_label

            # 3. Mix audio tracks
            if len(track_a_labels) > 1:
                amix_in = "".join(track_a_labels)
                fc_parts.append(f"{amix_in}amix=inputs={len(track_a_labels)}[outa]")
                final_a_label = "[outa]"
            else:
                final_a_label = track_a_labels[0]

            # Template overlay
            if template_idx >= 0:
                if scale_width > 0 and scale_height > 0:
                    fc_parts.append(
                        f"[{template_idx}:v]scale={scale_width}:{scale_height}"
                        f":force_original_aspect_ratio=decrease[ovr]"
                    )
                    fc_parts.append(f"{current}[ovr]overlay=(W-w)/2:(H-h)/2[comp]")
                else:
                    fc_parts.append(
                        f"{current}[{template_idx}:v]overlay=(W-w)/2:(H-h)/2[comp]"
                    )
                current = "[comp]"

            # PIP image overlays
            if img_inputs:
                vid_w, vid_h = _get_video_resolution(ffmpeg, video_path)
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
                    vid_w, vid_h = _get_video_resolution(ffmpeg, video_path)
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

            # Final output
            fc_parts.append(f"{current}copy[out]")
            filter_complex = ";".join(fc_parts)

            # ---- Build command ----
            cmd = [ffmpeg, *input_args,
                   "-filter_complex", filter_complex,
                   "-map", "[out]"]

            if audio_idx >= 0:
                # Mixing with external audio might need amix or just replacement
                # For now let's assume external audio overrides all track audio 
                # (consistent with previous behavior for simplification)
                cmd.extend(["-map", f"{audio_idx}:a",
                            "-c:v", video_encoder, *encoder_flags,
                            *audio_codec_flags])
            elif final_a_label:
                cmd.extend(["-map", final_a_label,
                            "-c:v", video_encoder, *encoder_flags,
                            *audio_codec_flags])
            else:
                cmd.extend(["-map", "0:a?",
                            "-c:v", video_encoder, *encoder_flags,
                            "-c:a", "copy"])

            cmd.extend(["-y", "-progress", "pipe:1", str(output_path)])

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
                cmd = [
                    ffmpeg,
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
                cmd = [
                    ffmpeg,
                    "-i", str(video_path),
                    "-vf", vf_string,
                    "-c:v", video_encoder,
                    *encoder_flags,
                    "-c:a", "copy",
                    "-y",
                    "-progress", "pipe:1",
                    str(output_path),
                ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # Drain stderr in a background thread
        stderr_chunks: list[str] = []

        def _drain_stderr():
            try:
                for line in process.stderr:
                    stderr_chunks.append(line)
            except Exception:
                pass

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # Parse -progress output for duration tracking
        if multi_track and video_tracks:
            total_duration = max((vt.output_duration_ms for vt in video_tracks), default=0) / 1000.0
        else:
            total_duration = _get_video_duration(ffmpeg, video_path)

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

        if process.returncode != 0:
            stderr = "".join(stderr_chunks)
            raise RuntimeError(f"FFmpeg failed (code {process.returncode}): {stderr[:500]}")

    finally:
        tmp_subs.unlink(missing_ok=True)


def _get_video_resolution(ffmpeg: str, video_path: Path) -> tuple[int, int]:
    """Get video width and height using ffprobe."""
    ffprobe = str(Path(ffmpeg).parent / "ffprobe.exe")
    if not Path(ffprobe).is_file():
        ffprobe = str(Path(ffmpeg).parent / "ffprobe")
    if not Path(ffprobe).is_file():
        return 0, 0

    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        parts = result.stdout.strip().split("x")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 0, 0


def _get_video_duration(ffmpeg: str, video_path: Path) -> float:
    """Get video duration in seconds using ffprobe or FFmpeg."""
    ffprobe = str(Path(ffmpeg).parent / "ffprobe.exe")
    if not Path(ffprobe).is_file():
        ffprobe = str(Path(ffmpeg).parent / "ffprobe")
    if not Path(ffprobe).is_file():
        return 0.0

    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0
