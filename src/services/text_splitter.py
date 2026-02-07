"""
Text splitter for dividing scripts into segments for TTS generation.
"""
from dataclasses import dataclass
from enum import Enum
from typing import List
import re


class SplitStrategy(Enum):
    """Strategy for splitting text into segments."""
    SENTENCE = "sentence"  # Split by sentence endings (. ! ?)
    NEWLINE = "newline"    # Split by newlines
    FIXED_LENGTH = "fixed" # Split by fixed character length


@dataclass
class TextSegment:
    """A segment of text to be converted to speech."""
    text: str
    index: int  # 0-based index in the sequence


class TextSplitter:
    """Splits text into segments for TTS generation."""

    def split(
        self,
        script: str,
        strategy: SplitStrategy = SplitStrategy.SENTENCE,
        max_length: int = 50
    ) -> List[TextSegment]:
        """
        Split script into segments based on strategy.

        Args:
            script: The text to split
            strategy: The splitting strategy to use
            max_length: Maximum characters per segment (for FIXED_LENGTH)

        Returns:
            List of TextSegment objects
        """
        if not script or not script.strip():
            return []

        if strategy == SplitStrategy.SENTENCE:
            return self._split_by_sentence(script)
        elif strategy == SplitStrategy.NEWLINE:
            return self._split_by_newline(script)
        elif strategy == SplitStrategy.FIXED_LENGTH:
            return self._split_by_fixed_length(script, max_length)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _split_by_sentence(self, text: str) -> List[TextSegment]:
        """
        Split text by sentence endings (. ! ? followed by space or end).

        Handles common edge cases:
        - Multiple punctuation marks (e.g., "!!!", "...?")
        - Quotes after punctuation (e.g., 'He said "Hello."')
        """
        # Pattern: sentence ending punctuation + optional quotes + space/end
        pattern = r'([.!?]+["\']?\s+|[.!?]+["\']?$)'

        # Split and keep delimiters
        parts = re.split(pattern, text)

        # Reconstruct sentences by combining text and delimiters
        segments = []
        current_sentence = ""

        for part in parts:
            if not part:
                continue

            current_sentence += part

            # If this part is a delimiter (ends with sentence ending)
            if re.match(pattern, part):
                sentence = current_sentence.strip()
                if sentence:
                    segments.append(TextSegment(
                        text=sentence,
                        index=len(segments)
                    ))
                current_sentence = ""

        # Add any remaining text
        if current_sentence.strip():
            segments.append(TextSegment(
                text=current_sentence.strip(),
                index=len(segments)
            ))

        return segments

    def _split_by_newline(self, text: str) -> List[TextSegment]:
        """Split text by newlines."""
        lines = text.split('\n')
        segments = []

        for line in lines:
            line = line.strip()
            if line:  # Skip empty lines
                segments.append(TextSegment(
                    text=line,
                    index=len(segments)
                ))

        return segments

    def _split_by_fixed_length(self, text: str, max_length: int) -> List[TextSegment]:
        """
        Split text by fixed character length.

        Tries to break at word boundaries when possible.
        """
        if max_length <= 0:
            raise ValueError("max_length must be positive")

        segments = []
        remaining = text.strip()

        while remaining:
            if len(remaining) <= max_length:
                # Last segment
                segments.append(TextSegment(
                    text=remaining,
                    index=len(segments)
                ))
                break

            # Find the last space within max_length
            chunk = remaining[:max_length]
            last_space = chunk.rfind(' ')

            if last_space > 0 and last_space > max_length * 0.5:
                # Break at word boundary (if it's not too early)
                split_point = last_space
            else:
                # Break at max_length (mid-word if necessary)
                split_point = max_length

            segment_text = remaining[:split_point].strip()
            if segment_text:
                segments.append(TextSegment(
                    text=segment_text,
                    index=len(segments)
                ))

            remaining = remaining[split_point:].strip()

        return segments
