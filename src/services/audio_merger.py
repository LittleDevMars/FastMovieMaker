"""
Audio merger service using FFmpeg for concatenating and mixing audio tracks.
"""
from pathlib import Path
from typing import List
import subprocess
import json
import tempfile


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

        # Find ffprobe
        from ..utils.ffmpeg_utils import find_ffprobe
        ffprobe_path = find_ffprobe()

        if not ffprobe_path:
            raise Exception("FFprobe not found")

        # Run ffprobe
        cmd = [
            ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(audio_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            data = json.loads(result.stdout)
            duration = float(data["format"]["duration"])
            return duration

        except subprocess.CalledProcessError as e:
            raise Exception(f"FFprobe failed: {e.stderr}")
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

        # Find ffmpeg
        from ..utils.ffmpeg_utils import find_ffmpeg
        ffmpeg_path = find_ffmpeg()

        if not ffmpeg_path:
            raise Exception("FFmpeg not found")

        # Check if any volume differs from 1.0
        needs_volume = volumes and any(v != 1.0 for v in volumes)

        if needs_volume:
            # Use filter_complex approach for per-file volume
            return AudioMerger._merge_with_volumes(
                ffmpeg_path, audio_files, output_path, volumes
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
            # FFmpeg concat command
            cmd = [
                ffmpeg_path,
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                "-y",
                str(output_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            return output_path

        except subprocess.CalledProcessError as e:
            raise Exception(f"FFmpeg merge failed: {e.stderr}")

        finally:
            # Clean up temp file
            if concat_file.exists():
                concat_file.unlink()

    @staticmethod
    def _merge_with_volumes(
        ffmpeg_path: str,
        audio_files: List[Path],
        output_path: Path,
        volumes: List[float],
    ) -> Path:
        """Merge audio files with per-file volume using FFmpeg filter_complex."""
        # Build inputs and filter
        cmd = [ffmpeg_path]
        for audio_file in audio_files:
            if not audio_file.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_file}")
            cmd.extend(["-i", str(audio_file)])

        # Build filter_complex: apply volume to each input, then concat
        parts = []
        for i, vol in enumerate(volumes):
            parts.append(f"[{i}:a]volume={vol:.2f}[a{i}]")

        concat_inputs = "".join(f"[a{i}]" for i in range(len(audio_files)))
        parts.append(f"{concat_inputs}concat=n={len(audio_files)}:v=0:a=1[out]")

        filter_complex = ";".join(parts)
        cmd.extend(["-filter_complex", filter_complex, "-map", "[out]", "-y", str(output_path)])

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return output_path
        except subprocess.CalledProcessError as e:
            raise Exception(f"FFmpeg merge with volumes failed: {e.stderr}")

    @staticmethod
    def has_audio_stream(file_path: Path) -> bool:
        """
        Check if a file has an audio stream.

        Args:
            file_path: Path to the media file

        Returns:
            True if the file has an audio stream, False otherwise
        """
        from ..utils.ffmpeg_utils import find_ffprobe
        ffprobe_path = find_ffprobe()

        if not ffprobe_path:
            return False

        cmd = [
            ffprobe_path,
            "-v", "quiet",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(file_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip() == "audio"
        except Exception:
            return False

    @staticmethod
    def mix_audio_tracks(
        track1_path: Path,
        track2_path: Path,
        output_path: Path,
        track1_volume: float = 0.5,
        track2_volume: float = 1.0
    ) -> Path:
        """
        Mix two audio tracks with volume control.

        Args:
            track1_path: Path to first audio track (e.g., background music)
            track2_path: Path to second audio track (e.g., TTS narration)
            output_path: Where to save the mixed audio
            track1_volume: Volume for track 1 (0.0 to 1.0+)
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

        # Check if track1 has audio
        if not AudioMerger.has_audio_stream(track1_path):
            # If track1 has no audio, just copy track2 with volume adjustment
            import shutil
            shutil.copy2(track2_path, output_path)
            return output_path

        # Find ffmpeg
        from ..utils.ffmpeg_utils import find_ffmpeg
        ffmpeg_path = find_ffmpeg()

        if not ffmpeg_path:
            raise Exception("FFmpeg not found")

        # Build filter complex
        # [0:a]volume=X[a1];[1:a]volume=Y[a2];[a1][a2]amix=inputs=2:duration=longest
        filter_complex = (
            f"[0:a]volume={track1_volume}[a1];"
            f"[1:a]volume={track2_volume}[a2];"
            f"[a1][a2]amix=inputs=2:duration=longest"
        )

        cmd = [
            ffmpeg_path,
            "-i", str(track1_path),
            "-i", str(track2_path),
            "-filter_complex", filter_complex,
            "-y",
            str(output_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            return output_path

        except subprocess.CalledProcessError as e:
            raise Exception(f"FFmpeg mix failed: {e.stderr}")
