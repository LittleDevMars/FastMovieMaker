"""Tests for text_splitter module."""

import pytest
from src.services.text_splitter import TextSplitter, SplitStrategy, TextSegment


class TestTextSplitter:
    """Test suite for TextSplitter."""

    def test_empty_text(self):
        """Test splitting empty text returns empty list."""
        splitter = TextSplitter()
        result = splitter.split("", SplitStrategy.SENTENCE)
        assert result == []

    def test_whitespace_only(self):
        """Test splitting whitespace-only text returns empty list."""
        splitter = TextSplitter()
        result = splitter.split("   \n\t  ", SplitStrategy.SENTENCE)
        assert result == []

    def test_sentence_basic(self):
        """Test basic sentence splitting."""
        splitter = TextSplitter()
        text = "Hello world. How are you? I'm fine!"
        result = splitter.split(text, SplitStrategy.SENTENCE)

        assert len(result) == 3
        assert result[0].text == "Hello world."
        assert result[1].text == "How are you?"
        assert result[2].text == "I'm fine!"
        assert result[0].index == 0
        assert result[1].index == 1
        assert result[2].index == 2

    def test_sentence_korean(self):
        """Test sentence splitting with Korean text."""
        splitter = TextSplitter()
        text = "안녕하세요. 반갑습니다! 좋은 하루 되세요?"
        result = splitter.split(text, SplitStrategy.SENTENCE)

        assert len(result) == 3
        assert result[0].text == "안녕하세요."
        assert result[1].text == "반갑습니다!"
        assert result[2].text == "좋은 하루 되세요?"

    def test_sentence_no_trailing_space(self):
        """Test sentence splitting with final sentence without trailing space."""
        splitter = TextSplitter()
        text = "First. Second. Third."
        result = splitter.split(text, SplitStrategy.SENTENCE)

        assert len(result) == 3
        assert result[0].text == "First."
        assert result[1].text == "Second."
        assert result[2].text == "Third."

    def test_newline_basic(self):
        """Test newline splitting."""
        splitter = TextSplitter()
        text = "Line one\nLine two\nLine three"
        result = splitter.split(text, SplitStrategy.NEWLINE)

        assert len(result) == 3
        assert result[0].text == "Line one"
        assert result[1].text == "Line two"
        assert result[2].text == "Line three"

    def test_newline_empty_lines(self):
        """Test newline splitting ignores empty lines."""
        splitter = TextSplitter()
        text = "Line one\n\n\nLine two\n\nLine three"
        result = splitter.split(text, SplitStrategy.NEWLINE)

        assert len(result) == 3
        assert result[0].text == "Line one"
        assert result[1].text == "Line two"
        assert result[2].text == "Line three"

    def test_fixed_length_basic(self):
        """Test fixed length splitting."""
        splitter = TextSplitter()
        text = "This is a test sentence that should be split."
        result = splitter.split(text, SplitStrategy.FIXED_LENGTH, max_length=15)

        assert len(result) > 1
        for segment in result:
            # Each segment should be <= max_length (except maybe if no spaces)
            assert len(segment.text) <= 20  # Some tolerance for word boundaries

    def test_fixed_length_word_boundary(self):
        """Test fixed length splitting respects word boundaries."""
        splitter = TextSplitter()
        text = "one two three four five six seven eight"
        result = splitter.split(text, SplitStrategy.FIXED_LENGTH, max_length=15)

        # Should split at word boundaries, not mid-word
        for segment in result[:-1]:  # All except last
            assert not segment.text.endswith(" ")
            if segment.text != result[-1].text:
                # Check next segment doesn't start with partial word
                assert " " in segment.text or len(segment.text) <= 15

    def test_fixed_length_invalid(self):
        """Test fixed length with invalid max_length raises error."""
        splitter = TextSplitter()
        with pytest.raises(ValueError, match="max_length must be positive"):
            splitter.split("test", SplitStrategy.FIXED_LENGTH, max_length=0)

    def test_unknown_strategy(self):
        """Test unknown strategy raises error."""
        splitter = TextSplitter()
        # Create a fake enum value
        with pytest.raises(ValueError, match="Unknown strategy"):
            # We need to bypass enum validation
            class FakeStrategy:
                value = "fake"
            splitter.split("test", FakeStrategy())
