"""BGM ducking service - FFmpeg volume expressions for TTS-aware BGM volume control."""

from __future__ import annotations

from src.models.subtitle import SubtitleSegment


class DuckingService:
    """Creates FFmpeg volume expressions to duck BGM during TTS playback."""

    @staticmethod
    def build_volume_expr(
        segments: list[SubtitleSegment],
        base_volume: float,
        duck_volume: float,
    ) -> str:
        """
        Build FFmpeg volume filter expression that ducks BGM during TTS segments.

        Args:
            segments: List of subtitle segments (only those with audio_file are used).
            base_volume: BGM volume outside TTS segments (0.0-1.0).
            duck_volume: BGM volume during TTS segments (0.0-1.0).

        Returns:
            FFmpeg volume expression string, e.g.:
            "if(gt(between(t,0.500,2.000)+between(t,3.000,5.500),0),0.300,0.800)"
            If no active TTS segments, returns str(base_volume).
        """
        active = [s for s in segments if s.audio_file]
        if not active:
            return str(base_volume)

        parts = [
            f"between(t,{s.start_ms / 1000:.3f},{s.end_ms / 1000:.3f})"
            for s in active
        ]
        return f"if(gt({'+'.join(parts)},0),{duck_volume:.3f},{base_volume:.3f})"
