"""
Audio regeneration service for timeline editing.
Regenerates merged audio when segment timing changes.
"""
from pathlib import Path
from typing import List
import tempfile
import shutil

from src.services.settings_manager import SettingsManager
from src.services.ffmpeg_logger import log_ffmpeg_command
from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner
from src.models.subtitle import SubtitleTrack


class AudioRegenerator:
    """Regenerates audio files when segment timing changes."""

    @staticmethod
    def regenerate_track_audio(
        track: SubtitleTrack,
        output_path: Path,
        video_audio_path: Path | None = None,
        bg_volume: float = 0.5,
        tts_volume: float = 1.0,
        apply_segment_volumes: bool = True,
    ) -> tuple[Path, int]:
        """
        Regenerate merged audio file based on current segment timing.

        Args:
            track: SubtitleTrack with segments containing audio_file paths
            output_path: Where to save the regenerated merged audio
            video_audio_path: Optional background audio to mix with
            bg_volume: Background audio volume (0.0-1.0)
            tts_volume: TTS audio volume (0.0-1.0)
            apply_segment_volumes: Whether to apply per-segment volume settings

        Returns:
            tuple[Path, int]: (output_path, total_duration_ms)

        Raises:
            ValueError: If segments don't have audio files
            RuntimeError: If FFmpeg command fails
        """
        # Check if segments have audio files
        audio_segments = [seg for seg in track.segments if seg.audio_file]
        if not audio_segments:
            raise ValueError("No audio files found in segments")

        # Create temporary directory for intermediate files
        temp_dir = Path(tempfile.mkdtemp(prefix="audio_regen_"))

        try:
            # Step 1: Create timeline with audio segments and silence gaps
            timeline_file = temp_dir / "timeline.txt"
            tts_audio = AudioRegenerator._create_timeline_audio(
                segments=audio_segments,
                temp_dir=temp_dir,
                timeline_file=timeline_file,
                apply_segment_volumes=apply_segment_volumes,
            )

            # Calculate total duration
            total_duration_ms = max(seg.end_ms for seg in audio_segments)

            # Step 2: Mix with background audio if provided
            if video_audio_path and video_audio_path.exists():
                from src.services.audio_merger import AudioMerger
                AudioMerger.mix_audio_tracks(
                    track1_path=video_audio_path,
                    track2_path=tts_audio,
                    output_path=output_path,
                    track1_volume=bg_volume,
                    track2_volume=tts_volume
                )
            else:
                # Just copy the TTS audio
                shutil.copy2(tts_audio, output_path)

            return output_path, total_duration_ms

        finally:
            # Cleanup temporary directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _create_timeline_audio(
        segments: List,
        temp_dir: Path,
        timeline_file: Path,
        apply_segment_volumes: bool = True,
    ) -> Path:
        """
        Create audio file with segments positioned at their timeline positions.

        Uses FFmpeg concat with silence padding to position audio segments
        at exact timeline positions.

        Args:
            segments: List of SubtitleSegment with audio_file paths
            temp_dir: Temporary directory for intermediate files
            timeline_file: Path to write the concat file list
            apply_segment_volumes: Whether to apply per-segment volume settings
        """
        runner = get_ffmpeg_runner()
        if not runner.is_available():
            raise RuntimeError("FFmpeg not found")

        sorted_segments = sorted(segments, key=lambda s: s.start_ms)

        silence_file = temp_dir / "silence.mp3"
        silence_args = [
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "1",
            "-q:a", "9",
            "-acodec", "libmp3lame",
            "-y",
            str(silence_file),
        ]
        log_ffmpeg_command(silence_args)
        runner.run(silence_args, check=True)

        # Build concat list with audio segments and silence gaps
        concat_list = []
        current_time_ms = 0

        for i, seg in enumerate(sorted_segments):
            # Add silence gap if needed
            gap_ms = seg.start_ms - current_time_ms
            if gap_ms > 0:
                # Calculate number of silence segments needed (1s each)
                num_silence = int(gap_ms / 1000)
                for _ in range(num_silence):
                    concat_list.append(f"file '{silence_file}'")

                # Add fractional silence if needed
                remaining_ms = gap_ms % 1000
                if remaining_ms > 50:
                    frac_silence = temp_dir / f"silence_{i}_frac.mp3"
                    frac_args = [
                        "-f", "lavfi",
                        "-i", "anullsrc=r=44100:cl=stereo",
                        "-t", f"{remaining_ms/1000:.3f}",
                        "-q:a", "9",
                        "-acodec", "libmp3lame",
                        "-y",
                        str(frac_silence),
                    ]
                    log_ffmpeg_command(frac_args)
                    runner.run(frac_args, check=True)
                    concat_list.append(f"file '{frac_silence}'")

            # Add audio segment (with optional volume adjustment)
            if seg.audio_file and Path(seg.audio_file).exists():
                audio_file_path = seg.audio_file
                
                # 속도 및 볼륨 처리 필요 여부 확인
                has_speed = hasattr(seg, 'speed') and seg.speed is not None and seg.speed != 1.0
                has_volume = apply_segment_volumes and hasattr(seg, 'volume') and seg.volume != 1.0
                
                if has_speed or has_volume:
                    processed_file = temp_dir / f"proc_{i}.mp3"
                    filters = []
                    
                    # 1. 볼륨 필터 추가
                    if has_volume:
                        filters.append(f"volume={seg.volume:.2f}")
                    
                    # 2. 속도 필터 추가
                    settings = SettingsManager()
                    pitch_shift_enabled = settings.get_audio_speed_pitch_shift()

                    if has_speed:
                        if pitch_shift_enabled:
                            filters.append(f"asetpts=PTS/{seg.speed:.3f}") # Change audio timing and pitch
                        else: # Pitch-preserving
                            s = seg.speed
                            while s > 2.0:
                                filters.append("atempo=2.0")
                                s /= 2.0
                            while s < 0.5:
                                filters.append("atempo=0.5")
                                s /= 0.5
                            filters.append(f"atempo={s:.3f}")
                    
                    proc_args = [
                        "-i", str(seg.audio_file),
                        "-af", ",".join(filters),
                        "-q:a", "2",
                        "-y",
                        str(processed_file),
                    ]
                    log_ffmpeg_command(proc_args)
                    runner.run(proc_args, check=True)
                    audio_file_path = str(processed_file)

                concat_list.append(f"file '{audio_file_path}'")
                current_time_ms = seg.end_ms
            else:
                # If audio file missing, add silence for segment duration
                duration_s = (seg.end_ms - seg.start_ms) / 1000
                missing_silence = temp_dir / f"missing_{i}.mp3"
                missing_args = [
                    "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", f"{duration_s:.3f}",
                    "-q:a", "9",
                    "-acodec", "libmp3lame",
                    "-y",
                    str(missing_silence),
                ]
                log_ffmpeg_command(missing_args)
                runner.run(missing_args, check=True)
                concat_list.append(f"file '{missing_silence}'")
                current_time_ms = seg.end_ms

        # Write concat file
        timeline_file.write_text("\n".join(concat_list), encoding="utf-8")

        output_audio = temp_dir / "merged.mp3"
        merge_args = [
            "-f", "concat",
            "-safe", "0",
            "-i", str(timeline_file),
            "-c", "copy",
            "-y",
            str(output_audio),
        ]
        log_ffmpeg_command(merge_args)
        result = runner.run(merge_args)
        if result.returncode != 0:
            fallback_args = [
                "-f", "concat",
                "-safe", "0",
                "-i", str(timeline_file),
                "-q:a", "2",
                "-y",
                str(output_audio),
            ]
            log_ffmpeg_command(fallback_args)
            runner.run(fallback_args, check=True)

        return output_audio
