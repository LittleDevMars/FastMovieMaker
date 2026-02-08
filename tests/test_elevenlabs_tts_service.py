"""Tests for ElevenLabs TTS service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.elevenlabs_tts_service import ElevenLabsTTSService
from src.utils.config import ELEVENLABS_DEFAULT_VOICES, TTSEngine


class TestElevenLabsVoices:
    def test_default_voices_not_empty(self):
        assert len(ELEVENLABS_DEFAULT_VOICES) > 0

    def test_default_voices_have_ids(self):
        for name, voice_id in ELEVENLABS_DEFAULT_VOICES.items():
            assert voice_id, f"Voice '{name}' has empty ID"
            assert len(voice_id) > 10, f"Voice ID '{voice_id}' seems too short"


class TestTTSEngine:
    def test_engine_constants(self):
        assert TTSEngine.EDGE_TTS == "edge_tts"
        assert TTSEngine.ELEVENLABS == "elevenlabs"


class TestElevenLabsTTSService:
    def test_generate_speech_empty_text(self):
        service = ElevenLabsTTSService(api_key="test-key")
        with pytest.raises(ValueError, match="Text cannot be empty"):
            service.generate_speech("", "voice_id", output_path=Path("/tmp/test.mp3"))

    def test_generate_speech_whitespace_text(self):
        service = ElevenLabsTTSService(api_key="test-key")
        with pytest.raises(ValueError, match="Text cannot be empty"):
            service.generate_speech("   ", "voice_id", output_path=Path("/tmp/test.mp3"))

    def test_generate_speech_no_output_path(self):
        service = ElevenLabsTTSService(api_key="test-key")
        with pytest.raises(ValueError, match="output_path is required"):
            service.generate_speech("Hello", "voice_id")

    def test_generate_segments_no_output_dir(self):
        service = ElevenLabsTTSService(api_key="test-key")
        with pytest.raises(ValueError, match="output_dir is required"):
            service.generate_segments([("hello", 0)], "voice_id")

    def test_validate_api_key_empty(self):
        assert ElevenLabsTTSService.validate_api_key("") is False

    def test_validate_api_key_whitespace(self):
        assert ElevenLabsTTSService.validate_api_key("   ") is False

    @patch("src.services.elevenlabs_tts_service.urllib.request.urlopen")
    def test_list_voices_fallback_on_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Network error")
        service = ElevenLabsTTSService(api_key="test-key")
        voices = service.list_voices()
        assert voices == dict(ELEVENLABS_DEFAULT_VOICES)

    @patch("src.services.elevenlabs_tts_service.urllib.request.urlopen")
    def test_list_voices_parses_api_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = (
            b'{"voices": [{"name": "TestVoice", "voice_id": "abc123"}]}'
        )
        mock_urlopen.return_value = mock_response

        service = ElevenLabsTTSService(api_key="test-key")
        voices = service.list_voices()
        assert "TestVoice" in voices
        assert voices["TestVoice"] == "abc123"

    @patch("src.services.elevenlabs_tts_service.urllib.request.urlopen")
    def test_list_voices_empty_response_falls_back(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b'{"voices": []}'
        mock_urlopen.return_value = mock_response

        service = ElevenLabsTTSService(api_key="test-key")
        voices = service.list_voices()
        assert voices == dict(ELEVENLABS_DEFAULT_VOICES)


class TestWorkerEngineParam:
    def test_tts_worker_accepts_engine_param(self):
        """TTSWorker should accept the engine parameter."""
        import inspect
        from src.workers.tts_worker import TTSWorker

        sig = inspect.signature(TTSWorker.__init__)
        assert "engine" in sig.parameters

    def test_tts_worker_default_engine(self):
        """TTSWorker default engine should be edge_tts."""
        import inspect
        from src.workers.tts_worker import TTSWorker

        sig = inspect.signature(TTSWorker.__init__)
        default = sig.parameters["engine"].default
        assert default == TTSEngine.EDGE_TTS
