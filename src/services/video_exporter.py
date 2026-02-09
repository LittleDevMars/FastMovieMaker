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
        if need_scale:
            v_filter += (
                f",scale={out_w}:{out_h}:force_original_aspect_ratio=decrease"
                f",pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
            )
        v_filter += f"[{vl}]"
        parts.append(v_filter)

        parts.append(
            f"[{idx}:a]atrim=start={start_s:.3f}:end={end_s:.3f},asetpts=PTS-STARTPTS[{al}]"
        )
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
    overlay_path: Path | None = None,
    image_overlays: list | None = None,
    video_clips: VideoClipTrack | None = None,
) -> None:
    """Burn subtitles into video using FFmpeg's subtitles filter.

    Args:
        video_path: Source video file.
        track: Subtitle track to burn.
        output_path: Destination video file.
        on_progress: Optional callback(duration_sec, current_sec) for progress.
        audio_path: Optional path to replacement audio file (e.g. TTS mixed audio).
                    When provided, replaces the original audio with this file.
        scale_width: Target width in pixels (0 = keep original).
        scale_height: Target height in pixels (0 = keep original).
        codec: Video codec - "h264" or "hevc" (default "h264").
        overlay_path: Optional path to overlay PNG image (transparent) to composite on video.
        image_overlays: Optional list of ImageOverlay objects for PIP compositing.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found")

    # Write a temporary SRT file
    tmp_srt = Path(tempfile.mktemp(suffix=".srt"))
    try:
        export_srt(track, tmp_srt)

        # Escape path for FFmpeg subtitles filter
        srt_str = str(tmp_srt).replace("\\", "/")
        if sys.platform == "win32":
            srt_str = srt_str.replace(":", "\\:")
            srt_filter = f"subtitles='{srt_str}'"
        else:
            # On macOS/Linux, escape colons and use without quotes
            srt_str = srt_str.replace(":", "\\:")
            srt_filter = f"subtitles={srt_str}"

        # Determine encoder based on output container
        from src.utils.hw_accel import get_hw_encoder

        if output_path.suffix.lower() == ".webm":
            video_encoder = "libvpx-vp9"
            encoder_flags = ["-crf", "30", "-b:v", "0"]
            audio_codec_flags = ["-c:a", "libvorbis", "-b:a", "128k"]
        else:
            video_encoder, encoder_flags = get_hw_encoder(codec)
            audio_codec_flags = ["-c:a", "aac", "-b:a", "192k"]

        # Determine if overlay / PIP is used
        use_overlay = overlay_path and overlay_path.exists()
        valid_image_overlays = [
            ov for ov in (image_overlays or [])
            if Path(ov.image_path).exists()
        ]
        # Multi-clip also needs filter_complex for concat
        multi_clip = (
            video_clips is not None
            and len(video_clips.clips) > 1
        )
        multi_source = (
            multi_clip
            and video_clips is not None
            and video_clips.has_multiple_sources()
        )
        use_filter_complex = use_overlay or bool(valid_image_overlays) or multi_clip

        if use_filter_complex:
            # ---- Collect all inputs (multi-source: one per unique source) ----
            source_index_map: dict[str | None, int] = {}
            if multi_source and video_clips is not None:
                # Primary video is input 0 (source_path=None)
                input_args: list[str] = ["-i", str(video_path)]
                source_index_map[None] = 0
                next_idx = 1
                for sp in video_clips.unique_source_paths():
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
            concat_audio_label = ""

            # Multi-clip concat (trim + concat)
            if multi_clip:
                if multi_source:
                    # Get output resolution for normalization
                    norm_w = scale_width if scale_width > 0 else 0
                    norm_h = scale_height if scale_height > 0 else 0
                    if norm_w == 0 or norm_h == 0:
                        norm_w, norm_h = _get_video_resolution(ffmpeg, video_path)
                        if norm_w <= 0 or norm_h <= 0:
                            norm_w, norm_h = 1920, 1080
                    concat_parts, v_label, a_label = _build_concat_filter(
                        video_clips.clips, source_index_map, norm_w, norm_h,
                    )
                else:
                    concat_parts, v_label, a_label = _build_concat_filter(
                        video_clips.clips,
                    )
                fc_parts.extend(concat_parts)
                current = v_label  # e.g. "[concatv]"
                concat_audio_label = a_label  # e.g. "[concata]"
            else:
                current = "[0:v]"

            # Scale video if needed
            if scale_width > 0 and scale_height > 0:
                src = current
                fc_parts.append(
                    f"{src}scale={scale_width}:{scale_height}"
                    f":force_original_aspect_ratio=decrease,"
                    f"pad={scale_width}:{scale_height}:(ow-iw)/2:(oh-ih)/2[scaled]"
                )
                current = "[scaled]"

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

            # Subtitles (last in chain)
            fc_parts.append(f"{current}{srt_filter}[out]")
            filter_complex = ";".join(fc_parts)

            # ---- Build command ----
            cmd = [ffmpeg, *input_args,
                   "-filter_complex", filter_complex,
                   "-map", "[out]"]

            if audio_idx >= 0:
                cmd.extend(["-map", f"{audio_idx}:a",
                            "-c:v", video_encoder, *encoder_flags,
                            *audio_codec_flags])
            elif concat_audio_label:
                # Multi-clip: audio from concat filter
                cmd.extend(["-map", concat_audio_label,
                            "-c:v", video_encoder, *encoder_flags,
                            *audio_codec_flags])
            else:
                cmd.extend(["-map", "0:a?",
                            "-c:v", video_encoder, *encoder_flags,
                            "-c:a", "copy"])

            cmd.extend(["-y", "-progress", "pipe:1", str(output_path)])

        else:
            # No overlay, no image overlays — use simple -vf filter chain
            vf_parts: list[str] = []
            if scale_width > 0 and scale_height > 0:
                vf_parts.append(
                    f"scale={scale_width}:{scale_height}"
                    f":force_original_aspect_ratio=decrease,"
                    f"pad={scale_width}:{scale_height}:(ow-iw)/2:(oh-ih)/2"
                )
            vf_parts.append(srt_filter)
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

        # Drain stderr in a background thread to prevent pipe buffer deadlock.
        # FFmpeg writes verbose per-frame stats to stderr; if the pipe buffer
        # fills up (4 KB on Windows), FFmpeg blocks and stdout stalls too.
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
        if multi_clip:
            total_duration = video_clips.output_duration_ms / 1000.0
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
        tmp_srt.unlink(missing_ok=True)


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
