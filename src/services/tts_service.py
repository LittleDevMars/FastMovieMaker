"""
TTS (Text-to-Speech) service using edge-tts.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Callable, Optional
import asyncio
import edge_tts


@dataclass
class Voice:
    """Represents a TTS voice."""
    name: str          # e.g., "ko-KR-SunHiNeural"
    gender: str        # "Male" or "Female"
    language: str      # e.g., "ko-KR"
    display_name: str  # e.g., "SunHi (Female)"


@dataclass
class AudioSegment:
    """Result of TTS generation for a text segment."""
    text: str
    audio_path: Path
    duration_sec: float
    index: int


class TTSService:
    """Service for text-to-speech generation using edge-tts."""

    @staticmethod
    async def generate_speech(
        text: str,
        voice: str,
        rate: str = "+0%",
        output_path: Path = None,
        timeout: float = 30.0
    ) -> float:
        """
        Generate speech for a single text segment.

        Args:
            text: Text to convert to speech
            voice: Voice name (e.g., "ko-KR-SunHiNeural")
            rate: Speech rate (e.g., "+0%", "+50%", "-50%")
            output_path: Where to save the audio file
            timeout: Timeout in seconds

        Returns:
            Duration of the generated audio in seconds

        Raises:
            asyncio.TimeoutError: If generation times out
            Exception: If generation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        if output_path is None:
            raise ValueError("output_path is required")

        # Create communicate object
        communicate = edge_tts.Communicate(text, voice, rate=rate)

        try:
            # Save with timeout
            await asyncio.wait_for(
                communicate.save(str(output_path)),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                f"TTS generation timed out after {timeout}s"
            )
        except Exception as e:
            raise Exception(f"TTS generation failed: {e}")

        # Get duration using edge_tts metadata
        # We need to read the file to get accurate duration
        from .audio_merger import AudioMerger
        duration = AudioMerger.get_audio_duration(output_path)

        return duration

    @staticmethod
    async def generate_segments(
        segments: List[tuple],  # List of (text, index)
        voice: str,
        rate: str,
        output_dir: Path,
        on_progress: Optional[Callable[[int, int], None]] = None,
        timeout: float = 30.0
    ) -> List[AudioSegment]:
        """
        Generate speech for multiple text segments.

        Args:
            segments: List of (text, index) tuples
            voice: Voice name
            rate: Speech rate
            output_dir: Directory to save audio files
            on_progress: Callback(current, total) for progress updates
            timeout: Timeout per segment in seconds

        Returns:
            List of AudioSegment objects
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        total = len(segments)

        for i, (text, index) in enumerate(segments):
            # Generate filename
            audio_path = output_dir / f"segment_{index:04d}.mp3"

            try:
                # Generate speech
                duration = await TTSService.generate_speech(
                    text=text,
                    voice=voice,
                    rate=rate,
                    output_path=audio_path,
                    timeout=timeout
                )

                results.append(AudioSegment(
                    text=text,
                    audio_path=audio_path,
                    duration_sec=duration,
                    index=index
                ))

                # Report progress
                if on_progress:
                    on_progress(i + 1, total)

            except Exception as e:
                # Clean up partial file
                if audio_path.exists():
                    audio_path.unlink()
                raise Exception(
                    f"Failed to generate segment {index} ('{text[:30]}...'): {e}"
                )

        return results

    @staticmethod
    async def list_voices(language: str = None) -> List[Voice]:
        """
        List available voices.

        Args:
            language: Filter by language code (e.g., "ko", "en")

        Returns:
            List of Voice objects
        """
        voices_list = await edge_tts.list_voices()
        result = []

        for voice_data in voices_list:
            voice_locale = voice_data.get("Locale", "")
            voice_name = voice_data.get("ShortName", "")
            voice_gender = voice_data.get("Gender", "")

            # Filter by language if specified
            if language:
                if not voice_locale.lower().startswith(language.lower()):
                    continue

            # Extract display name (e.g., "SunHiNeural" -> "SunHi")
            display_base = voice_name.split("-")[-1].replace("Neural", "")
            display_name = f"{display_base} ({voice_gender})"

            result.append(Voice(
                name=voice_name,
                gender=voice_gender,
                language=voice_locale,
                display_name=display_name
            ))

        return result

    @staticmethod
    def format_rate(speed: float) -> str:
        """
        Convert speed multiplier to edge-tts rate format.

        Args:
            speed: Speed multiplier (0.5 = 50%, 1.0 = 100%, 2.0 = 200%)

        Returns:
            Rate string (e.g., "+0%", "+50%", "-50%")
        """
        if speed <= 0:
            raise ValueError("Speed must be positive")

        # Convert to percentage change
        # 1.0 -> +0%, 1.5 -> +50%, 0.5 -> -50%
        percent_change = int((speed - 1.0) * 100)

        if percent_change >= 0:
            return f"+{percent_change}%"
        else:
            return f"{percent_change}%"
