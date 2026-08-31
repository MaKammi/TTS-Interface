# KI-Handover & Developer Guide

Dieses Dokument richtet sich an nachfolgende **KI-Agenten (Gemini, Claude, GPT, Cursor, Copilot etc.)** und menschliche Entwickler. Es fasst die Architektur, getroffenen Entscheidungen, bekannte Fallstricke und Erweiterungsmöglichkeiten zusammen.

---

## 1. Quick Start für KI-Agenten

1. **Repository-Zustand prüfen**:
   ```bash
   git status
   ```
2. **Abhängigkeiten installieren**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Tests ausführen**:
   ```bash
   python test_tts.py
   python test_batch.py
   ```
4. **App im Entwicklungsmodus starten**:
   ```bash
   python main.py
   ```
5. **Standalone Windows EXE bauen**:
   ```bash
   python build_exe.py
   ```

---

## 2. Wichtige Module & Verantwortlichkeiten

| Modul | Zweck |
| :--- | :--- |
| `src/document_parser.py` | Extrahiert Text aus `.txt`, `.md`, `.pdf` (`pypdf`), `.docx` (`python-docx`), `.srt` und splittet Kapitel anhand von Überschriften (`# Kapitel`). |
| `src/batch_processor.py` | Verwaltet die Warteschlange (`BatchItem`) für Stapelverarbeitung, führt Jobs sequentiell aus und bietet Abbruchunterstützung. |
| `src/tts_service.py` | Gemini API Client, Tag-Übersetzung (`[lachen]` $\to$ `[laugh]`), Smart Chunking gegen Timeouts, PCM-Stitching & Modell-Fallback. |
| `src/audio_converter.py` | FFmpeg-Wrapper für AAC-LC Mono 64k FastStart MP4/M4A/MP3 Konvertierung. |
| `src/player.py` | Pygame Audio Player mit Scrubbing-Unterstützung (`seek`). |
| `src/gui.py` | CustomTkinter GUI mit Modus-Umschaltung (Einzeltext / Batch), `AutoScrollableFrame` (Auto-Hide Scrollbar) und Echtzeit-Status. |
| `src/config.py` | Stimmen, Modelle, Presets, Pfade und `.env`-Management (auch im PyInstaller frozen Mode). |

---

## 3. Bekannte Fallstricke & API-Besonderheiten

- **Gemini TTS Preview Endpunkte**: `gemini-3.1-flash-tts-preview` und `gemini-2.5-flash-preview-tts` akzeptieren **keine** `systemInstruction` im Payload (wirft sonst API-Fehler). Regieanweisungen werden direkt als Inline-Tags im Text übergeben.
- **Timeouts bei langen Texten**: Die Smart-Chunking-Engine in `src/tts_service.py` zerlegt Texte an Satzgrenzen in Blöcke à ~300 Zeichen und konkateniert die resultierenden PCM-Bytes nahtlos.
- **PyInstaller Bundling**: `build_exe.py` sammelt `--collect-all=customtkinter`, `--collect-all=imageio_ffmpeg`, `--collect-all=pygame`, `--collect-all=pypdf`, `--collect-all=docx` und prüft, ob die Ziel-EXE gerade geöffnet ist, um Sperrfehler zu vermeiden.

---

## 4. Nächste geplante Erweiterungen (Roadmap)

1. **Multi-Speaker / Skript-Modus**: Parsing von Sprecher-Präfixen wie `[Puck]: Hallo` und `[Aoede]: Hi` mit automatischer Stimmenzuweisung.
2. **Audio-Visualisierung**: Wellenform-Anzeige (Waveform) im Player.
3. **Audio-Ducking / Hintergrundmusik**: Sanftes Unterlegen von Ambient-Musik mit automatischer Absenkung bei Sprache.
