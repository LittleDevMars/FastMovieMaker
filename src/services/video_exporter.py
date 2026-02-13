"""Export video with hard-burned subtitles via FFmpeg."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from src.models.subtitle import SubtitleTrack
from src.models.video_clip import VideoClipTrack
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
            idx = source_index_map.get(clip.source_path, 0)
        else:
            idx = 0
        start_s = clip.source_in_ms / 1000.0
        end_s = clip.source_out_ms / 1000.0
        vl = f"cv{i}"
        al = f"ca{i}"

        v_filter = f"[{idx}:v]trim=start={start_s:.3f}:end={end_s:.3f},setpts=PTS-STARTPTS"
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
        a_filter += f"[{al}]"
        parts.append(a_filter)
        v_labels.append(f"[{vl}]")
        a_labels.append(f"[{al}]")

    concat_in = "".join(v_labels[j] + a_labels[j] for j in range(len(clips)))
    parts.append(f"{concat_in}concat=n={len(clips)}:v=1:a=1[concatv][concata]")
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
            # VP9 doesn't use -preset typically like x264, but has -cpu-used
            # We'll map preset loosely or just ignore for VP9 to keep it simple
            encoder_flags = ["-crf", str(crf), "-b:v", "0"]
            audio_codec_flags = ["-c:a", "libvorbis", "-b:a", "128k"]
        else:
            # H.264 / HEVC
            # Hardware encoders might not support -crf or -preset the same way.
            # safe assumption: use libx264/libx265 if HW accel is tricky with CRF/Preset.
            # But get_hw_encoder might return h264_videotoolbox on mac.
            # h264_videotoolbox supports -q:v (quality) but not CRF.
            # Let's try to stick to standard software encoders if user wants precise CRF/Preset control?
            # Or try to map arguments.
            
            # For now, let's prioritize the user's explicit codec choice over auto-detection if possible,
            # OR just append flags and hope ffmpeg maps them (it usually doesn't for HW encoders).
            
            # If we want to support Preset/CRF reliably, software encoding (libx264/libx265) is safer.
            # But it's slower.
            # Let's try standard get_hw_encoder, but if it returns libx264/libx265, add preset/crf.
            # If it returns hardware encoder (e.g. h264_nvenc, h264_videotoolbox), we might need specific flags.
            
            # MacOS VideoToolbox: -q:v (0-100), no -preset usually.
            # NVENC: -cq, -preset (p1-p7).
            
            # heuristic: if we want extended control, maybe force software?
            # For this feature "Advanced Export", users might expect CPU encoding reliability.
            # bit let's try to be smart.
            
            if codec == "h264":
                video_encoder = "libx264"
            elif codec == "hevc":
                video_encoder = "libx265"
            else:
                video_encoder = "libx264"
                
            encoder_flags = [
                "-preset", preset,
                "-crf", str(crf),
                "-pix_fmt", "yuv420p"  # Ensure compatibility
            ]
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

            # Subtitles (last in chain) - USING ASS FILTER
            fc_parts.append(f"{current}{subs_filter}[out]")
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
