"""
Translation Service for Gemini TTS Studio
Uses Gemini 3.8 Flash to translate script texts into target languages while strictly preserving audio tags.
"""

import os
import requests
from typing import Optional
from .config import get_api_key, TRANSLATION_MODEL, SUPPORTED_LANGUAGES


LANGUAGE_NAME_MAP = {
    "de": "German (Deutsch)",
    "en": "English (UK)",
    "en-us": "English (US)",
    "fr": "French (Français)",
    "es": "Spanish (Español)",
    "it": "Italian (Italiano)",
    "pt": "Portuguese (Português de Portugal)",
    "pt-br": "Brazilian Portuguese (Português do Brasil)",
    "nl": "Dutch (Nederlands)",
    "pl": "Polish (Polski)",
    "sv": "Swedish (Svenska)",
    "no": "Norwegian (Norsk)",
    "da": "Danish (Dansk)",
    "fi": "Finnish (Suomi)",
    "tr": "Turkish (Türkçe)",
    "el": "Greek (Ελληνικά)",
    "cs": "Czech (Čeština)",
    "ro": "Romanian (Română)",
    "hu": "Hungarian (Magyar)",
    "uk": "Ukrainian (Українська)",
    "ru": "Russian (Русский)",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
    "zh": "Chinese (Mandarin / 中文)",
    "hi": "Hindi (हिन्दी)",
    "ar": "Arabic (العربية)",
    "id": "Indonesian (Bahasa Indonesia)",
    "vi": "Vietnamese (Tiếng Việt)",
    "th": "Thai (ไทย)",
    "bg": "Bulgarian (Български)",
    "hr": "Croatian (Hrvatski)",
}


class TranslationService:
    """Translates audio script texts using Gemini while maintaining bracketed emotion tags."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_api_key()

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    def translate_text(self, text: str, target_lang_id: str, source_lang_id: str = "auto") -> str:
        """
        Translates text to target language while keeping audio tags like [lachen], [whisper], [pause] intact.
        """
        text = text.strip()
        if not text:
            return ""

        if target_lang_id == "auto" or target_lang_id == source_lang_id:
            return text

        target_lang_name = LANGUAGE_NAME_MAP.get(target_lang_id, target_lang_id)
        api_key = self.api_key or get_api_key()
        if not api_key:
            raise ValueError("Kein Gemini API-Key vorhanden. Bitte API-Key hinterlegen.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{TRANSLATION_MODEL}:generateContent?key={api_key}"

        prompt = (
            f"You are a professional multilingual audio script translator.\n"
            f"Translate the following text into {target_lang_name}.\n\n"
            f"CRITICAL RULES:\n"
            f"1. Preserve all square-bracketed audio directives and emotion tags (e.g. [lachen], [flüstern], [traurig], "
            f"[begeistert], [Pause], [seufzen], [wütend], [nachdenklich], [langsam], [schnell], [laugh], [whisper], [pause], etc.) "
            f"EXACTLY as they are in square brackets, placed naturally at the corresponding positions in the sentence.\n"
            f"2. Do NOT translate or remove the bracketed tags themselves.\n"
            f"3. Return ONLY the translated script text. Do NOT add any preamble, greeting, markdown backticks, or explanation.\n\n"
            f"Text to translate:\n{text}"
        )

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.3
            }
        }

        response = requests.post(url, json=payload, timeout=60)
        if response.status_code != 200:
            error_data = response.json() if response.text else {}
            msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
            raise RuntimeError(f"Fehler bei der Übersetzung mit {TRANSLATION_MODEL}: {msg}")

        result_json = response.json()
        candidates = result_json.get("candidates", [])
        if not candidates:
            raise RuntimeError("Keine Übersetzung von Gemini erhalten.")

        translated_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        
        # Clean up any potential markdown code blocks if model wrapped output
        if translated_text.startswith("```") and translated_text.endswith("```"):
            lines = translated_text.splitlines()
            if len(lines) >= 2:
                translated_text = "\n".join(lines[1:-1]).strip()

        return translated_text
