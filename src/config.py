"""
Configuration and constants for Gemini TTS Interface
"""

import json
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
CUSTOM_STYLES_FILE = BASE_DIR / "custom_styles.json"
CUSTOM_VOICES_FILE = BASE_DIR / "custom_voices.json"

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)


def load_custom_styles() -> dict:
    """Load user-defined style presets from custom_styles.json."""
    if CUSTOM_STYLES_FILE.exists():
        try:
            with open(CUSTOM_STYLES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_custom_style(name: str, directive: str):
    """Save a user-defined style preset."""
    styles = load_custom_styles()
    styles[name] = directive
    with open(CUSTOM_STYLES_FILE, "w", encoding="utf-8") as f:
        json.dump(styles, f, ensure_ascii=False, indent=2)


def delete_custom_style(name: str):
    """Delete a user-defined style preset."""
    styles = load_custom_styles()
    if name in styles:
        del styles[name]
        with open(CUSTOM_STYLES_FILE, "w", encoding="utf-8") as f:
            json.dump(styles, f, ensure_ascii=False, indent=2)


def load_custom_voices() -> list:
    """Load user-created or imported custom voices from custom_voices.json."""
    if CUSTOM_VOICES_FILE.exists():
        try:
            with open(CUSTOM_VOICES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_custom_voice(voice_data: dict):
    """Save or update a custom voice definition."""
    voices = load_custom_voices()
    updated = False
    for i, v in enumerate(voices):
        if v.get("id") == voice_data.get("id"):
            voices[i] = voice_data
            updated = True
            break
    if not updated:
        voices.insert(0, voice_data)
    with open(CUSTOM_VOICES_FILE, "w", encoding="utf-8") as f:
        json.dump(voices, f, ensure_ascii=False, indent=2)


def delete_custom_voice(voice_id: str):
    """Delete a custom voice definition."""
    voices = load_custom_voices()
    voices = [v for v in voices if v.get("id") != voice_id]
    with open(CUSTOM_VOICES_FILE, "w", encoding="utf-8") as f:
        json.dump(voices, f, ensure_ascii=False, indent=2)


def get_all_voices() -> list:
    """Return all voices combining prebuilt voices and user custom voices."""
    custom = load_custom_voices()
    formatted_custom = []
    for c in custom:
        formatted_custom.append({
            "id": c.get("id"),
            "name": c.get("name", c.get("id")),
            "desc": c.get("desc", "Eigene Stimme"),
            "category": "🎙️ Eigene / Geklonte Stimmen",
            "type": c.get("type", "prompted"),
            "sample_audio": c.get("sample_audio", "")
        })
    return formatted_custom + AVAILABLE_VOICES


# Load environment variables (from .env next to exe/script or current dir)
load_dotenv(ENV_FILE)
if not os.getenv("GEMINI_API_KEY") and (Path.cwd() / ".env").exists():
    load_dotenv(Path.cwd() / ".env")

# Application & Update Configuration
APP_VERSION = "2.3.0"
GITHUB_REPO = "MaKammi/TTS-Interface"

# API Configuration
DEFAULT_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")

# Available Gemini Models for TTS
AVAILABLE_MODELS = [
    {"id": "gemini-3.8-flash-tts", "name": "Gemini 3.8 Flash TTS (Studio-Qualität & Neueste Version)"},
    {"id": "gemini-3.8-flash-lite-tts", "name": "Gemini 3.8 Flash Lite TTS (High-Speed & Massenverarbeitung)"},
    {"id": "gemini-3.1-flash-tts-preview", "name": "Gemini 3.1 Flash TTS (Bewährte Version)"},
    {"id": "gemini-2.5-flash-preview-tts", "name": "Gemini 2.5 Flash TTS"},
    {"id": "gemini-2.5-pro-preview-tts", "name": "Gemini 2.5 Pro TTS (Studio-Qualität)"},
]

# Available Gemini Prebuilt Voices (Kuratierte Auswahl aus 50+ Stimmen inkl. nativer deutscher Rollen)
AVAILABLE_VOICES = [
    # Top-Klassiker & Allrounder
    {"id": "Erinome", "name": "Erinome", "desc": "Natürlich, sympathisch & klar (Weiblich)", "category": "⭐ Favoriten & Allrounder"},
    {"id": "Puck", "name": "Puck", "desc": "Freundlich, gesprächig & lebendig (Männlich)", "category": "⭐ Favoriten & Allrounder"},
    {"id": "Charon", "name": "Charon", "desc": "Tief, autoritär & informativ (Männlich)", "category": "⭐ Favoriten & Allrounder"},
    {"id": "Kore", "name": "Kore", "desc": "Ruhig, klar & besonnen (Weiblich)", "category": "⭐ Favoriten & Allrounder"},
    {"id": "Fenrir", "name": "Fenrir", "desc": "Kraftvoll, dynamisch & markant (Männlich)", "category": "⭐ Favoriten & Allrounder"},
    {"id": "Aoede", "name": "Aoede", "desc": "Melodisch, warm & lebendig (Weiblich)", "category": "⭐ Favoriten & Allrounder"},
    {"id": "Leda", "name": "Leda", "desc": "Sanft, melodisch & professionell (Weiblich)", "category": "⭐ Favoriten & Allrounder"},
    {"id": "Orus", "name": "Orus", "desc": "Warm, vertrauenswürdig & resonant (Männlich)", "category": "⭐ Favoriten & Allrounder"},
    {"id": "Zephyr", "name": "Zephyr", "desc": "Leicht, modern & präzise (Weiblich/Neutral)", "category": "⭐ Favoriten & Allrounder"},

    # Deutsche Rollen-Personas (Google Native DE)
    {"id": "Authoritative Advisor 1", "name": "Authoritative Advisor 1", "desc": "Anwältin / Sachlich, klar & objektiv (Weiblich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Authoritative Advisor 2", "name": "Authoritative Advisor 2", "desc": "Anwalt / Souverän, natürlich & fundiert (Männlich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Authoritative Advisor 10", "name": "Authoritative Advisor 10", "desc": "Arzt / Freundlich, ruhig & vertrauensvoll (Männlich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Authoritative Advisor 4", "name": "Authoritative Advisor 4", "desc": "Ärztin / Klar, besonnen & helfend (Weiblich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Authoritative Advisor 11", "name": "Authoritative Advisor 11", "desc": "Wissenschaftler / Nachdenklich & beruhigend (Männlich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Authoritative Advisor 5", "name": "Authoritative Advisor 5", "desc": "Finanzberaterin / Strukturiert & kompetent (Weiblich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Tutor 1", "name": "Tutor 1", "desc": "Professorin / Akademisch, didaktisch & präzise (Weiblich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Tutor 2", "name": "Tutor 2", "desc": "Lehrer / Geduldig, anschaulich & freundlich (Männlich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Tutor 3", "name": "Tutor 3", "desc": "Motivationstrainerin / Dynamisch, aktivierend (Weiblich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Training Voiceover 1", "name": "Training Voiceover 1", "desc": "Moderatorin / Freundlich, einladend, Video-Host (Weiblich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Training Voiceover 12", "name": "Training Voiceover 12", "desc": "Schulungsleiter / Klar, instruktiv & geduldig (Männlich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Digital Assistant 5", "name": "Digital Assistant 5", "desc": "Erzählerin / Warm, nahbar & einfühlsam (Weiblich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Call Center Agent 10", "name": "Call Center Agent 10", "desc": "Kundenservice / Hilfsbereit & zuvorkommend (Weiblich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Commercial Voiceover 2", "name": "Commercial Voiceover 2", "desc": "Werbung & Medien / Ausdrucksstark & modern (Weiblich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},
    {"id": "Commercial Voiceover 3", "name": "Commercial Voiceover 3", "desc": "Werbung & Medien / Frisch, dynamisch & werblich (Männlich)", "category": "🇩🇪 Deutsche Stimmen & Rollen"},

    # Erweiterte Hörbuch- & Storyteller-Stimmen
    {"id": "Achernar", "name": "Achernar", "desc": "Sanft, leise & meditativ (Weiblich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Achird", "name": "Achird", "desc": "Warm, nahbar & natürlich (Männlich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Algenib", "name": "Algenib", "desc": "Sonor, geerdet & markant (Männlich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Algieba", "name": "Algieba", "desc": "Hell, dynamisch & ausdrucksstark (Weiblich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Alnilam", "name": "Alnilam", "desc": "Ruhig, getragen & sonor (Männlich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Callirrhoe", "name": "Callirrhoe", "desc": "Sanft, getragen & einfühlsam (Weiblich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Despina", "name": "Despina", "desc": "Lebhaft, enthusiastisch & freundlich (Weiblich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Iapetus", "name": "Iapetus", "desc": "Tief, sonor & erzählerisch (Männlich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Lyra", "name": "Lyra", "desc": "Melodisch, harmonisch & warm (Weiblich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Sadaltager", "name": "Sadaltager", "desc": "Resonant, ruhig & ausgewogen (Männlich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Sadachbia", "name": "Sadachbia", "desc": "Ausdrucksstark, warm & präsent (Weiblich)", "category": "📖 Erzähler & Storytelling"},
    {"id": "Ursa", "name": "Ursa", "desc": "Kraftvoll, präsent & selbstbewusst (Weiblich)", "category": "📖 Erzähler & Storytelling"},
]

# Translation & Instruction Configuration
TRANSLATION_MODEL = "gemini-3.6-flash"

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

# Audio Emotion & Style Tags (Display Name, Tag Text, Native Gemini Tag, Tooltip/Description)
AUDIO_TAGS = [
    {"display": "😂 Lachen", "tag": "[lachen]", "gemini_tag": "<laughs>", "desc": "Hörbares, natürliches Lachen oder Heiterkeit"},
    {"display": "😮‍💨 Seufzen", "tag": "[seufzen]", "gemini_tag": "<sigh>", "desc": "Hörbares Seufzen oder emotionale Entlastung"},
    {"display": "😮 Einatmen", "tag": "[einatmen]", "gemini_tag": "<gasp>", "desc": "Überraschtes oder tiefes Luftholen / Gasp"},
    {"display": "🗣️ Räuspern", "tag": "[räuspern]", "gemini_tag": "<throat-clearing>", "desc": "Hörbares Räuspern vor dem Weitersprechen"},
    {"display": "🤝 Zustimmung (mhm)", "tag": "[mhm]", "gemini_tag": "|mhm|", "desc": "Natürliches bejahendes / zustimmendes Brummen"},
    {"display": "🤫 Flüstern", "tag": "[flüstern]", "gemini_tag": "[whispering]", "desc": "Geflüsterter, leiser und intimer Ton"},
    {"display": "⏸️ Pause", "tag": "[Pause]", "gemini_tag": "[pause]", "desc": "Kurze, wirkungsvolle Sprechpause einlegen"},
    {"display": "✨ Begeistert", "tag": "[begeistert]", "gemini_tag": "[excited]", "desc": "Energiegeladen und enthusiastisch"},
    {"display": "🤔 Nachdenklich", "tag": "[nachdenklich]", "gemini_tag": "[thoughtful]", "desc": "Zögernd, reflektierend und bedacht"},
    {"display": "😢 Traurig", "tag": "[traurig]", "gemini_tag": "[sad]", "desc": "Gedrückte, melancholische Stimmlage"},
    {"display": "🐢 Langsam", "tag": "[langsam]", "gemini_tag": "[slow]", "desc": "Deutlich verlangsamtes Sprechtempo"},
    {"display": "🐇 Schnell", "tag": "[schnell]", "gemini_tag": "[fast]", "desc": "Erhöhtes, dynamisches Sprechtempo"},
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
