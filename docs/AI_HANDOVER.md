# KI-Handover & Developer Guide

Dieses Dokument richtet sich an nachfolgende **KI-Agenten (Gemini, Claude, GPT, Cursor, Copilot etc.)** und menschliche Entwickler. Es fasst die getroffenen Designentscheidungen, bekannte Fallstricke bei der Gemini TTS API, Testverfahren und Erweiterungsmöglichkeiten zusammen.

---

## 1. Quick Start für KI-Agenten

Wenn du als KI an diesem Projekt weiterarbeitest:
1. **Repository-Zustand prüfen**:
   ```bash
   git status
   ```
2. **Abhängigkeiten installieren**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Pipeline testen**:
   ```bash
   python test_tts.py
   ```
4. **App starten**:
   ```bash
   python main.py
   ```
5. **Windows EXE bauen**:
   ```bash
   python build_exe.py
   ```

---

## 2. Wichtige Erkenntnisse & "Lessons Learned" (Gemini TTS API)

### A. Modellwahl & Endpunkte
- Gemini verfügt über spezialisierte Text-to-Speech Preview-Modelle:
  - `gemini-3.1-flash-tts-preview` (Standard)
  - `gemini-2.5-flash-preview-tts` (stabiler Fallback)
- Ältere Modelle wie `gemini-2.0-flash` sind für reine Audioausgabe deprecated.
- **Wichtig**: Bei den reinen TTS-Modellen darf **kein** `systemInstruction`-Feld im JSON übergeben werden, da die API sonst mit einem internen Fehler abbricht. Die Regieanweisungen werden direkt als Inline-Tags im Prompt übergeben.

### B. Audio-Tags & Regieanweisungen
- Tags wie `[laugh]`, `[whisper]`, `[sad]`, `[excited]`, `[pause]`, `[sigh]`, `[slow]`, `[fast]` werden von Gemini nativ interpretiert und nicht vorgelesen.
- Der Vorverarbeiter in `src/tts_service.py` (`TAG_REPLACEMENTS`) sorgt dafür, dass deutsche Begriffe (z. B. `[lachen]` → `[laugh]`, `[flüstern]` → `[whisper]`) vor dem API-Aufruf automatisch gemappt werden.

### C. Umgang mit langen Texten & Timeouts (Smart Chunking)
- Ein einzelner HTTP-Request für Audio-Synthese neigt bei Texten ab ~400 Zeichen zu Timeouts (`Read timed out`).
- **Lösung**: `split_text_into_chunks()` in `src/tts_service.py` zerlegt den Text in logische Satzblöcke (~300 Zeichen), ruft die API sequentiell auf und verkettet die resultierenden 16-Bit-PCM-Daten nahtlos (`b"".join()`).
- Falls das 3.1-Modell bei einem Chunk einen leeren Stream meldet (`finishReason: SAFETY / Stream interrupted`), schaltet der Service für diesen Block automatisch auf `gemini-2.5-flash-preview-tts` um.

### D. Audio-Konvertierung & FastStart
- Gemini liefert PCM-Audio (24 kHz).
- FFmpeg kodiert das Audio in das vom Nutzer gewünschte Web-Standardprofil:
  ```bash
  ffmpeg -i eingabe.wav -c:a aac -b:a 64k -ac 1 -ar 44100 -movflags +faststart ausgabe.mp4
  ```
- Durch `imageio-ffmpeg` ist FFmpeg immer als Binärdatei enthalten, sodass der Endnutzer kein separates FFmpeg auf Windows installieren muss.

---

## 3. UI-Architektur & Besonderheiten

- **Framework**: `customtkinter`
- **AutoScrollableFrame**: Um zu verhindern, dass bei großen Fenstern ein permanenter grauer Scrollbalken angezeigt wird, überwacht `AutoScrollableFrame` die Canvas-Scrollposition:
  - Wenn `first <= 0.001 and last >= 0.999` (Inhalt passt komplett): Scrollbar wird via `grid_remove()` versteckt.
  - Wenn der Inhalt überläuft (Fenster verkleinert oder Formular aufgeklappt): Scrollbar wird via `grid()` eingeblendet.
- **Player-Scrubbing**: Der `timeline_slider` ist an `_on_seek_change` gebunden. Beim Ziehen mit der Maus wird `is_user_scrubbing = True` gesetzt, damit der periodische UI-Timer nicht gegen die Mausbewegung arbeitet.

---

## 4. Häufige Aufgaben & Erweiterungen (Roadmap)

1. **Neue Stimme hinzufügen**:
   In `src/config.py` im Array `AVAILABLE_VOICES` einen neuen Eintrag ergänzen (z. B. `{"id": "VoiceName", "name": "...", "desc": "..."}`).
2. **Neues Format-Preset hinzufügen**:
   In `src/config.py` im Dictionary `AUDIO_PRESETS` die Parameter eintragen (Codec, Kanäle, Abtastrate, Bitrate, FastStart).
3. **Batch-Generierung (Mehrere Texte / Dateien verarbeiten)**:
   Kann über eine Iteration von `GeminiTTSService.generate_speech()` und `convert_audio()` implementiert werden.
4. **Wellenform-Visualisierung (Waveform Canvas)**:
   In `src/gui.py` kann unter dem Player ein `tkinter.Canvas` für Audio-Wellenformen eingefügt werden.
