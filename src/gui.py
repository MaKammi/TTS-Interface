"""
Modern GUI for Gemini TTS Interface using CustomTkinter
"""

import os
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any

import customtkinter as ctk
from tkinter import filedialog, messagebox

from .config import (
    AVAILABLE_VOICES,
    AVAILABLE_MODELS,
    SUPPORTED_LANGUAGES,
    AUDIO_TAGS,
    AUDIO_PRESETS,
    get_api_key,
    save_api_key,
    OUTPUT_DIR,
    TEMP_DIR,
)
from .tts_service import GeminiTTSService
from .audio_converter import convert_audio, get_command_preview
from .player import AudioPlayer


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class APIKeyDialog(ctk.CTkToplevel):
    """Dialog for viewing and editing the Gemini API Key."""

    def __init__(self, parent, on_save_callback):
        super().__init__(parent)
        self.title("Gemini API-Key Einstellungen")
        self.geometry("520x240")
        self.resizable(False, False)
        self.on_save_callback = on_save_callback

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Container frame
        frame = ctk.CTkFrame(self, corner_radius=10)
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        lbl = ctk.CTkLabel(
            frame,
            text="🔑 Google Gemini API-Key",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        lbl.pack(pady=(15, 5))

        desc = ctk.CTkLabel(
            frame,
            text="Trage hier deinen API-Key aus Google AI Studio ein.\nDer Key wird sicher in deiner lokalen .env Datei gespeichert.",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        desc.pack(pady=(0, 10))

        self.key_entry = ctk.CTkEntry(
            frame,
            placeholder_text="AQ... oder AIzaSy...",
            show="*",
            width=400,
            height=35
        )
        self.key_entry.pack(pady=5)
        self.key_entry.insert(0, get_api_key())

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=(15, 10))

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Speichern",
            command=self._save,
            width=120,
            fg_color="#1f6aa5",
            hover_color="#144870"
        )
        save_btn.pack(side="left", padx=10)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            command=self.destroy,
            width=100,
            fg_color="gray",
            hover_color="#555"
        )
        cancel_btn.pack(side="left", padx=10)

        self.transient(parent)
        self.grab_set()

    def _save(self):
        new_key = self.key_entry.get().strip()
        if not new_key:
            messagebox.showwarning("Hinweis", "Bitte gib einen gültigen API-Key ein.")
            return
        save_api_key(new_key)
        if self.on_save_callback:
            self.on_save_callback(new_key)
        self.destroy()


class GeminiTTSApp(ctk.CTk):
    """Main application window for Gemini TTS Interface."""

    def __init__(self):
        super().__init__()

        self.title("🎙️ Gemini TTS Studio - Windows Interface")
        self.geometry("980x860")
        self.minsize(900, 750)

        self.tts_service = GeminiTTSService()
        self.player = AudioPlayer()
        
        self.current_generated_wav: Optional[Path] = None
        self.current_converted_file: Optional[Path] = None
        self.is_generating = False

        self._build_ui()
        self._setup_player_timer()
        self._update_ffmpeg_command_preview()

    def _build_ui(self):
        # Master grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ------------------ Header Bar ------------------
        header_frame = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color=("gray85", "gray17"))
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        title_label = ctk.CTkLabel(
            header_frame,
            text="🎙️ Gemini TTS Studio",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, padx=20, pady=12, sticky="w")

        # Key Status & Settings Button
        self.key_status_btn = ctk.CTkButton(
            header_frame,
            text=self._get_key_status_text(),
            command=self._open_api_key_dialog,
            width=160,
            height=30,
            fg_color="#2b3b4c",
            hover_color="#3b4f66"
        )
        self.key_status_btn.grid(row=0, column=2, padx=(0, 10), pady=12, sticky="e")

        theme_switch = ctk.CTkSwitch(
            header_frame,
            text="Dark Mode",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light"
        )
        theme_switch.select()
        theme_switch.grid(row=0, column=3, padx=15, pady=12, sticky="e")

        # ------------------ Main Scrollable Content ------------------
        main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=0)
        main_scroll.grid_columnconfigure(0, weight=1)

        # 1. TEXT INPUT CARD
        text_card = ctk.CTkFrame(main_scroll, corner_radius=10)
        text_card.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        text_card.grid_columnconfigure(0, weight=1)

        text_header_frame = ctk.CTkFrame(text_card, fg_color="transparent")
        text_header_frame.pack(fill="x", padx=15, pady=(12, 5))

        text_title = ctk.CTkLabel(
            text_header_frame,
            text="📝 Text für Sprachgenerierung",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        text_title.pack(side="left")

        self.char_counter_lbl = ctk.CTkLabel(
            text_header_frame,
            text="0 Zeichen | 0 Wörter",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.char_counter_lbl.pack(side="right")

        # Text input area
        self.text_input = ctk.CTkTextbox(
            text_card,
            height=130,
            font=ctk.CTkFont(size=14),
            wrap="word",
            border_width=1,
            border_color=("gray70", "gray30")
        )
        self.text_input.pack(fill="x", padx=15, pady=5)
        self.text_input.insert("0.0", "Hallo! Dies ist ein Test mit Gemini TTS. [lachen] Es ist wirklich erstaunlich, wie lebendig die Stimme klingt! [flüstern] Kannst du ein Geheimnis für dich behalten?")
        self.text_input.bind("<KeyRelease>", self._update_counters)
        self._update_counters()

        # Audio-Tags / Emotion Toolbar
        tag_section_frame = ctk.CTkFrame(text_card, fg_color="transparent")
        tag_section_frame.pack(fill="x", padx=15, pady=(5, 12))

        tag_title_lbl = ctk.CTkLabel(
            tag_section_frame,
            text="🎭 Audio-Tags einfügen (Cursor-Position):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#3b8ed0"
        )
        tag_title_lbl.pack(anchor="w", pady=(0, 4))

        # Flow of Tag buttons
        tag_buttons_frame = ctk.CTkFrame(tag_section_frame, fg_color="transparent")
        tag_buttons_frame.pack(fill="x", anchor="w")

        for tag_info in AUDIO_TAGS:
            btn = ctk.CTkButton(
                tag_buttons_frame,
                text=tag_info["display"],
                command=lambda t=tag_info["tag"]: self._insert_tag(t),
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color=("gray80", "gray25"),
                hover_color=("gray70", "gray35"),
                text_color=("black", "white")
            )
            btn.pack(side="left", padx=3, pady=2)

        # 2. VOICE, LANGUAGE & MODEL CONFIG CARD
        voice_card = ctk.CTkFrame(main_scroll, corner_radius=10)
        voice_card.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        voice_card.grid_columnconfigure((0, 1, 2), weight=1)

        # Voice Selector
        voice_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        voice_box.grid(row=0, column=0, padx=15, pady=12, sticky="nsew")
        
        ctk.CTkLabel(
            voice_box,
            text="🗣️ Stimme",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", pady=(0, 4))

        voice_options = [f"{v['id']} - {v['desc'].split('(')[-1].replace(')', '')}" for v in AVAILABLE_VOICES]
        self.voice_var = ctk.StringVar(value=voice_options[0])
        self.voice_menu = ctk.CTkOptionMenu(
            voice_box,
            values=voice_options,
            variable=self.voice_var,
            command=self._on_voice_changed,
            height=32
        )
        self.voice_menu.pack(fill="x")

        self.voice_desc_lbl = ctk.CTkLabel(
            voice_box,
            text=AVAILABLE_VOICES[0]["desc"],
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=260,
            justify="left"
        )
        self.voice_desc_lbl.pack(anchor="w", pady=(4, 0))

        # Language Selector
        lang_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        lang_box.grid(row=0, column=1, padx=15, pady=12, sticky="nsew")

        ctk.CTkLabel(
            lang_box,
            text="🌐 Sprache",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", pady=(0, 4))

        lang_options = [l["name"] for l in SUPPORTED_LANGUAGES]
        self.lang_var = ctk.StringVar(value=lang_options[0])
        self.lang_menu = ctk.CTkOptionMenu(
            lang_box,
            values=lang_options,
            variable=self.lang_var,
            height=32
        )
        self.lang_menu.pack(fill="x")

        ctk.CTkLabel(
            lang_box,
            text="Erkennt Sprache automatisch am Textinhalt.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).pack(anchor="w", pady=(4, 0))

        # Model Selector
        model_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        model_box.grid(row=0, column=2, padx=15, pady=12, sticky="nsew")

        ctk.CTkLabel(
            model_box,
            text="🤖 Gemini Modell",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", pady=(0, 4))

        model_options = [m["name"] for m in AVAILABLE_MODELS]
        self.model_var = ctk.StringVar(value=model_options[0])
        self.model_menu = ctk.CTkOptionMenu(
            model_box,
            values=model_options,
            variable=self.model_var,
            height=32
        )
        self.model_menu.pack(fill="x")

        ctk.CTkLabel(
            model_box,
            text="Nativer Multimodal-Audio-Support.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).pack(anchor="w", pady=(4, 0))

        # 3. AUDIO FORMAT & EXPORT SETTINGS CARD
        format_card = ctk.CTkFrame(main_scroll, corner_radius=10)
        format_card.grid(row=2, column=0, sticky="ew", pady=(0, 15))
        format_card.grid_columnconfigure(0, weight=1)

        format_header = ctk.CTkFrame(format_card, fg_color="transparent")
        format_header.pack(fill="x", padx=15, pady=(12, 5))

        ctk.CTkLabel(
            format_header,
            text="🎛️ Audioformat & FFmpeg Konvertierung",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(side="left")

        # Preset Selector
        preset_frame = ctk.CTkFrame(format_card, fg_color="transparent")
        preset_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            preset_frame,
            text="Format-Preset:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left", padx=(0, 10))

        preset_names = [p["name"] for p in AUDIO_PRESETS.values()]
        self.preset_var = ctk.StringVar(value=preset_names[0])
        self.preset_menu = ctk.CTkOptionMenu(
            preset_frame,
            values=preset_names,
            variable=self.preset_var,
            command=self._on_preset_changed,
            width=480,
            height=32
        )
        self.preset_menu.pack(side="left", fill="x", expand=True)

        # Custom controls container (visible or adjusted based on preset)
        self.custom_settings_frame = ctk.CTkFrame(format_card, fg_color=("gray90", "gray20"), corner_radius=8)
        self.custom_settings_frame.pack(fill="x", padx=15, pady=8)
        self.custom_settings_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        # Codec
        ctk.CTkLabel(self.custom_settings_frame, text="Codec:", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=8, pady=(6, 2), sticky="w")
        self.codec_var = ctk.StringVar(value="aac")
        self.codec_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["aac", "libmp3lame", "pcm_s16le"],
            variable=self.codec_var,
            command=lambda _: self._update_ffmpeg_command_preview(),
            height=28
        )
        self.codec_menu.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")

        # Channels
        ctk.CTkLabel(self.custom_settings_frame, text="Kanäle:", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=1, padx=8, pady=(6, 2), sticky="w")
        self.channels_var = ctk.StringVar(value="Mono (1)")
        self.channels_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["Mono (1)", "Stereo (2)"],
            variable=self.channels_var,
            command=lambda _: self._update_ffmpeg_command_preview(),
            height=28
        )
        self.channels_menu.grid(row=1, column=1, padx=8, pady=(0, 8), sticky="ew")

        # Sample Rate
        ctk.CTkLabel(self.custom_settings_frame, text="Abtastrate:", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=2, padx=8, pady=(6, 2), sticky="w")
        self.rate_var = ctk.StringVar(value="44.100 Hz")
        self.rate_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["44.100 Hz", "48.000 Hz", "24.000 Hz"],
            variable=self.rate_var,
            command=lambda _: self._update_ffmpeg_command_preview(),
            height=28
        )
        self.rate_menu.grid(row=1, column=2, padx=8, pady=(0, 8), sticky="ew")

        # Bitrate
        ctk.CTkLabel(self.custom_settings_frame, text="Datenrate:", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=3, padx=8, pady=(6, 2), sticky="w")
        self.bitrate_var = ctk.StringVar(value="64 kbit/s")
        self.bitrate_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["64 kbit/s", "96 kbit/s", "128 kbit/s", "192 kbit/s", "320 kbit/s"],
            variable=self.bitrate_var,
            command=lambda _: self._update_ffmpeg_command_preview(),
            height=28
        )
        self.bitrate_menu.grid(row=1, column=3, padx=8, pady=(0, 8), sticky="ew")

        # FastStart Checkbox
        self.faststart_var = ctk.BooleanVar(value=True)
        self.faststart_check = ctk.CTkCheckBox(
            self.custom_settings_frame,
            text="+faststart (Web-Streaming)",
            variable=self.faststart_var,
            command=self._update_ffmpeg_command_preview,
            font=ctk.CTkFont(size=11)
        )
        self.faststart_check.grid(row=1, column=4, padx=8, pady=(0, 8), sticky="w")

        # Command Preview Box
        preview_frame = ctk.CTkFrame(format_card, fg_color="transparent")
        preview_frame.pack(fill="x", padx=15, pady=(2, 12))

        ctk.CTkLabel(
            preview_frame,
            text="FFmpeg-Befehl:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray"
        ).pack(anchor="w")

        self.cmd_preview_entry = ctk.CTkEntry(
            preview_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            height=28,
            state="normal"
        )
        self.cmd_preview_entry.pack(fill="x", pady=(2, 0))

        # 4. ACTION & GENERATION
        action_card = ctk.CTkFrame(main_scroll, corner_radius=10)
        action_card.grid(row=3, column=0, sticky="ew", pady=(0, 15))
        action_card.grid_columnconfigure(0, weight=1)

        self.generate_btn = ctk.CTkButton(
            action_card,
            text="⚡ Sprache generieren & konvertieren",
            command=self._start_generation_thread,
            height=45,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#28a745",
            hover_color="#218838"
        )
        self.generate_btn.pack(fill="x", padx=15, pady=(15, 8))

        self.status_lbl = ctk.CTkLabel(
            action_card,
            text="Bereit zur Sprachgenerierung.",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.status_lbl.pack(padx=15, pady=(0, 10))

        # 5. AUDIO PLAYER & EXPORT CARD
        player_card = ctk.CTkFrame(main_scroll, corner_radius=10)
        player_card.grid(row=4, column=0, sticky="ew", pady=(0, 20))
        player_card.grid_columnconfigure(1, weight=1)

        player_header = ctk.CTkLabel(
            player_card,
            text="🔊 Integrierter Audio-Player & Export",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        player_header.grid(row=0, column=0, columnspan=3, sticky="w", padx=15, pady=(12, 10))

        # Controls row
        controls_frame = ctk.CTkFrame(player_card, fg_color="transparent")
        controls_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=15, pady=0)
        controls_frame.grid_columnconfigure(2, weight=1)

        self.play_btn = ctk.CTkButton(
            controls_frame,
            text="▶️ Abspielen",
            command=self._toggle_playback,
            width=110,
            height=34,
            state="disabled",
            fg_color="#1f6aa5"
        )
        self.play_btn.grid(row=0, column=0, padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            controls_frame,
            text="⏹️ Stopp",
            command=self._stop_playback,
            width=80,
            height=34,
            state="disabled",
            fg_color="gray"
        )
        self.stop_btn.grid(row=0, column=1, padx=(0, 15))

        # Timeline slider
        self.timeline_slider = ctk.CTkSlider(
            controls_frame,
            from_=0.0,
            to=1.0,
            number_of_steps=100,
            state="disabled"
        )
        self.timeline_slider.set(0.0)
        self.timeline_slider.grid(row=0, column=2, sticky="ew", padx=10)

        # Time label
        self.time_lbl = ctk.CTkLabel(
            controls_frame,
            text="00:00 / 00:00",
            font=ctk.CTkFont(size=12)
        )
        self.time_lbl.grid(row=0, column=3, padx=(10, 15))

        # Volume control
        ctk.CTkLabel(controls_frame, text="🔈", font=ctk.CTkFont(size=14)).grid(row=0, column=4, padx=(0, 4))
        self.volume_slider = ctk.CTkSlider(
            controls_frame,
            from_=0.0,
            to=1.0,
            width=90,
            command=self._on_volume_changed
        )
        self.volume_slider.set(0.8)
        self.volume_slider.grid(row=0, column=5, padx=(0, 0))

        # Export Button
        self.export_btn = ctk.CTkButton(
            player_card,
            text="💾 Audiodatei speichern unter...",
            command=self._export_audio,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#17a2b8",
            hover_color="#138496",
            state="disabled"
        )
        self.export_btn.grid(row=2, column=0, columnspan=3, sticky="ew", padx=15, pady=(12, 15))

    # ------------------ Helper Methods ------------------

    def _get_key_status_text(self) -> str:
        key = get_api_key()
        if key and len(key) > 6:
            return f"🔑 Key: {key[:4]}...{key[-3:]}"
        return "⚠️ API-Key fehlt"

    def _open_api_key_dialog(self):
        APIKeyDialog(self, on_save_callback=self._on_key_saved)

    def _on_key_saved(self, new_key: str):
        self.tts_service.set_api_key(new_key)
        self.key_status_btn.configure(text=self._get_key_status_text())
        messagebox.showinfo("Erfolg", "API-Key wurde erfolgreich gespeichert!")

    def _toggle_theme(self):
        mode = ctk.get_appearance_mode()
        ctk.set_appearance_mode("Light" if mode == "Dark" else "Dark")

    def _update_counters(self, event=None):
        content = self.text_input.get("0.0", "end").strip()
        chars = len(content)
        words = len(content.split()) if chars > 0 else 0
        self.char_counter_lbl.configure(text=f"{chars} Zeichen | {words} Wörter")

    def _insert_tag(self, tag: str):
        """Insert audio tag at current cursor position."""
        self.text_input.insert("insert", f" {tag} ")
        self.text_input.focus_set()
        self._update_counters()

    def _on_voice_changed(self, choice: str):
        voice_id = choice.split(" - ")[0]
        for v in AVAILABLE_VOICES:
            if v["id"] == voice_id:
                self.voice_desc_lbl.configure(text=v["desc"])
                break

    def _on_preset_changed(self, choice: str):
        preset = None
        for p in AUDIO_PRESETS.values():
            if p["name"] == choice:
                preset = p
                break
        
        if not preset or preset["name"] == AUDIO_PRESETS["custom"]["name"]:
            return

        self.codec_var.set(preset["codec"])
        self.channels_var.set("Mono (1)" if preset["channels"] == 1 else "Stereo (2)")
        self.rate_var.set(f"{preset['sample_rate']:,}".replace(",", ".") + " Hz")
        self.bitrate_var.set(preset["bitrate"] + "bit/s" if preset["bitrate"] else "128 kbit/s")
        self.faststart_var.set(preset["faststart"])
        self._update_ffmpeg_command_preview()

    def _get_current_encoding_settings(self) -> Dict[str, Any]:
        codec = self.codec_var.get()
        channels = 1 if "Mono" in self.channels_var.get() else 2
        rate_str = self.rate_var.get().replace(".", "").replace(" Hz", "")
        sample_rate = int(rate_str)
        bitrate = self.bitrate_var.get().replace(" kbit/s", "k").replace(" ", "")
        faststart = self.faststart_var.get()
        
        # Determine target extension
        if codec == "aac":
            ext = ".mp4" if "mp4" in self.preset_var.get().lower() else ".m4a"
        elif codec == "libmp3lame":
            ext = ".mp3"
        elif codec == "pcm_s16le":
            ext = ".wav"
        else:
            ext = ".mp4"

        return {
            "codec": codec,
            "channels": channels,
            "sample_rate": sample_rate,
            "bitrate": bitrate if codec != "pcm_s16le" else None,
            "faststart": faststart,
            "extension": ext
        }

    def _update_ffmpeg_command_preview(self):
        settings = self._get_current_encoding_settings()
        cmd_str = get_command_preview(
            input_file="eingabe.wav",
            output_file=f"ausgabe{settings['extension']}",
            codec=settings["codec"],
            channels=settings["channels"],
            sample_rate=settings["sample_rate"],
            bitrate=settings["bitrate"],
            faststart=settings["faststart"]
        )
        self.cmd_preview_entry.configure(state="normal")
        self.cmd_preview_entry.delete(0, "end")
        self.cmd_preview_entry.insert(0, cmd_str)

    # ------------------ Generation & Processing ------------------

    def _start_generation_thread(self):
        if self.is_generating:
            return

        text = self.text_input.get("0.0", "end").strip()
        if not text:
            messagebox.showwarning("Hinweis", "Bitte gib einen Text für die Sprachausgabe ein.")
            return

        if not get_api_key():
            self._open_api_key_dialog()
            return

        self.is_generating = True
        self.generate_btn.configure(state="disabled", text="⏳ Generiere Audio mit Gemini...")
        self.status_lbl.configure(text="Sende Anfrage an Gemini TTS API...", text_color="#17a2b8")
        
        thread = threading.Thread(target=self._run_generation, args=(text,), daemon=True)
        thread.start()

    def _run_generation(self, text: str):
        try:
            # 1. Voice & Model selection
            voice_choice = self.voice_var.get().split(" - ")[0]
            
            selected_model_name = self.model_var.get()
            model_id = "gemini-2.0-flash"
            for m in AVAILABLE_MODELS:
                if m["name"] == selected_model_name:
                    model_id = m["id"]
                    break

            selected_lang_name = self.lang_var.get()
            lang_id = "auto"
            for l in SUPPORTED_LANGUAGES:
                if l["name"] == selected_lang_name:
                    lang_id = l["id"]
                    break

            # 2. Gemini TTS Generation
            self.status_lbl.configure(text=f"Generiere Sprache ({voice_choice}, Modell: {model_id})...")
            start_time = time.time()
            
            raw_wav_path = self.tts_service.generate_speech(
                text=text,
                voice_name=voice_choice,
                model=model_id,
                language=lang_id
            )
            self.current_generated_wav = raw_wav_path

            # 3. Audio Conversion (FFmpeg)
            self.status_lbl.configure(text="Konvertiere Audio mit FFmpeg in Zielformat...")
            settings = self._get_current_encoding_settings()
            
            output_converted_path = OUTPUT_DIR / f"tts_output_{int(time.time())}{settings['extension']}"
            
            converted_path = convert_audio(
                input_file=raw_wav_path,
                output_file=output_converted_path,
                codec=settings["codec"],
                channels=settings["channels"],
                sample_rate=settings["sample_rate"],
                bitrate=settings["bitrate"],
                faststart=settings["faststart"]
            )
            self.current_converted_file = converted_path

            duration = time.time() - start_time
            file_size_kb = converted_path.stat().st_size / 1024.0

            # 4. Load into player
            self.player.load(converted_path)

            # Update UI on main thread
            self.after(0, self._on_generation_success, duration, file_size_kb, converted_path.name)

        except Exception as e:
            self.after(0, self._on_generation_error, str(e))

    def _on_generation_success(self, duration: float, file_size_kb: float, filename: str):
        self.is_generating = False
        self.generate_btn.configure(state="normal", text="⚡ Sprache generieren & konvertieren")
        self.status_lbl.configure(
            text=f"✅ Erfolgreich generiert ({duration:.1f}s)! Datei: {filename} ({file_size_kb:.1f} KB)",
            text_color="#28a745"
        )
        self.play_btn.configure(state="normal", text="▶️ Abspielen")
        self.stop_btn.configure(state="normal")
        self.export_btn.configure(state="normal")
        self.timeline_slider.configure(state="normal")
        self._toggle_playback()  # Auto play preview

    def _on_generation_error(self, err_msg: str):
        self.is_generating = False
        self.generate_btn.configure(state="normal", text="⚡ Sprache generieren & konvertieren")
        self.status_lbl.configure(text=f"❌ Fehler: {err_msg}", text_color="#dc3545")
        messagebox.showerror("Fehler bei Sprachgenerierung", err_msg)

    # ------------------ Audio Player Controls ------------------

    def _toggle_playback(self):
        if not self.current_converted_file:
            return

        if self.player.is_playing() and not self.player.is_paused():
            self.player.pause()
            self.play_btn.configure(text="▶️ Fortsetzen")
        elif self.player.is_paused():
            self.player.resume()
            self.play_btn.configure(text="⏸️ Pause")
        else:
            self.player.play()
            self.play_btn.configure(text="⏸️ Pause")

    def _stop_playback(self):
        self.player.stop()
        self.play_btn.configure(text="▶️ Abspielen")
        self.timeline_slider.set(0.0)
        self.time_lbl.configure(text=f"00:00 / {self._format_time(self.player.get_duration())}")

    def _on_volume_changed(self, value):
        self.player.set_volume(float(value))

    def _setup_player_timer(self):
        """Update playback slider and time display periodically."""
        if self.player.is_playing() or self.player.is_paused():
            curr = self.player.get_position()
            total = self.player.get_duration()
            if total > 0:
                self.timeline_slider.set(curr / total)
            self.time_lbl.configure(text=f"{self._format_time(curr)} / {self._format_time(total)}")
            
            if not self.player.is_playing() and not self.player.is_paused():
                self.play_btn.configure(text="▶️ Abspielen")
                self.timeline_slider.set(0.0)
        
        self.after(100, self._setup_player_timer)

    def _format_time(self, seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    # ------------------ Export File Dialog ------------------

    def _export_audio(self):
        if not self.current_converted_file or not self.current_converted_file.exists():
            messagebox.showwarning("Hinweis", "Keine generierte Audiodatei zum Speichern vorhanden.")
            return

        ext = self.current_converted_file.suffix.lower()
        file_types = {
            ".mp4": ("MP4 Audio (*.mp4)", "*.mp4"),
            ".m4a": ("M4A Audio (*.m4a)", "*.m4a"),
            ".mp3": ("MP3 Audio (*.mp3)", "*.mp3"),
            ".wav": ("WAV Audio (*.wav)", "*.wav"),
        }
        
        filter_spec = [file_types.get(ext, ("Audiodatei", f"*{ext}")), ("Alle Dateien", "*.*")]

        target_file = filedialog.asksaveasfilename(
            title="Audiodatei speichern unter...",
            initialdir=str(Path.home() / "Music"),
            initialfile=f"gemini_tts_{int(time.time())}{ext}",
            filetypes=filter_spec,
            defaultextension=ext
        )

        if target_file:
            try:
                import shutil
                shutil.copyfile(str(self.current_converted_file), target_file)
                messagebox.showinfo("Erfolg", f"Audiodatei wurde erfolgreich gespeichert unter:\n{target_file}")
            except Exception as e:
                messagebox.showerror("Fehler beim Speichern", f"Datei konnte nicht gespeichert werden: {e}")
