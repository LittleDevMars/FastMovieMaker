"""GPT 기반 비디오 대본 자동 생성 서비스."""

import json
import urllib.request


class GptScriptService:
    """OpenAI GPT API를 사용해 비디오 나레이션 대본을 자동 생성한다."""

    LENGTH_CHARS: dict[str, int] = {
        "short": 300,
        "medium": 700,
        "long": 1500,
    }

    STYLE_PROMPTS: dict[str, str] = {
        "informative": "educational and informative",
        "casual":      "friendly and conversational",
        "persuasive":  "compelling and persuasive",
        "humorous":    "engaging and humorous",
    }

    @staticmethod
    def _build_prompt(
        topic: str,
        style: str = "informative",
        length: str = "medium",
        language: str = "ko",
    ) -> str:
        """테스트 가능한 독립 메서드 — 프롬프트 문자열 반환."""
        target_chars = GptScriptService.LENGTH_CHARS.get(length, 700)
        style_desc   = GptScriptService.STYLE_PROMPTS.get(style, "educational and informative")
        lang_name    = "Korean" if language == "ko" else "English"
        return (
            f"Write a {style_desc} video narration script about the following topic in {lang_name}.\n"
            f"Target length: approximately {target_chars} characters.\n"
            f"Topic: {topic}\n\n"
            "Write only the script text. No headers, labels, or metadata."
        )

    @staticmethod
    def _parse_response(data: dict) -> str:
        """API 응답 dict → 스크립트 텍스트."""
        return data["choices"][0]["message"]["content"].strip()

    @staticmethod
    def generate_script(
        topic: str,
        style: str = "informative",
        length: str = "medium",
        language: str = "ko",
        api_key: str = "",
    ) -> str:
        """OpenAI gpt-4o-mini 호출 → 생성된 스크립트 텍스트 반환.

        Raises:
            ValueError: API 키가 없을 때.
            Exception: API 호출 실패 시.
        """
        if not api_key:
            raise ValueError("OpenAI API key is required. Set it in Preferences > API Keys.")

        prompt = GptScriptService._build_prompt(topic, style, length, language)
        body = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a professional video script writer."},
                {"role": "user",   "content": prompt},
            ],
            "temperature": 0.7,
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            json.dumps(body).encode(),
            method="POST",
        )
        req.add_header("Content-Type",  "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return GptScriptService._parse_response(data)
