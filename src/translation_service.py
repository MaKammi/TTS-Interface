"""
Translation Service for Gemini TTS Studio
Uses Gemini 3.6 Flash (with fallback) to translate script texts into target languages while strictly preserving audio tags.
"""

import os
import re
import requests
from typing import Optional, List
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
    """Translates audio script texts using Gemini while strictly maintaining bracketed emotion tags."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_api_key()

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    def _call_translation_api(self, text_block: str, target_lang_name: str, api_key: str) -> str:
        """Translates a single block of text using Gemini with strict system instruction and temp 0.0."""
        models_to_try = [TRANSLATION_MODEL, "gemini-3.8-flash", "gemini-2.5-pro"]
        last_err = None

        system_instruction = (
            f"You are an expert multilingual voiceover and audio script translator.\n"
            f"Your task is to translate the provided text completely, naturally and accurately into {target_lang_name}.\n\n"
            f"STRICT RULES:\n"
            f"1. Translate 100% of the text. Every single sentence and paragraph must be fully translated into {target_lang_name}.\n"
            f"   Do NOT leave any words or sentences in the original source language.\n"
            f"2. Preserve all square-bracketed audio directives and emotion tags (e.g. [lachen], [flüstern], [traurig], "
            f"[begeistert], [Pause], [seufzen], [wütend], [nachdenklich], [langsam], [schnell], [laugh], [whisper], [pause], etc.) "
            f"EXACTLY as they are in square brackets, placed naturally at the corresponding positions in the sentence.\n"
            f"3. Do NOT translate or remove the bracketed tags themselves.\n"
            f"4. Return ONLY the translated script text. Do NOT add any greeting, preamble, explanations, notes, or markdown backticks."
        )

        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "systemInstruction": {
                    "parts": [{"text": system_instruction}]
                },
                "contents": [
                    {
                        "parts": [{"text": text_block}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.0
                }
            }

            try:
                response = requests.post(url, json=payload, timeout=60)
                if response.status_code == 200:
                    result_json = response.json()
                    candidates = result_json.get("candidates", [])
                    if candidates:
                        raw_trans = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        # Clean code blocks
                        if raw_trans.startswith("```") and raw_trans.endswith("```"):
                            lines = raw_trans.splitlines()
                            if len(lines) >= 2:
                                raw_trans = "\n".join(lines[1:-1]).strip()
                        if raw_trans:
                            return raw_trans
                else:
                    error_data = response.json() if response.text else {}
                    last_err = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
            except Exception as e:
                last_err = str(e)

        raise RuntimeError(f"Übersetzung fehlgeschlagen ({last_err or 'Keine Antwort erhalten'})")

    def translate_text(self, text: str, target_lang_id: str, source_lang_id: str = "auto") -> str:
        """
        Translates text to target language while keeping audio tags like [lachen], [whisper], [pause] intact.
        Splits multi-paragraph text to ensure no paragraph is ever skipped or left untranslated.
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

        # Check if text consists of multiple paragraphs
        raw_paragraphs = [p for p in text.split("\n\n") if p.strip()]
        if len(raw_paragraphs) > 1:
            translated_paragraphs = []
            for para in raw_paragraphs:
                cleaned = para.strip()
                trans_p = self._call_translation_api(cleaned, target_lang_name, api_key)
                translated_paragraphs.append(trans_p)
            return "\n\n".join(translated_paragraphs)

        # Single block or single-line separated text
        if "\n" in text and len(text) > 400:
            lines = [l for l in text.split("\n") if l.strip()]
            if len(lines) > 1:
                translated_lines = []
                for line in lines:
                    trans_l = self._call_translation_api(line.strip(), target_lang_name, api_key)
                    translated_lines.append(trans_l)
                return "\n".join(translated_lines)

        return self._call_translation_api(text, target_lang_name, api_key)
