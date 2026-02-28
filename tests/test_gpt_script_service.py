"""GptScriptService 단위 테스트 (Qt 의존 없음)."""

import pytest

from src.services.gpt_script_service import GptScriptService


class TestBuildPrompt:
    def test_build_prompt_contains_topic(self):
        prompt = GptScriptService._build_prompt("인공지능의 역사")
        assert "인공지능의 역사" in prompt

    def test_build_prompt_length_short(self):
        prompt = GptScriptService._build_prompt("topic", length="short")
        assert "300" in prompt

    def test_build_prompt_length_medium(self):
        prompt = GptScriptService._build_prompt("topic", length="medium")
        assert "700" in prompt

    def test_build_prompt_length_long(self):
        prompt = GptScriptService._build_prompt("topic", length="long")
        assert "1500" in prompt

    def test_build_prompt_language_ko(self):
        prompt = GptScriptService._build_prompt("topic", language="ko")
        assert "Korean" in prompt

    def test_build_prompt_language_en(self):
        prompt = GptScriptService._build_prompt("topic", language="en")
        assert "English" in prompt


class TestParseResponse:
    def test_parse_response(self):
        fake_data = {
            "choices": [
                {"message": {"content": "  생성된 대본 텍스트  "}}
            ]
        }
        result = GptScriptService._parse_response(fake_data)
        assert result == "생성된 대본 텍스트"


class TestGenerateScript:
    def test_api_key_missing_raises(self):
        with pytest.raises(ValueError, match="OpenAI API key"):
            GptScriptService.generate_script("topic", api_key="")


class TestI18nKeys:
    def test_i18n_keys_present(self):
        from src.utils.lang.ko import STRINGS
        assert "Generate with AI..." in STRINGS
        assert "Use This Script" in STRINGS
        assert "Generate Script with AI" in STRINGS
        assert "Topic / Context:" in STRINGS
        assert "Generated Script:" in STRINGS
