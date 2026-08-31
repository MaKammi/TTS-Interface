"""
Gemini TTS Service module with Smart Chunking & Long-Text Support
Handles communication with the Gemini API to generate audio from text of any length.
"""

import base64
import wave
import io
import re
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

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
    """Standardize inline audio tags into Gemini's recognized directives."""
    processed = text
    for pattern, replacement in TAG_REPLACEMENTS.items():
        processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)
    return processed.strip()


def split_text_into_chunks(text: str, max_chunk_chars: int = 300) -> List[str]:
    """
    Splits long text intelligently at sentence/paragraph boundaries to prevent timeouts.
    """
    cleaned = text.strip()
    if len(cleaned) <= max_chunk_chars:
        return [cleaned]

    paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) + 1 <= max_chunk_chars:
            current_chunk = f"{current_chunk} {paragraph}".strip() if current_chunk else paragraph
            continue

        if current_chunk:
            chunks.append(current_chunk)
            current_chunk = ""

        if len(paragraph) <= max_chunk_chars:
            current_chunk = paragraph
            continue

        # Split paragraph into sentences
        sentences = re.split(r'(?<=[.!?…])\s+', paragraph)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(current_chunk) + len(sentence) + 1 <= max_chunk_chars:
                current_chunk = f"{current_chunk} {sentence}".strip() if current_chunk else sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                
                if len(sentence) > max_chunk_chars:
                    sub_parts = re.split(r'(?<=[,;:])\s+', sentence)
                    for sub in sub_parts:
                        if len(current_chunk) + len(sub) + 1 <= max_chunk_chars:
                            current_chunk = f"{current_chunk} {sub}".strip() if current_chunk else sub
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = sub
                else:
                    current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [cleaned]


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
    """Service for interacting with Gemini Text-to-Speech API with chunking & fallback support."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_api_key()

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    def _call_single_model(
        self,
        text_chunk: str,
        voice_name: str,
        model: str,
        current_key: str
    ) -> Optional[bytes]:
        """Make a single API call for one chunk to a specific model."""
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={current_key}"
        
        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": text_chunk}
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
            timeout=120
        )

        if response.status_code != 200:
            return None

        res_json = response.json()
        candidates = res_json.get("candidates", [])
        if not candidates:
            return None
        
        parts = candidates[0].get("content", {}).get("parts", [])
        audio_part = None
        for p in parts:
            if "inlineData" in p:
                audio_part = p["inlineData"]
                break
        
        if not audio_part or "data" not in audio_part:
            return None

        raw_bytes = base64.b64decode(audio_part["data"])

        # Strip RIFF header if present to get raw PCM frames
        if raw_bytes[:4] == b"RIFF":
            try:
                with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                    return wf.readframes(wf.getnframes())
            except Exception:
                return raw_bytes[44:]

        return raw_bytes

    def generate_speech(
        self,
        text: str,
        voice_name: str = "Puck",
        model: str = "gemini-3.1-flash-tts-preview",
        language: str = "auto",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Path:
        """
        Generates audio from text using Gemini TTS with chunking and saves it as a WAV file in TEMP_DIR.
        """
        current_key = self.api_key or get_api_key()
        if not current_key or current_key.strip() == "":
            raise ValueError("Kein Gemini API-Key angegeben. Bitte trage deinen API-Key in den Einstellungen ein.")

        if not text or not text.strip():
            raise ValueError("Bitte gib einen Text für die Sprachgenerierung ein.")

        processed_text = preprocess_text_for_gemini(text)
        chunks = split_text_into_chunks(processed_text, max_chunk_chars=300)
        total_chunks = len(chunks)

        all_pcm_frames = []
        fallback_model = "gemini-2.5-flash-preview-tts" if model != "gemini-2.5-flash-preview-tts" else "gemini-2.5-pro-preview-tts"

        for idx, chunk in enumerate(chunks):
            if progress_callback:
                progress_val = idx / (total_chunks + 0.3)
                progress_callback(
                    progress_val,
                    f"Generiere Abschnitt {idx + 1} von {total_chunks}..."
                )

            # Try primary model first, fallback if necessary
            pcm_chunk = self._call_single_model(chunk, voice_name, model, current_key)
            
            if pcm_chunk is None:
                # Try fallback model
                pcm_chunk = self._call_single_model(chunk, voice_name, fallback_model, current_key)

            if pcm_chunk is None:
                raise RuntimeError(
                    f"Fehler bei der Audio-Synthese von Abschnitt {idx + 1}. Bitte überprüfe deine Netzwerkverbindung oder versuche einen kürzeren Text."
                )

            all_pcm_frames.append(pcm_chunk)

        # Seamlessly join all chunks
        combined_pcm = b"".join(all_pcm_frames)
        wav_bytes = pcm_to_wav(combined_pcm, sample_rate=24000, channels=1)

        # Save temporary WAV
        temp_wav_path = TEMP_DIR / f"temp_tts_input_{abs(hash(text)) & 0xFFFFFFFF}.wav"
        with open(temp_wav_path, "wb") as f:
            f.write(wav_bytes)

        if progress_callback:
            progress_callback(0.9, "Audio-Synthese abgeschlossen. Konvertiere Format...")

        return temp_wav_path
