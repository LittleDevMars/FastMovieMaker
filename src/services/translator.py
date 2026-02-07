"""Translation service for subtitle tracks.

Supports multiple translation engines:
- DeepL API
- OpenAI GPT-4o-mini
- Google Translate API
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from src.models.subtitle import SubtitleSegment, SubtitleTrack


class TranslationEngine(Enum):
    """Available translation engines."""
    DEEPL = auto()
    GPT = auto()
    GOOGLE = auto()


# Language code mappings
ISO_639_1_CODES = {
    "Korean": "ko",
    "English": "en",
    "Japanese": "ja",
    "Chinese": "zh",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Russian": "ru",
    "Portuguese": "pt",
    "Italian": "it",
    "Dutch": "nl",
    "Arabic": "ar",
    "Turkish": "tr",
    "Polish": "pl",
    "Vietnamese": "vi",
    "Thai": "th",
    "Indonesian": "id",
}

# DeepL-specific language codes
DEEPL_LANGUAGE_CODES = {
    "English": "EN",
    "German": "DE",
    "French": "FR",
    "Spanish": "ES",
    "Italian": "IT",
    "Japanese": "JA",
    "Dutch": "NL",
    "Polish": "PL",
    "Portuguese": "PT",
    "Russian": "RU",
    "Chinese": "ZH",
    "Korean": "KO",  # added in newer versions
}


class TranslatorService(QObject):
    """Service for translating subtitle tracks.

    Uses multiple translation engines and handles batch translation
    of subtitle segments.
    """

    # Signal emitted during translation progress
    progress = Signal(int, int)  # current, total
    error = Signal(str)  # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._api_keys = {
            TranslationEngine.DEEPL: "",
            TranslationEngine.GPT: "",
        }
        self._canceled = False

    def set_api_key(self, engine: TranslationEngine, key: str) -> None:
        """Set the API key for a translation engine."""
        self._api_keys[engine] = key

    def get_api_key(self, engine: TranslationEngine) -> str:
        """Get the API key for a translation engine."""
        return self._api_keys.get(engine, "")

    def translate_track(
        self,
        track: SubtitleTrack,
        source_lang: str,
        target_lang: str,
        engine: TranslationEngine,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Optional[SubtitleTrack]:
        """Translate an entire subtitle track.

        Args:
            track: The subtitle track to translate
            source_lang: Source language name (e.g., "Korean")
            target_lang: Target language name (e.g., "English")
            engine: Translation engine to use
            progress_callback: Optional callback for progress updates

        Returns:
            A new SubtitleTrack with translated content or None if canceled
        """
        if not track or len(track) == 0:
            return None

        self._canceled = False
        result_track = SubtitleTrack(
            language=ISO_639_1_CODES.get(target_lang, ""),
            name=f"{target_lang} (Translated)"
        )

        total = len(track)
        batch_size = self._get_batch_size(engine)

        # Process in batches to avoid API limits
        for start_idx in range(0, total, batch_size):
            if self._canceled:
                return None

            end_idx = min(start_idx + batch_size, total)
            batch = track.segments[start_idx:end_idx]

            # Extract just the text for translation
            texts = [seg.text for seg in batch]

            try:
                # Translate the batch
                translated_texts = self._translate_batch(
                    texts, source_lang, target_lang, engine
                )

                # Create new segments with translated text
                for i, text in enumerate(translated_texts):
                    if self._canceled:
                        return None

                    original_seg = batch[i]
                    result_track.add_segment(SubtitleSegment(
                        start_ms=original_seg.start_ms,
                        end_ms=original_seg.end_ms,
                        text=text,
                        style=original_seg.style  # Keep original style
                    ))

                # Update progress
                if progress_callback:
                    progress_callback(end_idx, total)
                self.progress.emit(end_idx, total)

            except Exception as e:
                self.error.emit(str(e))
                return None

            # Rate limiting - sleep between batches
            if end_idx < total:
                time.sleep(self._get_rate_limit_delay(engine))

        return result_track

    def cancel_translation(self) -> None:
        """Cancel an ongoing translation."""
        self._canceled = True

    def _get_batch_size(self, engine: TranslationEngine) -> int:
        """Get the appropriate batch size for the translation engine."""
        if engine == TranslationEngine.DEEPL:
            return 50  # DeepL can handle larger batches
        elif engine == TranslationEngine.GPT:
            return 20  # GPT has context limitations
        else:
            return 100  # Google has higher limits

    def _get_rate_limit_delay(self, engine: TranslationEngine) -> float:
        """Get the appropriate delay between batches for the engine."""
        if engine == TranslationEngine.DEEPL:
            return 1.0  # 1 second between batches
        elif engine == TranslationEngine.GPT:
            return 1.5  # 1.5 seconds for OpenAI to avoid rate limits
        else:
            return 0.5  # 0.5 seconds for Google

    def _translate_batch(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        engine: TranslationEngine
    ) -> List[str]:
        """Translate a batch of text using the specified engine.

        Raises:
            Exception: If translation fails.
        """
        if engine == TranslationEngine.DEEPL:
            return self._translate_deepl(texts, source_lang, target_lang)
        elif engine == TranslationEngine.GPT:
            return self._translate_gpt(texts, source_lang, target_lang)
        else:
            return self._translate_google(texts, source_lang, target_lang)

    def _translate_deepl(
        self, texts: List[str], source_lang: str, target_lang: str
    ) -> List[str]:
        """Translate text using the DeepL API."""
        api_key = self._api_keys.get(TranslationEngine.DEEPL)
        if not api_key:
            raise Exception("DeepL API key not set. Please configure it in preferences.")

        # Get DeepL language codes
        source = DEEPL_LANGUAGE_CODES.get(source_lang, ISO_639_1_CODES.get(source_lang, ""))
        target = DEEPL_LANGUAGE_CODES.get(target_lang, ISO_639_1_CODES.get(target_lang, ""))

        if not source or not target:
            raise Exception(f"Unsupported language pair: {source_lang} to {target_lang}")

        # Prepare API request
        url = "https://api-free.deepl.com/v2/translate"  # Free API

        # Format texts for the API
        data = {
            "auth_key": api_key,
            "source_lang": source,
            "target_lang": target,
            "text": texts,
        }

        # Make HTTP request
        try:
            encoded_data = urllib.parse.urlencode(data).encode("utf-8")
            request = urllib.request.Request(url, data=encoded_data, method="POST")
            request.add_header("Content-Type", "application/x-www-form-urlencoded")

            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))

            # Extract translated texts
            return [translation["text"] for translation in result["translations"]]

        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Exception("DeepL API authentication failed. Check your API key.")
            elif e.code == 429:
                raise Exception("DeepL API rate limit exceeded. Try again later.")
            else:
                raise Exception(f"DeepL API error: {e.code} {e.reason}")
        except Exception as e:
            raise Exception(f"DeepL translation failed: {str(e)}")

    def _translate_gpt(
        self, texts: List[str], source_lang: str, target_lang: str
    ) -> List[str]:
        """Translate text using the OpenAI GPT API."""
        api_key = self._api_keys.get(TranslationEngine.GPT)
        if not api_key:
            raise Exception("OpenAI API key not set. Please configure it in preferences.")

        # Get language codes
        source_code = ISO_639_1_CODES.get(source_lang, "")
        target_code = ISO_639_1_CODES.get(target_lang, "")

        if not source_code or not target_code:
            raise Exception(f"Unsupported language pair: {source_lang} to {target_lang}")

        # Format prompt
        prompt = f"""Translate the following subtitles from {source_lang} to {target_lang}.
Return ONLY the translations with no additional text, one per line in the exact same order:

"""

        # Add texts to translate
        for text in texts:
            prompt += f"{text}\n"

        # Prepare API request
        url = "https://api.openai.com/v1/chat/completions"

        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": f"You are a professional subtitle translator from {source_lang} to {target_lang}. Provide accurate translations that maintain the original meaning and style."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
        }

        # Make HTTP request
        try:
            encoded_data = json.dumps(data).encode("utf-8")
            request = urllib.request.Request(url, data=encoded_data, method="POST")
            request.add_header("Content-Type", "application/json")
            request.add_header("Authorization", f"Bearer {api_key}")

            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))

            # Extract translated text
            translated_text = result["choices"][0]["message"]["content"]

            # Split the response into separate lines
            translated_lines = translated_text.strip().split("\n")

            # Make sure we have the right number of translations
            if len(translated_lines) != len(texts):
                raise Exception(f"Got {len(translated_lines)} translations but expected {len(texts)}")

            return translated_lines

        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise Exception("OpenAI API authentication failed. Check your API key.")
            elif e.code == 429:
                raise Exception("OpenAI API rate limit exceeded. Try again later.")
            else:
                error_data = json.loads(e.read().decode("utf-8"))
                error_msg = error_data.get("error", {}).get("message", f"{e.code} {e.reason}")
                raise Exception(f"OpenAI API error: {error_msg}")
        except Exception as e:
            raise Exception(f"GPT translation failed: {str(e)}")

    def _translate_google(
        self, texts: List[str], source_lang: str, target_lang: str
    ) -> List[str]:
        """Translate text using the Google Translate API (unofficial)."""
        # Get language codes
        source_code = ISO_639_1_CODES.get(source_lang, "")
        target_code = ISO_639_1_CODES.get(target_lang, "")

        if not source_code or not target_code:
            raise Exception(f"Unsupported language pair: {source_lang} to {target_lang}")

        # Use the free Google Translate API
        translated_texts = []

        # Process each text individually
        for text in texts:
            if self._canceled:
                raise Exception("Translation canceled")

            try:
                # URL encode the text
                encoded_text = urllib.parse.quote(text)

                # Construct the Google Translate URL
                url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source_code}&tl={target_code}&dt=t&q={encoded_text}"

                # Make HTTP request
                request = urllib.request.Request(url)
                request.add_header("User-Agent", "Mozilla/5.0")

                with urllib.request.urlopen(request, timeout=5) as response:
                    result = json.loads(response.read().decode("utf-8"))

                # Extract translated text - Google returns a nested list structure
                translated_text = ""
                for sentence in result[0]:
                    if sentence[0]:
                        translated_text += sentence[0]

                translated_texts.append(translated_text)

                # Small delay to avoid getting blocked
                time.sleep(0.2)

            except Exception as e:
                raise Exception(f"Google translation failed: {str(e)}")

        return translated_texts