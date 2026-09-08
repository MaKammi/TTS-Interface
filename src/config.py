"""
Configuration and constants for Gemini TTS Interface
"""

import os
from pathlib import Path
from dotenv import load_dotenv, set_key

import sys

# Paths - support both frozen EXE and script mode
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# Load environment variables (from .env next to exe/script or current dir)
load_dotenv(ENV_FILE)
if not os.getenv("GEMINI_API_KEY") and (Path.cwd() / ".env").exists():
    load_dotenv(Path.cwd() / ".env")

# API Configuration
DEFAULT_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")

# Available Gemini Models for TTS
AVAILABLE_MODELS = [
    {"id": "gemini-3.1-flash-tts-preview", "name": "Gemini 3.1 Flash TTS (Standard & Neueste Version)"},
    {"id": "gemini-2.5-flash-preview-tts", "name": "Gemini 2.5 Flash TTS"},
    {"id": "gemini-2.5-pro-preview-tts", "name": "Gemini 2.5 Pro TTS (Studio-Qualität)"},
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
]

# Available Gemini Prebuilt Voices (Alle verfügbaren Stimmen inkl. Erinome)
AVAILABLE_VOICES = [
    {"id": "Erinome", "name": "Erinome", "desc": "Natürlich, sympathisch & klar (Weiblich)"},
    {"id": "Puck", "name": "Puck", "desc": "Freundlich & gesprächig (Neutral/Männlich)"},
    {"id": "Charon", "name": "Charon", "desc": "Tief, autoritär & informativ (Männlich)"},
    {"id": "Kore", "name": "Kore", "desc": "Ruhig, klar & besonnen (Weiblich)"},
    {"id": "Fenrir", "name": "Fenrir", "desc": "Kraftvoll, dynamisch & markant (Männlich)"},
    {"id": "Aoede", "name": "Aoede", "desc": "Melodisch, warm & lebendig (Weiblich)"},
    {"id": "Leda", "name": "Leda", "desc": "Sanft, melodisch & professionell (Weiblich)"},
    {"id": "Orus", "name": "Orus", "desc": "Warm, vertrauenswürdig & resonant (Männlich)"},
    {"id": "Zephyr", "name": "Zephyr", "desc": "Leicht, modern & präzise (Neutral/Weiblich)"},
    {"id": "Callirrhoe", "name": "Callirrhoe", "desc": "Sanft, getragen & einfühlsam (Weiblich)"},
    {"id": "Despina", "name": "Despina", "desc": "Lebhaft, enthusiastisch & freundlich (Weiblich)"},
    {"id": "Iapetus", "name": "Iapetus", "desc": "Tief, sonor & erzählerisch (Männlich)"},
    {"id": "Algieba", "name": "Algieba", "desc": "Hell, dynamisch & ausdrucksstark (Weiblich)"},
    {"id": "Algenib", "name": "Algenib", "desc": "Klar, artikuliert & souverän (Männlich)"},
    {"id": "Lyra", "name": "Lyra", "desc": "Melodisch, harmonisch & warm (Weiblich)"},
    {"id": "Sadaltager", "name": "Sadaltager", "desc": "Resonant, ruhig & ausgewogen (Männlich)"},
    {"id": "Sadachbia", "name": "Sadachbia", "desc": "Ausdrucksstark, warm & präsent (Weiblich)"},
    {"id": "Ursa", "name": "Ursa", "desc": "Kraftvoll, präsent & selbstbewusst (Weiblich)"},
]

# Translation & Instruction Configuration
TRANSLATION_MODEL = "gemini-3.8-flash"

# Style & Tone Suggestions for System-Prompt
STYLE_SUGGESTIONS = [
    ("Keine Regieanweisung (Standard)", ""),
    ("Ruhig, professionell & sachlich (Dokumentation)", "calm, professional, informative, documentary style"),
    ("Warm, freundlich & vertrauenswürdig (Erklärvideo)", "warm, friendly, approachable, trustworthy"),
    ("Lebhaft, enthusiastisch & dynamisch (Social Media / Werbung)", "enthusiastic, energetic, lively, dynamic"),
    ("Sanft, einfühlsam & entspannend (Hörbuch / Meditation)", "gentle, soothing, soft, storytelling tone"),
    ("Dramatisch, tief & geheimnisvoll (Krimi / Hörspiel)", "dramatic, deep, mysterious, suspenseful"),
]

# Supported Languages (32 Welt- und Regionalsprachen)
SUPPORTED_LANGUAGES = [
    {"id": "auto", "name": "🌐 Automatisch erkennen (Auto-Detect)"},
    {"id": "de", "name": "🇩🇪 Deutsch"},
    {"id": "en", "name": "🇬🇧 Englisch (UK)"},
    {"id": "en-us", "name": "🇺🇸 Englisch (US)"},
    {"id": "fr", "name": "🇫🇷 Französisch"},
    {"id": "es", "name": "🇪🇸 Spanisch"},
    {"id": "it", "name": "🇮🇹 Italienisch"},
    {"id": "pt", "name": "🇵🇹 Portugiesisch"},
    {"id": "pt-br", "name": "🇧🇷 Portugiesisch (Brasilien)"},
    {"id": "nl", "name": "🇳🇱 Niederländisch"},
    {"id": "pl", "name": "🇵🇱 Polnisch"},
    {"id": "sv", "name": "🇸🇪 Schwedisch"},
    {"id": "no", "name": "🇳🇴 Norwegisch"},
    {"id": "da", "name": "🇩🇰 Dänisch"},
    {"id": "fi", "name": "🇫🇮 Finnisch"},
    {"id": "tr", "name": "🇹🇷 Türkisch"},
    {"id": "el", "name": "🇬🇷 Griechisch"},
    {"id": "cs", "name": "🇨🇿 Tschechisch"},
    {"id": "ro", "name": "🇷🇴 Rumänisch"},
    {"id": "hu", "name": "🇭🇺 Ungarisch"},
    {"id": "uk", "name": "🇺🇦 Ukrainisch"},
    {"id": "ru", "name": "🇷🇺 Russisch"},
    {"id": "ja", "name": "🇯🇵 Japanisch"},
    {"id": "ko", "name": "🇰🇷 Koreanisch"},
    {"id": "zh", "name": "🇨🇳 Chinesisch (Mandarin)"},
    {"id": "hi", "name": "🇮🇳 Hindi"},
    {"id": "ar", "name": "🇸🇦 Arabisch"},
    {"id": "id", "name": "🇮🇩 Indonesisch"},
    {"id": "vi", "name": "🇻🇳 Vietnamesisch"},
    {"id": "th", "name": "🇹🇭 Thailändisch"},
    {"id": "bg", "name": "🇧🇬 Bulgarisch"},
    {"id": "hr", "name": "🇭🇷 Kroatisch"},
]

# Audio Emotion & Style Tags (Display Name, Tag Text, Tooltip/Description, Category)
AUDIO_TAGS = [
    {"display": "😂 Lachen", "tag": "[lachen]", "gemini_tag": "[laugh]", "desc": "Lachen oder belustigter Ton"},
    {"display": "🤫 Flüstern", "tag": "[flüstern]", "gemini_tag": "[whisper]", "desc": "Geflüsterter, leiser Ton"},
    {"display": "😢 Traurig", "tag": "[traurig]", "gemini_tag": "[sad]", "desc": "Gedrückte, traurige Stimmlage"},
    {"display": "✨ Begeistert", "tag": "[begeistert]", "gemini_tag": "[excited]", "desc": "Energiegeladen und enthusiastisch"},
    {"display": "⏸️ Pause", "tag": "[Pause]", "gemini_tag": "[pause]", "desc": "Kurze Sprechpause einlegen"},
    {"display": "😮‍💨 Seufzen", "tag": "[seufzen]", "gemini_tag": "[sigh]", "desc": "Hörbares Seufzen"},
    {"display": "😠 Wütend", "tag": "[wütend]", "gemini_tag": "[angry]", "desc": "Verärgerte, energische Betonung"},
    {"display": "🤔 Nachdenklich", "tag": "[nachdenklich]", "gemini_tag": "[thoughtful]", "desc": "Zögernd, reflektierend"},
    {"display": "🐢 Langsam", "tag": "[langsam]", "gemini_tag": "[slow]", "desc": "Verlangsamtes Sprechtempo"},
    {"display": "🐇 Schnell", "tag": "[schnell]", "gemini_tag": "[fast]", "desc": "Erhöhtes Sprechtempo"},
]

# Audio Format Presets
AUDIO_PRESETS = {
    "web_aac_mono_64k": {
        "name": "🌐 Web-Optimiert (AAC-LC Mono 64k FastStart) [Standard]",
        "extension": ".mp4",
        "codec": "aac",
        "channels": 1,
        "sample_rate": 44100,
        "bitrate": "64k",
        "faststart": True,
        "desc": "Höchste Browser-Kompatibilität, 50% Bandbreitenersparnis, Streaming-optimiert"
    },
    "web_m4a_aac_mono_64k": {
        "name": "🎵 M4A Web (AAC-LC Mono 64k FastStart)",
        "extension": ".m4a",
        "codec": "aac",
        "channels": 1,
        "sample_rate": 48000,
        "bitrate": "64k",
        "faststart": True,
        "desc": "M4A Container, 48 kHz Abtastrate, FastStart Flag"
    },
    "hq_m4a_stereo_128k": {
        "name": "🎧 High Quality M4A (AAC-LC Stereo 128k)",
        "extension": ".m4a",
        "codec": "aac",
        "channels": 2,
        "sample_rate": 48000,
        "bitrate": "128k",
        "faststart": True,
        "desc": "Hohe Audioqualität für Podcasts und Musikplayer"
    },
    "mp3_standard_192k": {
        "name": "📻 MP3 Standard (192 kbit/s Stereo)",
        "extension": ".mp3",
        "codec": "libmp3lame",
        "channels": 2,
        "sample_rate": 44100,
        "bitrate": "192k",
        "faststart": False,
        "desc": "Klassisches MP3-Format für universelle Abspielbarkeit"
    },
    "wav_uncompressed": {
        "name": "💿 Unkomprimiert (WAV PCM 44.1 kHz)",
        "extension": ".wav",
        "codec": "pcm_s16le",
        "channels": 1,
        "sample_rate": 44100,
        "bitrate": None,
        "faststart": False,
        "desc": "Verlustfreie Studio-Qualität"
    },
    "custom": {
        "name": "⚙️ Benutzerdefiniert...",
        "extension": ".mp4",
        "codec": "aac",
        "channels": 1,
        "sample_rate": 44100,
        "bitrate": "64k",
        "faststart": True,
        "desc": "Individuelle Einstellungen festlegen"
    }
}


def save_api_key(api_key: str):
    """Save API key to .env file and environment."""
    os.environ["GEMINI_API_KEY"] = api_key
    set_key(str(ENV_FILE), "GEMINI_API_KEY", api_key)


def get_api_key() -> str:
    """Retrieve current API key."""
    return os.getenv("GEMINI_API_KEY", "")
