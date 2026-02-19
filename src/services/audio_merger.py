"""
Audio merger service using FFmpeg for concatenating and mixing audio tracks.
"""
from pathlib import Path
from typing import List
import json
import tempfile

from src.infrastructure.ffmpeg_runner import get_ffmpeg_runner


class AudioMerger:
    """Service for merging and mixing audio files using FFmpeg."""

    @staticmethod
    def get_audio_duration(audio_path: Path) -> float:
        """
        Get the duration of an audio file using FFprobe.

        Args:
            audio_path: Path to the audio file

        Returns:
            Duration in seconds

        Raises:
            FileNotFoundError: If audio file doesn't exist
            Exception: If FFprobe fails
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        runner = get_ffmpeg_runner()
        if not runner.ffprobe_path:
            raise Exception("FFprobe not found")

        try:
            result = runner.run_ffprobe(
                [
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    str(audio_path),
                ],
                check=True,
            )
            data = json.loads(result.stdout)
            duration = float(data["format"]["duration"])
            return duration
        except Exception as e:
            if "FFprobe" in str(e) or "ffprobe" in str(e).lower():
                raise Exception(f"FFprobe failed: {e}") from e
            raise
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            raise Exception(f"Failed to parse FFprobe output: {e}")

    @staticmethod
    def merge_audio_files(
        audio_files: List[Path],
        output_path: Path,
        add_silence_ms: int = 0,
        volumes: List[float] | None = None,
    ) -> Path:
        """
        Merge multiple audio files into one using FFmpeg.

        Args:
            audio_files: List of audio file paths (in order)
            output_path: Where to save the merged audio
            add_silence_ms: Milliseconds of silence to add between segments
            volumes: Optional per-file volume multipliers (0.0~2.0).
                     If provided, must match length of audio_files.

        Returns:
            Path to the output file

        Raises:
            ValueError: If audio_files is empty
            Exception: If FFmpeg fails
        """
        if not audio_files:
            raise ValueError("audio_files cannot be empty")

        runner = get_ffmpeg_runner()
        if not runner.is_available():
            raise Exception("FFmpeg not found")

        needs_volume = volumes and any(v != 1.0 for v in volumes)

        if needs_volume:
            return AudioMerger._merge_with_volumes(
                runner, audio_files, output_path, volumes
            )

        # Create temporary concat file (simple concat, no volume changes)
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False,
            encoding='utf-8'
        ) as f:
            concat_file = Path(f.name)

            for audio_file in audio_files:
                if not audio_file.exists():
                    raise FileNotFoundError(f"Audio file not found: {audio_file}")
                # Use absolute path and escape quotes
                f.write(f"file '{audio_file.absolute()}'\n")

                # Add silence between segments if requested
                if add_silence_ms > 0 and audio_file != audio_files[-1]:
                    # Generate silence using anullsrc
                    silence_duration = add_silence_ms / 1000.0
                    f.write(f"file 'anullsrc=d={silence_duration}'\n")

        try:
            runner.run(
                [
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_file),
                    "-c", "copy",
                    "-y",
                    str(output_path),
                ],
                check=True,
            )
            return output_path
        except Exception as e:
            raise Exception(f"FFmpeg merge failed: {e}") from e

        finally:
            # Clean up temp file
            if concat_file.exists():
                concat_file.unlink()

    @staticmethod
    def _merge_with_volumes(
        runner,
        audio_files: List[Path],
        output_path: Path,
        volumes: List[float],
    ) -> Path:
        """Merge audio files with per-file volume using FFmpeg filter_complex."""
        args = []
        for audio_file in audio_files:
            if not audio_file.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_file}")
            args.extend(["-i", str(audio_file)])

        parts = []
        for i, vol in enumerate(volumes):
            parts.append(f"[{i}:a]volume={vol:.2f}[a{i}]")

        concat_inputs = "".join(f"[a{i}]" for i in range(len(audio_files)))
        parts.append(f"{concat_inputs}concat=n={len(audio_files)}:v=0:a=1[out]")

        filter_complex = ";".join(parts)
        args.extend(["-filter_complex", filter_complex, "-map", "[out]", "-y", str(output_path)])

        try:
            runner.run(args, check=True)
            return output_path
        except Exception as e:
            raise Exception(f"FFmpeg merge with volumes failed: {e}") from e

    @staticmethod
    def has_audio_stream(file_path: Path) -> bool:
        """
        Check if a file has an audio stream.

        Args:
            file_path: Path to the media file

        Returns:
            True if the file has an audio stream, False otherwise
        """
        runner = get_ffmpeg_runner()
        if not runner.ffprobe_path:
            return False

        try:
            result = runner.run_ffprobe(
                [
                    "-v", "quiet",
                    "-select_streams", "a:0",
                    "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0",
                    str(file_path),
                ],
                check=True,
            )
            return result.stdout.strip() == "audio"
        except Exception:
            return False

    @staticmethod
    def mix_audio_tracks(
        track1_path: Path,
        track2_path: Path,
        output_path: Path,
        track1_volume: float | str = 0.5,
        track2_volume: float = 1.0
    ) -> Path:
        """
        Mix two audio tracks with volume control.

        Args:
            track1_path: Path to first audio track (e.g., background music)
            track2_path: Path to second audio track (e.g., TTS narration)
            output_path: Where to save the mixed audio
            track1_volume: Volume for track 1 (0.0 to 1.0+), or an FFmpeg
                           volume expression string (e.g. for BGM ducking).
            track2_volume: Volume for track 2 (0.0 to 1.0+)

        Returns:
            Path to the output file

        Raises:
            FileNotFoundError: If input files don't exist
            Exception: If FFmpeg fails
        """
        if not track1_path.exists():
            raise FileNotFoundError(f"Track 1 not found: {track1_path}")
        if not track2_path.exists():
            raise FileNotFoundError(f"Track 2 not found: {track2_path}")

        if not AudioMerger.has_audio_stream(track1_path):
            import shutil
            shutil.copy2(track2_path, output_path)
            return output_path

        runner = get_ffmpeg_runner()
        if not runner.is_available():
            raise Exception("FFmpeg not found")

        # Support plain float or FFmpeg expression string for ducking
        vol1_expr = f"'{track1_volume}'" if isinstance(track1_volume, str) else str(track1_volume)

        filter_complex = (
            f"[0:a]volume={vol1_expr}[a1];"
            f"[1:a]volume={track2_volume}[a2];"
            f"[a1][a2]amix=inputs=2:duration=longest"
        )

        try:
            runner.run(
                [
                    "-i", str(track1_path),
                    "-i", str(track2_path),
                    "-filter_complex", filter_complex,
                    "-y",
                    str(output_path),
                ],
                check=True,
            )
            return output_path
        except Exception as e:
            raise Exception(f"FFmpeg mix failed: {e}") from e
