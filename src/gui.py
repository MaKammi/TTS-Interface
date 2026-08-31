"""
Modern, high-contrast GUI for Gemini TTS Interface with Progress Bar & Scrubbing Player
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
from .audio_converter import convert_audio
from .player import AudioPlayer


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Typography & Color Constants for High Readability
FONT_FAMILY = "Segoe UI"
COLOR_PRIMARY_TEXT = ("#111827", "#F9FAFB")       # Crisp dark / white
COLOR_MUTED_TEXT = ("#4B5563", "#9CA3AF")         # Readable secondary text
COLOR_ACCENT = "#2563EB"                           # Blue accent
COLOR_ACCENT_HOVER = "#1D4ED8"
COLOR_TAG_BG = ("#E5E7EB", "#374151")             # Tag button background
COLOR_TAG_HOVER = ("#D1D5DB", "#4B5563")          # Tag button hover
COLOR_TAG_TEXT = ("#1F2937", "#F3F4F6")           # Tag button text
COLOR_CARD_BG = ("#FFFFFF", "#1E2430")            # Clean card background
COLOR_CARD_BORDER = ("#E5E7EB", "#2D3748")


class APIKeyDialog(ctk.CTkToplevel):
    """Dialog for viewing and editing the Gemini API Key."""

    def __init__(self, parent, on_save_callback):
        super().__init__(parent)
        self.title("Gemini API-Key Einstellungen")
        self.geometry("540x260")
        self.resizable(False, False)
        self.on_save_callback = on_save_callback

        frame = ctk.CTkFrame(self, corner_radius=12, fg_color=COLOR_CARD_BG)
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        lbl = ctk.CTkLabel(
            frame,
            text="Google Gemini API-Key",
            font=ctk.CTkFont(family=FONT_FAMILY, size=17, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        lbl.pack(pady=(16, 6))

        desc = ctk.CTkLabel(
            frame,
            text="Trage hier deinen API-Key aus Google AI Studio ein.\nDer Key wird sicher in deiner lokalen .env Datei gespeichert.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT,
            justify="center"
        )
        desc.pack(pady=(0, 12))

        self.key_entry = ctk.CTkEntry(
            frame,
            placeholder_text="AQ... oder AIzaSy...",
            show="*",
            width=440,
            height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13)
        )
        self.key_entry.pack(pady=6)
        self.key_entry.insert(0, get_api_key())

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=(16, 10))

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Speichern",
            command=self._save,
            width=130,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER
        )
        save_btn.pack(side="left", padx=8)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            command=self.destroy,
            width=100,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=("gray75", "gray35"),
            hover_color=("gray65", "gray45"),
            text_color=COLOR_PRIMARY_TEXT
        )
        cancel_btn.pack(side="left", padx=8)

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

        self.title("Gemini TTS Studio - Windows Interface")
        self.geometry("1060x860")
        self.minsize(960, 760)

        self.tts_service = GeminiTTSService()
        self.player = AudioPlayer()
        
        self.current_generated_wav: Optional[Path] = None
        self.current_converted_file: Optional[Path] = None
        self.is_generating = False
        self.is_user_scrubbing = False

        self._build_ui()
        self._setup_player_timer()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ------------------ Header Bar ------------------
        header_frame = ctk.CTkFrame(self, height=64, corner_radius=0, fg_color=("gray90", "#161B22"))
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        title_label = ctk.CTkLabel(
            header_frame,
            text="🎙️ Gemini TTS Studio",
            font=ctk.CTkFont(family=FONT_FAMILY, size=21, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        title_label.grid(row=0, column=0, padx=22, pady=14, sticky="w")

        # API-Key Badge & Settings Button
        self.key_status_btn = ctk.CTkButton(
            header_frame,
            text=self._get_key_status_text(),
            command=self._open_api_key_dialog,
            width=180,
            height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=("#E5E7EB", "#21262D"),
            hover_color=("#D1D5DB", "#30363D"),
            text_color=COLOR_PRIMARY_TEXT,
            border_width=1,
            border_color=("gray70", "#30363D")
        )
        self.key_status_btn.grid(row=0, column=2, padx=(0, 12), pady=14, sticky="e")

        theme_switch = ctk.CTkSwitch(
            header_frame,
            text="Dark Mode",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_PRIMARY_TEXT
        )
        theme_switch.select()
        theme_switch.grid(row=0, column=3, padx=18, pady=14, sticky="e")

        # ------------------ Main Content Frame ------------------
        main_content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_content.grid(row=1, column=0, sticky="nsew", padx=20, pady=0)
        main_content.grid_columnconfigure(0, weight=1)

        # 1. TEXT INPUT & AUDIO-TAGS CARD
        text_card = ctk.CTkFrame(
            main_content,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER
        )
        text_card.pack(fill="x", pady=(0, 14))

        text_header_frame = ctk.CTkFrame(text_card, fg_color="transparent")
        text_header_frame.pack(fill="x", padx=18, pady=(14, 6))

        text_title = ctk.CTkLabel(
            text_header_frame,
            text="📝 Texteingabe & Regieanweisungen",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        text_title.pack(side="left")

        self.char_counter_lbl = ctk.CTkLabel(
            text_header_frame,
            text="0 Zeichen | 0 Wörter",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        )
        self.char_counter_lbl.pack(side="right")

        # Text input area
        self.text_input = ctk.CTkTextbox(
            text_card,
            height=130,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            wrap="word",
            border_width=1,
            border_color=("gray75", "#374151"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.text_input.pack(fill="x", padx=18, pady=(0, 8))
        self.text_input.insert("0.0", "Hallo! Dies ist ein Test mit Gemini TTS. [lachen] Es ist wirklich erstaunlich, wie lebendig die Stimme klingt! [flüstern] Kannst du ein Geheimnis für dich behalten?")
        self.text_input.bind("<KeyRelease>", self._update_counters)
        self._update_counters()

        # Audio-Tags Toolbar
        tag_section_frame = ctk.CTkFrame(text_card, fg_color="transparent")
        tag_section_frame.pack(fill="x", padx=18, pady=(0, 14))

        tag_title_lbl = ctk.CTkLabel(
            tag_section_frame,
            text="🎭 Audio-Tags einfügen (an Cursor-Position):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=("#1D4ED8", "#60A5FA")
        )
        tag_title_lbl.pack(anchor="w", pady=(0, 6))

        tag_buttons_frame = ctk.CTkFrame(tag_section_frame, fg_color="transparent")
        tag_buttons_frame.pack(fill="x", anchor="w")

        tags_display_list = [
            ("[lachen]", "+ [lachen]"),
            ("[flüstern]", "+ [flüstern]"),
            ("[traurig]", "+ [traurig]"),
            ("[begeistert]", "+ [begeistert]"),
            ("[Pause]", "+ [Pause]"),
            ("[seufzen]", "+ [seufzen]"),
            ("[wütend]", "+ [wütend]"),
            ("[nachdenklich]", "+ [nachdenklich]"),
            ("[langsam]", "+ [langsam]"),
            ("[schnell]", "+ [schnell]"),
        ]

        for tag_code, label_text in tags_display_list:
            btn = ctk.CTkButton(
                tag_buttons_frame,
                text=label_text,
                command=lambda t=tag_code: self._insert_tag(t),
                height=28,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                fg_color=COLOR_TAG_BG,
                hover_color=COLOR_TAG_HOVER,
                text_color=COLOR_TAG_TEXT,
                corner_radius=6,
                border_width=1,
                border_color=("gray75", "#4B5563")
            )
            btn.pack(side="left", padx=3, pady=2)

        # 2. VOICE, LANGUAGE & MODEL CONFIG CARD
        voice_card = ctk.CTkFrame(
            main_content,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER
        )
        voice_card.pack(fill="x", pady=(0, 14))
        voice_card.grid_columnconfigure((0, 1, 2), weight=1)

        # Voice Selector
        voice_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        voice_box.grid(row=0, column=0, padx=16, pady=14, sticky="nsew")
        
        ctk.CTkLabel(
            voice_box,
            text="🗣️ Stimme",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        voice_options = [f"{v['id']} ({v['desc'].split('(')[-1].replace(')', '')})" for v in AVAILABLE_VOICES]
        self.voice_var = ctk.StringVar(value=voice_options[0])
        self.voice_menu = ctk.CTkOptionMenu(
            voice_box,
            values=voice_options,
            variable=self.voice_var,
            command=self._on_voice_changed,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.voice_menu.pack(fill="x")

        self.voice_desc_lbl = ctk.CTkLabel(
            voice_box,
            text=AVAILABLE_VOICES[0]["desc"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT,
            wraplength=270,
            justify="left"
        )
        self.voice_desc_lbl.pack(anchor="w", pady=(5, 0))

        # Language Selector
        lang_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        lang_box.grid(row=0, column=1, padx=16, pady=14, sticky="nsew")

        ctk.CTkLabel(
            lang_box,
            text="🌐 Sprache",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        lang_options = [l["name"] for l in SUPPORTED_LANGUAGES]
        self.lang_var = ctk.StringVar(value=lang_options[0])
        self.lang_menu = ctk.CTkOptionMenu(
            lang_box,
            values=lang_options,
            variable=self.lang_var,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.lang_menu.pack(fill="x")

        ctk.CTkLabel(
            lang_box,
            text="Erkennt Sprache automatisch am Textinhalt.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(5, 0))

        # Model Selector (Defaults to Gemini 3.1 Flash TTS)
        model_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        model_box.grid(row=0, column=2, padx=16, pady=14, sticky="nsew")

        ctk.CTkLabel(
            model_box,
            text="🤖 Gemini TTS Modell",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        model_options = [m["name"] for m in AVAILABLE_MODELS]
        self.model_var = ctk.StringVar(value=model_options[0])
        self.model_menu = ctk.CTkOptionMenu(
            model_box,
            values=model_options,
            variable=self.model_var,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.model_menu.pack(fill="x")

        ctk.CTkLabel(
            model_box,
            text="Standard: Gemini 3.1 Flash TTS Engine.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(5, 0))

        # 3. AUDIO FORMAT & EXPORT SETTINGS CARD
        format_card = ctk.CTkFrame(
            main_content,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER
        )
        format_card.pack(fill="x", pady=(0, 14))

        format_header = ctk.CTkFrame(format_card, fg_color="transparent")
        format_header.pack(fill="x", padx=18, pady=(14, 6))

        ctk.CTkLabel(
            format_header,
            text="🎛️ Audioformat & Enkodierung",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left")

        # Preset Selector
        preset_frame = ctk.CTkFrame(format_card, fg_color="transparent")
        preset_frame.pack(fill="x", padx=18, pady=(4, 10))

        ctk.CTkLabel(
            preset_frame,
            text="Format-Preset:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left", padx=(0, 10))

        preset_names = [p["name"] for p in AUDIO_PRESETS.values()]
        self.preset_var = ctk.StringVar(value=preset_names[0])
        self.preset_menu = ctk.CTkOptionMenu(
            preset_frame,
            values=preset_names,
            variable=self.preset_var,
            command=self._on_preset_changed,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.preset_menu.pack(side="left", fill="x", expand=True)

        # Settings panel (clean parameter view)
        self.custom_settings_frame = ctk.CTkFrame(
            format_card,
            fg_color=("gray95", "#161B22"),
            corner_radius=8,
            border_width=1,
            border_color=COLOR_CARD_BORDER
        )
        self.custom_settings_frame.pack(fill="x", padx=18, pady=(0, 14))
        self.custom_settings_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        # Codec
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Codec:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=0, padx=8, pady=(6, 2), sticky="w")
        
        self.codec_var = ctk.StringVar(value="aac")
        self.codec_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["aac", "libmp3lame", "pcm_s16le"],
            variable=self.codec_var,
            height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.codec_menu.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")

        # Channels
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Kanäle:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=1, padx=8, pady=(6, 2), sticky="w")
        
        self.channels_var = ctk.StringVar(value="Mono (1)")
        self.channels_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["Mono (1)", "Stereo (2)"],
            variable=self.channels_var,
            height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.channels_menu.grid(row=1, column=1, padx=8, pady=(0, 8), sticky="ew")

        # Sample Rate
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Abtastrate:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=2, padx=8, pady=(6, 2), sticky="w")
        
        self.rate_var = ctk.StringVar(value="44.100 Hz")
        self.rate_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["44.100 Hz", "48.000 Hz", "24.000 Hz"],
            variable=self.rate_var,
            height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.rate_menu.grid(row=1, column=2, padx=8, pady=(0, 8), sticky="ew")

        # Bitrate
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Datenrate:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=3, padx=8, pady=(6, 2), sticky="w")
        
        self.bitrate_var = ctk.StringVar(value="64 kbit/s")
        self.bitrate_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["64 kbit/s", "96 kbit/s", "128 kbit/s", "192 kbit/s", "320 kbit/s"],
            variable=self.bitrate_var,
            height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.bitrate_menu.grid(row=1, column=3, padx=8, pady=(0, 8), sticky="ew")

        # FastStart Checkbox
        self.faststart_var = ctk.BooleanVar(value=True)
        self.faststart_check = ctk.CTkCheckBox(
            self.custom_settings_frame,
            text="+faststart (Web-Streaming)",
            variable=self.faststart_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.faststart_check.grid(row=1, column=4, padx=8, pady=(0, 8), sticky="w")

        # 4. ACTION & GENERATION (With Progress Bar)
        action_card = ctk.CTkFrame(
            main_content,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER
        )
        action_card.pack(fill="x", pady=(0, 14))

        self.generate_btn = ctk.CTkButton(
            action_card,
            text="⚡ Sprache generieren & konvertieren",
            command=self._start_generation_thread,
            height=46,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#FFFFFF"
        )
        self.generate_btn.pack(fill="x", padx=18, pady=(16, 8))

        # Progress Bar (Animates during generation)
        self.progress_bar = ctk.CTkProgressBar(
            action_card,
            height=10,
            corner_radius=5,
            progress_color=COLOR_ACCENT
        )
        self.progress_bar.pack(fill="x", padx=18, pady=(0, 8))
        self.progress_bar.set(0.0)
        self.progress_bar.pack_forget()  # Hidden by default until generation starts

        self.status_lbl = ctk.CTkLabel(
            action_card,
            text="Bereit zur Sprachgenerierung.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        )
        self.status_lbl.pack(padx=18, pady=(0, 14))

        # 5. AUDIO PLAYER & EXPORT CARD
        player_card = ctk.CTkFrame(
            main_content,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER
        )
        player_card.pack(fill="x", pady=(0, 18))
        player_card.grid_columnconfigure(1, weight=1)

        player_header = ctk.CTkLabel(
            player_card,
            text="🔊 Integrierter Audio-Player & Export",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        player_header.grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(14, 10))

        # Controls row
        controls_frame = ctk.CTkFrame(player_card, fg_color="transparent")
        controls_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=18, pady=0)
        controls_frame.grid_columnconfigure(2, weight=1)

        self.play_btn = ctk.CTkButton(
            controls_frame,
            text="▶ Abspielen",
            command=self._toggle_playback,
            width=115,
            height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            state="disabled",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER
        )
        self.play_btn.grid(row=0, column=0, padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            controls_frame,
            text="■ Stopp",
            command=self._stop_playback,
            width=85,
            height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            state="disabled",
            fg_color=("gray70", "gray35"),
            hover_color=("gray60", "gray45"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.stop_btn.grid(row=0, column=1, padx=(0, 14))

        # Interactive Playhead Timeline Slider
        self.timeline_slider = ctk.CTkSlider(
            controls_frame,
            from_=0.0,
            to=1.0,
            number_of_steps=200,
            state="disabled",
            command=self._on_seek_change
        )
        self.timeline_slider.set(0.0)
        self.timeline_slider.grid(row=0, column=2, sticky="ew", padx=10)

        # Bind mouse press/release to handle dragging cleanly without timer jitter
        self.timeline_slider.bind("<Button-1>", self._on_slider_press)
        self.timeline_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        # Time label
        self.time_lbl = ctk.CTkLabel(
            controls_frame,
            text="00:00 / 00:00",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.time_lbl.grid(row=0, column=3, padx=(10, 16))

        # Volume control
        ctk.CTkLabel(
            controls_frame,
            text="Lautstärke:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        ).grid(row=0, column=4, padx=(0, 6))
        
        self.volume_slider = ctk.CTkSlider(
            controls_frame,
            from_=0.0,
            to=1.0,
            width=100,
            command=self._on_volume_changed
        )
        self.volume_slider.set(0.8)
        self.volume_slider.grid(row=0, column=5, padx=(0, 0))

        # Export Button
        self.export_btn = ctk.CTkButton(
            player_card,
            text="💾 Audiodatei speichern unter...",
            command=self._export_audio,
            height=40,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            text_color="#FFFFFF",
            state="disabled"
        )
        self.export_btn.grid(row=2, column=0, columnspan=3, sticky="ew", padx=18, pady=(14, 16))

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
        self.text_input.insert("insert", f" {tag} ")
        self.text_input.focus_set()
        self._update_counters()

    def _on_voice_changed(self, choice: str):
        voice_id = choice.split(" ")[0]
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

    def _get_current_encoding_settings(self) -> Dict[str, Any]:
        codec = self.codec_var.get()
        channels = 1 if "Mono" in self.channels_var.get() else 2
        rate_str = self.rate_var.get().replace(".", "").replace(" Hz", "")
        sample_rate = int(rate_str)
        bitrate = self.bitrate_var.get().replace(" kbit/s", "k").replace(" ", "")
        faststart = self.faststart_var.get()
        
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
        self.progress_bar.pack(fill="x", padx=18, pady=(0, 8))
        self.progress_bar.set(0.05)
        self.status_lbl.configure(text="Initialisiere Sprachgenerierung...", text_color="#0284C7")
        
        thread = threading.Thread(target=self._run_generation, args=(text,), daemon=True)
        thread.start()

    def _update_generation_progress(self, progress_val: float, message: str):
        self.after(0, self._set_progress_ui, progress_val, message)

    def _set_progress_ui(self, progress_val: float, message: str):
        self.progress_bar.set(progress_val)
        self.status_lbl.configure(text=message, text_color="#0284C7")

    def _run_generation(self, text: str):
        try:
            voice_choice = self.voice_var.get().split(" ")[0]
            
            selected_model_name = self.model_var.get()
            model_id = "gemini-3.1-flash-tts-preview"
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

            start_time = time.time()
            
            # Generate speech with chunking & progress updates
            raw_wav_path = self.tts_service.generate_speech(
                text=text,
                voice_name=voice_choice,
                model=model_id,
                language=lang_id,
                progress_callback=self._update_generation_progress
            )
            self.current_generated_wav = raw_wav_path

            self._update_generation_progress(0.95, "Konvertiere Audio in Zielformat...")
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

            self.player.load(converted_path)

            self.after(0, self._on_generation_success, duration, file_size_kb, converted_path.name)

        except Exception as e:
            self.after(0, self._on_generation_error, str(e))

    def _on_generation_success(self, duration: float, file_size_kb: float, filename: str):
        self.is_generating = False
        self.progress_bar.set(1.0)
        self.after(800, lambda: self.progress_bar.pack_forget())
        self.generate_btn.configure(state="normal", text="⚡ Sprache generieren & konvertieren")
        self.status_lbl.configure(
            text=f"✅ Erfolgreich generiert ({duration:.1f}s)! Datei: {filename} ({file_size_kb:.1f} KB)",
            text_color="#10B981"
        )
        self.play_btn.configure(state="normal", text="▶ Abspielen")
        self.stop_btn.configure(state="normal")
        self.export_btn.configure(state="normal")
        self.timeline_slider.configure(state="normal")
        self._toggle_playback()

    def _on_generation_error(self, err_msg: str):
        self.is_generating = False
        self.progress_bar.pack_forget()
        self.generate_btn.configure(state="normal", text="⚡ Sprache generieren & konvertieren")
        self.status_lbl.configure(text=f"❌ Fehler: {err_msg}", text_color="#EF4444")
        messagebox.showerror("Fehler bei Sprachgenerierung", err_msg)

    # ------------------ Audio Player Controls & Scrubbing ------------------

    def _on_slider_press(self, event):
        self.is_user_scrubbing = True

    def _on_slider_release(self, event):
        val = self.timeline_slider.get()
        total = self.player.get_duration()
        if total > 0:
            target_sec = val * total
            self.player.seek(target_sec)
        self.is_user_scrubbing = False

    def _on_seek_change(self, value):
        total = self.player.get_duration()
        if total > 0:
            curr = float(value) * total
            self.time_lbl.configure(text=f"{self._format_time(curr)} / {self._format_time(total)}")
            if not self.is_user_scrubbing:
                self.player.seek(curr)

    def _toggle_playback(self):
        if not self.current_converted_file:
            return

        if self.player.is_playing() and not self.player.is_paused():
            self.player.pause()
            self.play_btn.configure(text="▶ Fortsetzen")
        elif self.player.is_paused():
            self.player.resume()
            self.play_btn.configure(text="⏸ Pause")
        else:
            self.player.play()
            self.play_btn.configure(text="⏸ Pause")

    def _stop_playback(self):
        self.player.stop()
        self.play_btn.configure(text="▶ Abspielen")
        self.timeline_slider.set(0.0)
        self.time_lbl.configure(text=f"00:00 / {self._format_time(self.player.get_duration())}")

    def _on_volume_changed(self, value):
        self.player.set_volume(float(value))

    def _setup_player_timer(self):
        """Update playback slider and time display periodically when not user scrubbing."""
        if not self.is_user_scrubbing:
            if self.player.is_playing() or self.player.is_paused():
                curr = self.player.get_position()
                total = self.player.get_duration()
                if total > 0:
                    self.timeline_slider.set(curr / total)
                self.time_lbl.configure(text=f"{self._format_time(curr)} / {self._format_time(total)}")
                
                if not self.player.is_playing() and not self.player.is_paused():
                    self.play_btn.configure(text="▶ Abspielen")
                    self.timeline_slider.set(0.0)
        
        self.after(80, self._setup_player_timer)

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
