"""
Gemini TTS Service module
Handles communication with the Gemini API to generate audio from text.
"""

import base64
import wave
import io
import re
import requests
from pathlib import Path
from typing import Optional, Dict, Any

from .config import get_api_key, TEMP_DIR


# Tag translation map from German/Common tags to Gemini standard directives
TAG_REPLACEMENTS = {
    r"\[lachen\]": "[laugh]",
    r"\[lacht\]": "[laugh]",
    r"\[lachend\]": "[laughing]",
    r"\[flüstern\]": "[whisper]",
    r"\[flüstert\]": "[whisper]",
    r"\[flüsternd\]": "[whispering]",
    r"\[traurig\]": "[sad]",
    r"\[weinen\]": "[crying]",
    r"\[begeistert\]": "[excited]",
    r"\[fröhlich\]": "[happy]",
    r"\[glücklich\]": "[happy]",
    r"\[seufzen\]": "[sigh]",
    r"\[seufzt\]": "[sigh]",
    r"\[wütend\]": "[angry]",
    r"\[ärgerlich\]": "[angry]",
    r"\[nachdenklich\]": "[thoughtful]",
    r"\[langsam\]": "[slow]",
    r"\[schnell\]": "[fast]",
    r"\[pause\]": "[pause]",
    r"\[stille\]": "[pause]",
    r"\[husten\]": "[cough]",
    r"\[räuspern\]": "[cough]",
}


def preprocess_text_for_gemini(text: str) -> str:
    """
    Standardize inline audio tags into Gemini's recognized directives.
    """
    processed = text
    # Replace German tag variants with standard Gemini audio tags (case-insensitive)
    for pattern, replacement in TAG_REPLACEMENTS.items():
        processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)
    
    return processed.strip()


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Convert raw 16-bit PCM bytes to WAV format with proper headers."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)  # 16-bit = 2 bytes
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_io.getvalue()


class GeminiTTSService:
    """Service for interacting with Gemini Text-to-Speech API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_api_key()

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    def generate_speech(
        self,
        text: str,
        voice_name: str = "Puck",
        model: str = "gemini-2.5-flash-preview-tts",
        language: str = "auto",
    ) -> Path:
        """
        Generates audio from text using Gemini TTS and saves it as a WAV file in TEMP_DIR.
        
        Returns:
            Path to the generated temporary WAV file.
        """
        current_key = self.api_key or get_api_key()
        if not current_key or current_key.strip() == "":
            raise ValueError("Kein Gemini API-Key angegeben. Bitte trage deinen API-Key in den Einstellungen ein.")

        if not text or not text.strip():
            raise ValueError("Bitte gib einen Text für die Sprachgenerierung ein.")

        processed_text = preprocess_text_for_gemini(text)

        # API Request Payload
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={current_key}"
        
        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": processed_text}
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                }
            }
        }

        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code != 200:
            error_msg = f"Gemini API Fehler ({response.status_code}): {response.text}"
            try:
                err_json = response.json()
                if "error" in err_json and "message" in err_json["error"]:
                    error_msg = f"Gemini API Fehler: {err_json['error']['message']}"
            except Exception:
                pass
            raise RuntimeError(error_msg)

        res_json = response.json()
        
        # Extract audio data from response
        try:
            candidates = res_json.get("candidates", [])
            if not candidates:
                raise ValueError("Keine Antwort von Gemini erhalten.")
            
            parts = candidates[0].get("content", {}).get("parts", [])
            audio_part = None
            for p in parts:
                if "inlineData" in p:
                    audio_part = p["inlineData"]
                    break
            
            if not audio_part or "data" not in audio_part:
                raise ValueError("Keine Audiodaten in der Gemini-Antwort gefunden.")

            mime_type = audio_part.get("mimeType", "")
            raw_audio_bytes = base64.b64decode(audio_part["data"])

            # Check if it's already a WAV file (starts with RIFF) or raw PCM
            if raw_audio_bytes[:4] == b"RIFF":
                wav_bytes = raw_audio_bytes
            else:
                # Default Gemini audio sample rate is typically 24000 Hz 16-bit PCM
                sample_rate = 24000
                if "rate=" in mime_type:
                    try:
                        rate_part = mime_type.split("rate=")[-1]
                        sample_rate = int(re.split(r"[^\d]", rate_part)[0])
                    except Exception:
                        sample_rate = 24000
                wav_bytes = pcm_to_wav(raw_audio_bytes, sample_rate=sample_rate, channels=1)

            # Save temporary WAV
            temp_wav_path = TEMP_DIR / f"temp_tts_input_{abs(hash(text)) & 0xFFFFFFFF}.wav"
            with open(temp_wav_path, "wb") as f:
                f.write(wav_bytes)

            return temp_wav_path

        except Exception as e:
            if isinstance(e, (RuntimeError, ValueError)):
                raise
            raise RuntimeError(f"Fehler beim Verarbeiten der Audiodaten: {str(e)}")
