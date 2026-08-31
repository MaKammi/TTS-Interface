# Gemini TTS Studio (Windows)

Ein modernes, professionelles Windows Desktop-Interface zur Text-in-Sprache-Umwandlung (Text-to-Speech) basierend auf der **Google Gemini API**. 

Unterstützt native **Audio-Tags / Regieanweisungen** (z. B. `[lachen]`, `[flüstern]`, `[traurig]`, `[begeistert]`, `[Pause]`), eine reiche Stimmenauswahl, automatische Spracherkennung, **Smart Chunking für lange Texte** und eine präzise AAC/MP4/M4A-Audiokonvertierung via FFmpeg inkl. Fast-Start-Flag für Web-Streaming.

---

## 📑 Inhaltsverzeichnis

- [Features](#features)
- [Schnellstart](#schnellstart)
- [Standalone EXE erstellen](#standalone-exe-erstellen)
- [Architektur & Entwickler-Dokumentation](#architektur--entwickler-dokumentation)
- [FFmpeg Konvertierungs-Profil](#ffmpeg-konvertierungs-profil)
- [Lizenz](#lizenz)

---

## Features

- 🎙️ **Gemini TTS Engine**: Nutzung moderner Gemini-Modelle (`gemini-3.1-flash-tts-preview` / `gemini-2.5-flash-preview-tts`).
- 🎭 **Audio-Tags & Emotionen**: Unterstützung von Regieanweisungen im Text (z. B. `[lachen]`, `[traurig]`, `[flüstern]`, `[begeistert]`, `[Pause]`, `[seufzen]`).
- 📜 **Smart Chunking (Keine Timeouts bei langen Texten)**: Zerlegt lange Texte automatisch an Satz- und Absatzgrenzen und fügt die Audiodaten nahtlos zusammen.
- 👥 **Stimmenauswahl**: Auswahl aus Charakterstimmen (*Puck*, *Charon*, *Kore*, *Fenrir*, *Aoede*, *Leda*, *Orus*, *Zephyr*).
- 🌐 **Sprachauswahl**: Automatische Spracherkennung oder feste Vorgabe (Deutsch, Englisch, etc.).
- 🎛️ **Optimierte Audio-Formate**:
  - Standard-Preset: **AAC-LC**, **Mono**, **64 kbit/s**, **44.100 Hz / 48.000 Hz**, Container: **MP4 / M4A** mit `+faststart` Streaming-Flag.
  - Weitere Formate: MP3 (192k), verlustfreies WAV sowie freier Modus („Benutzerdefiniert“).
  - Einklappbares Design für maximalen Platz und Übersicht.
- 🔊 **Integrierter Audio-Player mit Scrubbing**: Flüssiges Spulen mit der Maus, Pause, Lautstärkeregelung.
- 💾 **Export-Dialog**: Lokales Abspeichern der fertigen Datei per Windows-Dateidialog.
- 📦 **Standalone Portable EXE**: Kann ohne Python-Installation direkt auf jedem Windows-Rechner ausgeführt werden.

---

## Schnellstart

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

### 3. API-Key einrichten
Erstelle eine `.env`-Datei im Hauptverzeichnis (oder kopiere `.env.example`):
```env
GEMINI_API_KEY=dein_gemini_api_key
```
*(Alternativ kann der API-Key direkt in der App über den Button `🔑 API-Key` eingegeben werden.)*

### 4. Anwendung starten
```bash
python main.py
```

---

## Standalone EXE erstellen

Um eine eigenständige Windows-Programmdatei (`dist/GeminiTTSStudio.exe`) zu erstellen, die auf jedem Windows-PC ohne Python läuft:
```bash
python build_exe.py
```
*(Oder einfach per Doppelklick auf `build.bat` ausführen.)*

---

## Architektur & Entwickler-Dokumentation

Für Entwickler und KI-Assistenten stehen im Verzeichnis [`docs/`](docs/) ausführliche Dokumente bereit:
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**: Vollständige Systemarchitektur, Datenfluss-Diagramme, Modul-Spezifikationen und FFmpeg-Pipeline.
- **[docs/AI_HANDOVER.md](docs/AI_HANDOVER.md)**: Handover-Leitfaden für nachfolgende KI-Agenten, API-Besonderheiten, Lessons Learned und Roadmap.

---

## FFmpeg Konvertierungs-Profil

Das integrierte Web-Optimierungs-Preset nutzt folgenden FFmpeg-Befehl:
```bash
ffmpeg -i eingabe.wav -c:a aac -b:a 64k -ac 1 -ar 44100 -movflags +faststart ausgabe.mp4
```

---

## Lizenz
Privates Repository für MaKammi.
