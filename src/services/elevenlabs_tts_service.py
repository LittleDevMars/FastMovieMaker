"""ElevenLabs TTS service using the REST API."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable, Optional

from src.services.tts_service import AudioSegment
from src.utils.config import ELEVENLABS_DEFAULT_VOICES


class ElevenLabsTTSService:
    """Text-to-speech generation using the ElevenLabs API."""

    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def generate_speech(
        self,
        text: str,
        voice_id: str,
        speed: float = 1.0,
        output_path: Path | None = None,
        timeout: float = 60.0,
        model_id: str = "eleven_multilingual_v2",
    ) -> float:
        """Generate speech for a single text segment.

        Returns duration in seconds.
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        if output_path is None:
            raise ValueError("output_path is required")

        url = f"{self.BASE_URL}/text-to-speech/{voice_id}"

        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "speed": speed,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("xi-api-key", self._api_key)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "audio/mpeg")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                audio_bytes = response.read()

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            from src.services.audio_merger import AudioMerger
            return AudioMerger.get_audio_duration(output_path)

        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise Exception(
                    "ElevenLabs API 키가 유효하지 않습니다. "
                    "Edit > Preferences > API Keys에서 확인하세요."
                )
            elif e.code == 429:
                raise Exception(
                    "ElevenLabs 사용량 한도를 초과했습니다. 잠시 후 다시 시도하세요."
                )
            else:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                raise Exception(f"ElevenLabs API error ({e.code}): {body[:200]}")

    def generate_segments(
        self,
        segments: list[tuple],
        voice_id: str,
        speed: float = 1.0,
        output_dir: Path | None = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        timeout: float = 60.0,
    ) -> list[AudioSegment]:
        """Generate speech for multiple text segments."""
        if output_dir is None:
            raise ValueError("output_dir is required")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[AudioSegment] = []
        total = len(segments)

        for i, (text, index) in enumerate(segments):
            audio_path = output_dir / f"segment_{index:04d}.mp3"

            try:
                duration = self.generate_speech(
                    text=text,
                    voice_id=voice_id,
                    speed=speed,
                    output_path=audio_path,
                    timeout=timeout,
                )

                results.append(
                    AudioSegment(
                        text=text,
                        audio_path=audio_path,
                        duration_sec=duration,
                        index=index,
                    )
                )

                if on_progress:
                    on_progress(i + 1, total)

            except Exception as e:
                if audio_path.exists():
                    audio_path.unlink()
                raise Exception(
                    f"세그먼트 {index} 생성 실패 ('{text[:30]}...'): {e}"
                )

        return results

    def list_voices(self) -> dict[str, str]:
        """Fetch available voices from the ElevenLabs API.

        Returns dict of {display_name: voice_id}.
        Falls back to hardcoded defaults on error.
        """
        url = f"{self.BASE_URL}/voices"
        req = urllib.request.Request(url)
        req.add_header("xi-api-key", self._api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            voices: dict[str, str] = {}
            for voice in data.get("voices", []):
                name = voice.get("name", "Unknown")
                vid = voice.get("voice_id", "")
                if vid:
                    voices[name] = vid
            return voices if voices else dict(ELEVENLABS_DEFAULT_VOICES)
        except Exception:
            return dict(ELEVENLABS_DEFAULT_VOICES)

    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        """Quick validation: GET /v1/user with the key."""
        if not api_key or not api_key.strip():
            return False

        url = "https://api.elevenlabs.io/v1/user"
        req = urllib.request.Request(url)
        req.add_header("xi-api-key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except Exception:
            return False
