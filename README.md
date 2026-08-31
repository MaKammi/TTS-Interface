# Gemini TTS-Interface (Windows)

Ein modernes Windows Desktop-Interface zur Sprachgenerierung (Text-to-Speech) basierend auf der **Google Gemini API**. 

Unterstützt native **Audio-Tags / Regieanweisungen** (z. B. Emotionen, Lachen, Flüstern, Sprechpausen), verschiedene Stimmen, automatische Spracherkennung und hochgradig anpassbare Audio-Exporte (insbesondere Web-optimiertes AAC-LC in MP4/M4A mit Fast-Start-Flag via FFmpeg).

---

## Features

- 🎙️ **Gemini TTS Engine**: Nutzung moderner Gemini-Modelle mit nativer Audioausgabe.
- 🎭 **Audio-Tags / Emotionen**: Unterstützung von Regieanweisungen im Text (z. B. `[lachen]`, `[traurig]`, `[flüstern]`, `[begeistert]`, `[Pause]`, `[seufzen]`).
- 👥 **Stimmenauswahl**: Auswahl aus verschiedenen Charakterstimmen (z. B. *Puck*, *Charon*, *Kore*, *Fenrir*, *Aoede* etc.).
- 🌐 **Sprachauswahl**: Automatische Spracherkennung oder feste Vorgabe (Deutsch, Englisch, etc.).
- ⚙️ **Optimierte Audio-Formate**:
  - Standard-Preset: **AAC-LC**, **Mono**, **64 kbit/s**, **44.100 Hz / 48.000 Hz**, Container: **MP4 / M4A** mit `+faststart` Streaming-Flag.
  - Weitere Formate: MP3, unkomprimiertes WAV.
  - Einstellbare Bitraten, Kanäle (Mono/Stereo) und Abtastraten.
- 🔊 **Integrierter Audio-Player**: Sofortiges Probehören, Pause, Scrubbing und Lautstärkeregelung.
- 💾 **Export-Dialog**: Komfortables Abspeichern der generierten Audiodatei auf dem Rechner.

---

## Installation & Start

### 1. Repository klonen
```bash
git clone https://github.com/MaKammi/TTS-Interface.git
cd TTS-Interface
```

### 2. Abhängigkeiten installieren
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. API-Key konfigurieren
Erstelle eine `.env`-Datei im Hauptverzeichnis (oder kopiere `.env.example`):
```env
GEMINI_API_KEY=dein_gemini_api_key
```
*(Alternativ kann der API-Key auch direkt in den Einstellungen der App eingegeben werden.)*

### 4. Anwendung starten
```bash
python main.py
```

---

## FFmpeg Konvertierungsbefehl (Referenz)

Das Web-Optimierungs-Preset nutzt folgenden FFmpeg-Befehl:
```bash
ffmpeg -i eingabe.wav -c:a aac -b:a 64k -ac 1 -ar 44100 -movflags +faststart ausgabe.mp4
```

---

## Lizenz
Private Repository für MaKammi.
