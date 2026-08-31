"""
Modern, high-contrast GUI for Gemini TTS Studio
Includes Single-Text Mode with Document Importer and Full Batch / Document Queue Processing.
Rock-solid stable layout hierarchy where no elements jump or shift when switching tabs.
"""

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

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
from .document_parser import extract_text_from_file, split_into_chapters
from .batch_processor import BatchProcessor, BatchItem


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Typography & Color Constants for High Readability and Maximum Contrast
FONT_FAMILY = "Segoe UI"
COLOR_PRIMARY_TEXT = ("#0F172A", "#FFFFFF")       # Pure White in dark mode
COLOR_MUTED_TEXT = ("#334155", "#E2E8F0")         # Bright, clear secondary text
COLOR_ACCENT = "#2563EB"                           # High-contrast vibrant blue
COLOR_ACCENT_HOVER = "#1D4ED8"
COLOR_CARD_BG = ("#FFFFFF", "#1E293B")            # Deep Slate card background
COLOR_CARD_BORDER = ("#CBD5E1", "#334155")        # Clean contrast border


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
            text_color="#FFFFFF"
        )
        lbl.pack(pady=(16, 6))

        desc = ctk.CTkLabel(
            frame,
            text="Trage hier deinen API-Key aus Google AI Studio ein.\nDer Key wird sicher in deiner lokalen .env Datei gespeichert.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#CBD5E1",
            justify="center"
        )
        desc.pack(pady=(0, 12))

        self.key_entry = ctk.CTkEntry(
            frame,
            placeholder_text="AQ... oder AIzaSy...",
            show="*",
            width=440,
            height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color="#FFFFFF"
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
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#FFFFFF"
        )
        save_btn.pack(side="left", padx=8)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            command=self.destroy,
            width=100,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color="#475569",
            hover_color="#334155",
            text_color="#FFFFFF"
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


class AutoScrollableFrame(ctk.CTkScrollableFrame):
    """
    Intelligent ScrollableFrame that automatically hides its scrollbar
    when all elements fit inside the window, and reveals it smoothly
    when the window is made smaller or content overflows.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent_canvas.configure(yscrollcommand=self._auto_handle_scroll)

    def _auto_handle_scroll(self, first: str, last: str):
        self._scrollbar.set(first, last)
        try:
            f = float(first)
            l = float(last)
            if f <= 0.001 and l >= 0.999:
                if self._scrollbar.winfo_ismapped():
                    self._scrollbar.grid_remove()
            else:
                if not self._scrollbar.winfo_ismapped():
                    self._scrollbar.grid()
        except Exception:
            pass


class GeminiTTSApp(ctk.CTk):
    """Main application window for Gemini TTS Interface."""

    def __init__(self):
        super().__init__()

        self.title("Gemini TTS Studio - Windows Interface")
        self.geometry("1100x880")
        self.minsize(850, 550)

        self.tts_service = GeminiTTSService()
        self.player = AudioPlayer()
        self.batch_processor = BatchProcessor()
        
        self.current_generated_wav: Optional[Path] = None
        self.current_converted_file: Optional[Path] = None
        self.is_generating = False
        self.is_user_scrubbing = False
        self.is_format_collapsed = True  # Collapsed by default
        self.current_mode = "single"      # "single" or "batch"
        self.batch_output_dir = OUTPUT_DIR / "batch_exports"

        self._build_ui()
        self._setup_player_timer()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ------------------ Header Bar ------------------
        header_frame = ctk.CTkFrame(self, height=64, corner_radius=0, fg_color=("#E2E8F0", "#0F172A"))
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
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=("#CBD5E1", "#1E293B"),
            hover_color=("#94A3B8", "#334155"),
            text_color=COLOR_PRIMARY_TEXT,
            border_width=1.5,
            border_color=("#94A3B8", "#475569")
        )
        self.key_status_btn.grid(row=0, column=2, padx=(0, 12), pady=14, sticky="e")

        theme_switch = ctk.CTkSwitch(
            header_frame,
            text="Dark Mode",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        theme_switch.select()
        theme_switch.grid(row=0, column=3, padx=18, pady=14, sticky="e")

        # ------------------ Main Auto-Scrollable Content Frame ------------------
        main_content = AutoScrollableFrame(self, fg_color="transparent")
        main_content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        main_content.grid_columnconfigure(0, weight=1)

        # ------------------ 1. Mode Selector (Permanent Top) ------------------
        mode_frame = ctk.CTkFrame(main_content, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(0, 10))

        self.mode_segmented = ctk.CTkSegmentedButton(
            mode_frame,
            values=["✍️ Einzeltext-Modus", "📂 Dokumenten- & Batch-Import"],
            command=self._on_mode_switched,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
            unselected_color=("#CBD5E1", "#1E293B"),
            unselected_hover_color=("#94A3B8", "#334155"),
            text_color="#FFFFFF",
            height=38
        )
        self.mode_segmented.set("✍️ Einzeltext-Modus")
        self.mode_segmented.pack(fill="x")

        # ------------------ 2. Input Container (Permanent Slot) ------------------
        self.input_container = ctk.CTkFrame(main_content, fg_color="transparent")
        self.input_container.pack(fill="x", pady=(0, 0))

        # 2A: Single-Text Card
        self.single_text_card = ctk.CTkFrame(
            self.input_container,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )
        self.single_text_card.pack(fill="x", pady=(0, 10))

        text_header_frame = ctk.CTkFrame(self.single_text_card, fg_color="transparent")
        text_header_frame.pack(fill="x", padx=18, pady=(14, 6))

        text_title = ctk.CTkLabel(
            text_header_frame,
            text="📝 Texteingabe & Regieanweisungen",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        text_title.pack(side="left")

        # Quick Document Loader Button
        load_doc_btn = ctk.CTkButton(
            text_header_frame,
            text="📂 Dokument laden (.txt, .pdf, .docx, .md)",
            command=self._load_document_to_single_text,
            height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=("#334155", "#0F172A"),
            hover_color=("#1E293B", "#1E3A8A"),
            text_color="#FFFFFF",
            border_width=1.5,
            border_color=("#64748B", "#38BDF8")
        )
        load_doc_btn.pack(side="right", padx=(10, 0))

        self.char_counter_lbl = ctk.CTkLabel(
            text_header_frame,
            text="0 Zeichen | 0 Wörter",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        )
        self.char_counter_lbl.pack(side="right")

        # Text input area
        self.text_input = ctk.CTkTextbox(
            self.single_text_card,
            height=130,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            wrap="word",
            border_width=1.5,
            border_color=("#94A3B8", "#475569"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.text_input.pack(fill="x", padx=18, pady=(0, 10))
        self.text_input.insert("0.0", "Hallo! Dies ist ein Test mit Gemini TTS. [lachen] Es ist wirklich erstaunlich, wie lebendig die Stimme klingt! [flüstern] Kannst du ein Geheimnis für dich behalten?")
        self.text_input.bind("<KeyRelease>", self._update_counters)
        self._update_counters()

        # Audio-Tags Toolbar
        tag_section_frame = ctk.CTkFrame(self.single_text_card, fg_color="transparent")
        tag_section_frame.pack(fill="x", padx=18, pady=(0, 14))

        tag_title_lbl = ctk.CTkLabel(
            tag_section_frame,
            text="🎭 Audio-Tags einfügen (an Cursor-Position):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
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
                height=32,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                fg_color=("#334155", "#0F172A"),
                hover_color=("#1E293B", "#1E3A8A"),
                text_color="#FFFFFF",
                corner_radius=8,
                border_width=1.5,
                border_color=("#64748B", "#38BDF8")
            )
            btn.pack(side="left", padx=3, pady=2)

        # 2B: Batch Card (Instantiated, packed only in batch mode)
        self.batch_card = ctk.CTkFrame(
            self.input_container,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )

        batch_header = ctk.CTkFrame(self.batch_card, fg_color="transparent")
        batch_header.pack(fill="x", padx=18, pady=(14, 8))

        ctk.CTkLabel(
            batch_header,
            text="📂 Dokumenten- & Stapelverarbeitung (Batch)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left")

        # Toolbar
        toolbar_frame = ctk.CTkFrame(self.batch_card, fg_color="transparent")
        toolbar_frame.pack(fill="x", padx=18, pady=(0, 10))

        add_files_btn = ctk.CTkButton(
            toolbar_frame,
            text="➕ Dateien hinzufügen...",
            command=self._batch_add_files_dialog,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#FFFFFF"
        )
        add_files_btn.pack(side="left", padx=(0, 8))

        add_folder_btn = ctk.CTkButton(
            toolbar_frame,
            text="📁 Ordner importieren...",
            command=self._batch_add_folder_dialog,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            text_color="#FFFFFF"
        )
        add_folder_btn.pack(side="left", padx=(0, 8))

        clear_btn = ctk.CTkButton(
            toolbar_frame,
            text="🗑️ Liste leeren",
            command=self._batch_clear_queue,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="#475569",
            hover_color="#334155",
            text_color="#FFFFFF"
        )
        clear_btn.pack(side="left")

        # Options Row (Chapter Splitting & Output Directory)
        options_frame = ctk.CTkFrame(
            self.batch_card,
            fg_color=("gray95", "#0F172A"),
            corner_radius=8,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )
        options_frame.pack(fill="x", padx=18, pady=(0, 10))

        self.batch_split_var = ctk.BooleanVar(value=True)
        split_check = ctk.CTkCheckBox(
            options_frame,
            text="Lange Dokumente automatisch in Kapitel aufteilen (# Überschriften)",
            variable=self.batch_split_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        split_check.pack(anchor="w", padx=12, pady=(10, 6))

        outdir_row = ctk.CTkFrame(options_frame, fg_color="transparent")
        outdir_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(
            outdir_row,
            text="Ausgabe-Ordner:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left", padx=(0, 8))

        self.batch_outdir_lbl = ctk.CTkLabel(
            outdir_row,
            text=str(self.batch_output_dir),
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=("#1D4ED8", "#38BDF8")
        )
        self.batch_outdir_lbl.pack(side="left", fill="x", expand=True, padx=(0, 8))

        change_outdir_btn = ctk.CTkButton(
            outdir_row,
            text="Ändern...",
            command=self._batch_choose_outdir,
            width=80,
            height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=("#334155", "#1E293B"),
            hover_color=("#1E293B", "#334155"),
            text_color="#FFFFFF"
        )
        change_outdir_btn.pack(side="right", padx=(0, 6))

        open_outdir_btn = ctk.CTkButton(
            outdir_row,
            text="📂 Ordner öffnen",
            command=self._batch_open_outdir,
            width=110,
            height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=("#334155", "#1E293B"),
            hover_color=("#1E293B", "#334155"),
            text_color="#FFFFFF"
        )
        open_outdir_btn.pack(side="right", padx=(0, 6))

        # Batch Queue Table / List
        self.queue_frame = ctk.CTkScrollableFrame(
            self.batch_card,
            height=160,
            fg_color=("gray90", "#0F172A"),
            corner_radius=8,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )
        self.queue_frame.pack(fill="x", padx=18, pady=(0, 10))

        self.queue_empty_lbl = ctk.CTkLabel(
            self.queue_frame,
            text="Keine Dateien in der Warteschlange. Klicke auf '➕ Dateien hinzufügen...', um Dokumente (.txt, .pdf, .docx, .md, .srt) zu laden.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        )
        self.queue_empty_lbl.pack(pady=20)

        # ------------------ 3. Permanent Voice & Language Card ------------------
        voice_card = ctk.CTkFrame(
            main_content,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )
        voice_card.pack(fill="x", pady=(0, 10))
        voice_card.grid_columnconfigure((0, 1, 2), weight=1)

        # Voice Selector
        voice_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        voice_box.grid(row=0, column=0, padx=16, pady=14, sticky="nsew")
        
        ctk.CTkLabel(
            voice_box,
            text="🗣️ Stimme",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        voice_options = [f"{v['id']} ({v['desc'].split('(')[-1].replace(')', '')})" for v in AVAILABLE_VOICES]
        self.voice_var = ctk.StringVar(value=voice_options[0])
        self.voice_menu = ctk.CTkOptionMenu(
            voice_box,
            values=voice_options,
            variable=self.voice_var,
            command=self._on_voice_changed,
            height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=COLOR_ACCENT,
            button_color="#1D4ED8",
            button_hover_color="#1E3A8A",
            text_color="#FFFFFF"
        )
        self.voice_menu.pack(fill="x")

        self.voice_desc_lbl = ctk.CTkLabel(
            voice_box,
            text=AVAILABLE_VOICES[0]["desc"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
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
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        lang_options = [l["name"] for l in SUPPORTED_LANGUAGES]
        self.lang_var = ctk.StringVar(value=lang_options[0])
        self.lang_menu = ctk.CTkOptionMenu(
            lang_box,
            values=lang_options,
            variable=self.lang_var,
            height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=COLOR_ACCENT,
            button_color="#1D4ED8",
            button_hover_color="#1E3A8A",
            text_color="#FFFFFF"
        )
        self.lang_menu.pack(fill="x")

        ctk.CTkLabel(
            lang_box,
            text="Erkennt Sprache automatisch am Textinhalt.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(5, 0))

        # Model Selector (Defaults to Gemini 3.1 Flash TTS)
        model_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        model_box.grid(row=0, column=2, padx=16, pady=14, sticky="nsew")

        ctk.CTkLabel(
            model_box,
            text="🤖 Gemini TTS Modell",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        model_options = [m["name"] for m in AVAILABLE_MODELS]
        self.model_var = ctk.StringVar(value=model_options[0])
        self.model_menu = ctk.CTkOptionMenu(
            model_box,
            values=model_options,
            variable=self.model_var,
            height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=COLOR_ACCENT,
            button_color="#1D4ED8",
            button_hover_color="#1E3A8A",
            text_color="#FFFFFF"
        )
        self.model_menu.pack(fill="x")

        ctk.CTkLabel(
            model_box,
            text="Standard: Gemini 3.1 Flash TTS Engine.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(5, 0))

        # ------------------ 4. Permanent Collapsible Audio Format Card ------------------
        self.format_card = ctk.CTkFrame(
            main_content,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )
        self.format_card.pack(fill="x", pady=(0, 10))

        # Collapsible Header
        self.format_header_frame = ctk.CTkFrame(self.format_card, fg_color="transparent")
        self.format_header_frame.pack(fill="x", padx=18, pady=10)

        self.format_title_lbl = ctk.CTkLabel(
            self.format_header_frame,
            text="🎛️ Audioformat: Web-Optimiert (AAC-LC Mono 64k FastStart)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.format_title_lbl.pack(side="left")

        self.format_toggle_btn = ctk.CTkButton(
            self.format_header_frame,
            text="▾ Einstellungen anpassen",
            command=self._toggle_format_panel,
            width=190,
            height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=("#334155", "#0F172A"),
            hover_color=("#1E293B", "#1E3A8A"),
            text_color="#FFFFFF",
            border_width=1.5,
            border_color=("#64748B", "#38BDF8")
        )
        self.format_toggle_btn.pack(side="right")

        # Collapsible Body Container (hidden by default)
        self.format_body_frame = ctk.CTkFrame(self.format_card, fg_color="transparent")

        # Preset Selector Row
        preset_frame = ctk.CTkFrame(self.format_body_frame, fg_color="transparent")
        preset_frame.pack(fill="x", padx=18, pady=(0, 10))

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
            height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=COLOR_ACCENT,
            button_color="#1D4ED8",
            button_hover_color="#1E3A8A",
            text_color="#FFFFFF"
        )
        self.preset_menu.pack(side="left", fill="x", expand=True)

        # Settings panel
        self.custom_settings_frame = ctk.CTkFrame(
            self.format_body_frame,
            fg_color=("gray95", "#0F172A"),
            corner_radius=8,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )
        self.custom_settings_frame.pack(fill="x", padx=18, pady=(0, 14))
        self.custom_settings_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        # Codec
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Codec:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=0, padx=8, pady=(6, 2), sticky="w")
        
        self.codec_var = ctk.StringVar(value="aac")
        self.codec_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["aac", "libmp3lame", "pcm_s16le"],
            variable=self.codec_var,
            height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.codec_menu.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")

        # Channels
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Kanäle:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=1, padx=8, pady=(6, 2), sticky="w")
        
        self.channels_var = ctk.StringVar(value="Mono (1)")
        self.channels_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["Mono (1)", "Stereo (2)"],
            variable=self.channels_var,
            height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.channels_menu.grid(row=1, column=1, padx=8, pady=(0, 8), sticky="ew")

        # Sample Rate
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Abtastrate:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=2, padx=8, pady=(6, 2), sticky="w")
        
        self.rate_var = ctk.StringVar(value="44.100 Hz")
        self.rate_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["44.100 Hz", "48.000 Hz", "24.000 Hz"],
            variable=self.rate_var,
            height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#FFFFFF"
        )
        self.rate_menu.grid(row=1, column=2, padx=8, pady=(0, 8), sticky="ew")

        # Bitrate
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Datenrate:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=3, padx=8, pady=(6, 2), sticky="w")
        
        self.bitrate_var = ctk.StringVar(value="64 kbit/s")
        self.bitrate_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["64 kbit/s", "96 kbit/s", "128 kbit/s", "192 kbit/s", "320 kbit/s"],
            variable=self.bitrate_var,
            height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
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
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.faststart_check.grid(row=1, column=4, padx=8, pady=(0, 8), sticky="w")

        # ------------------ 5. Action Container (Permanent Slot) ------------------
        self.action_container = ctk.CTkFrame(main_content, fg_color="transparent")
        self.action_container.pack(fill="x", pady=(0, 0))

        # 5A: Single-Text Action Card
        self.single_action_card = ctk.CTkFrame(
            self.action_container,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )
        self.single_action_card.pack(fill="x", pady=(0, 10))

        self.generate_btn = ctk.CTkButton(
            self.single_action_card,
            text="⚡ Sprache generieren & konvertieren",
            command=self._start_generation_thread,
            height=48,
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            text_color="#FFFFFF",
            text_color_disabled="#FFFFFF"
        )
        self.generate_btn.pack(fill="x", padx=18, pady=(14, 8))

        self.progress_bar = ctk.CTkProgressBar(
            self.single_action_card,
            height=10,
            corner_radius=5,
            progress_color="#38BDF8",
            fg_color="#0F172A"
        )
        self.progress_bar.pack(fill="x", padx=18, pady=(0, 8))
        self.progress_bar.set(0.0)
        self.progress_bar.pack_forget()

        self.status_lbl = ctk.CTkLabel(
            self.single_action_card,
            text="Bereit zur Sprachgenerierung.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        )
        self.status_lbl.pack(padx=18, pady=(0, 12))

        # 5B: Batch Action Card (Instantiated, packed only in batch mode)
        self.batch_action_card = ctk.CTkFrame(
            self.action_container,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )

        batch_action_btn_row = ctk.CTkFrame(self.batch_action_card, fg_color="transparent")
        batch_action_btn_row.pack(fill="x", padx=18, pady=(14, 8))

        self.batch_start_btn = ctk.CTkButton(
            batch_action_btn_row,
            text="⚡ Alle Dateien in Warteschlange generieren",
            command=self._batch_start_processing,
            height=46,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            text_color="#FFFFFF"
        )
        self.batch_start_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.batch_cancel_btn = ctk.CTkButton(
            batch_action_btn_row,
            text="⏹ Abbrechen",
            command=self._batch_cancel,
            height=46,
            width=110,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color="#DC2626",
            hover_color="#B91C1C",
            text_color="#FFFFFF",
            state="disabled"
        )
        self.batch_cancel_btn.pack(side="right")

        self.batch_progress_bar = ctk.CTkProgressBar(
            self.batch_action_card,
            height=10,
            corner_radius=5,
            progress_color="#38BDF8",
            fg_color="#0F172A"
        )
        self.batch_progress_bar.pack(fill="x", padx=18, pady=(0, 8))
        self.batch_progress_bar.set(0.0)
        self.batch_progress_bar.pack_forget()

        self.batch_status_lbl = ctk.CTkLabel(
            self.batch_action_card,
            text="Warteschlange bereit.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        )
        self.batch_status_lbl.pack(padx=18, pady=(0, 12))

        # ------------------ 6. Permanent Audio Player & Export Card (Bottom) ------------------
        player_card = ctk.CTkFrame(
            main_content,
            corner_radius=12,
            fg_color=COLOR_CARD_BG,
            border_width=1.5,
            border_color=COLOR_CARD_BORDER
        )
        player_card.pack(fill="x", pady=(0, 10))
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
            width=120,
            height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            state="disabled",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#FFFFFF",
            text_color_disabled="#CBD5E1"
        )
        self.play_btn.grid(row=0, column=0, padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            controls_frame,
            text="■ Stopp",
            command=self._stop_playback,
            width=90,
            height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            state="disabled",
            fg_color="#DC2626",
            hover_color="#B91C1C",
            text_color="#FFFFFF",
            text_color_disabled="#CBD5E1"
        )
        self.stop_btn.grid(row=0, column=1, padx=(0, 14))

        # Interactive Playhead Timeline Slider
        self.timeline_slider = ctk.CTkSlider(
            controls_frame,
            from_=0.0,
            to=1.0,
            number_of_steps=200,
            state="disabled",
            command=self._on_seek_change,
            button_color="#38BDF8",
            button_hover_color="#0284C7",
            progress_color=COLOR_ACCENT
        )
        self.timeline_slider.set(0.0)
        self.timeline_slider.grid(row=0, column=2, sticky="ew", padx=10)

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
            command=self._on_volume_changed,
            button_color="#38BDF8",
            button_hover_color="#0284C7",
            progress_color=COLOR_ACCENT
        )
        self.volume_slider.set(0.8)
        self.volume_slider.grid(row=0, column=5, padx=(0, 0))

        # Export Button
        self.export_btn = ctk.CTkButton(
            player_card,
            text="💾 Audiodatei speichern unter...",
            command=self._export_audio,
            height=42,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            text_color="#FFFFFF",
            text_color_disabled="#CBD5E1",
            state="disabled"
        )
        self.export_btn.grid(row=2, column=0, columnspan=3, sticky="ew", padx=18, pady=(14, 16))

    # ------------------ Mode Switching (Zero Position Shift) ------------------

    def _on_mode_switched(self, mode_value: str):
        """Switches between Single-Text and Batch mode in-place without moving other cards."""
        if "Einzeltext" in mode_value:
            self.current_mode = "single"
            self.batch_card.pack_forget()
            self.batch_action_card.pack_forget()
            self.single_text_card.pack(fill="x", in_=self.input_container, pady=(0, 10))
            self.single_action_card.pack(fill="x", in_=self.action_container, pady=(0, 10))
        else:
            self.current_mode = "batch"
            self.single_text_card.pack_forget()
            self.single_action_card.pack_forget()
            self.batch_card.pack(fill="x", in_=self.input_container, pady=(0, 10))
            self.batch_action_card.pack(fill="x", in_=self.action_container, pady=(0, 10))

    # ------------------ Document Importer (Single Text) ------------------

    def _load_document_to_single_text(self):
        """Allows user to pick a document and places its content in the single text box."""
        file_path = filedialog.askopenfilename(
            title="Dokument für Einzeltext laden",
            filetypes=[
                ("Dokumente (*.txt, *.md, *.pdf, *.docx, *.srt)", "*.txt *.md *.pdf *.docx *.srt"),
                ("Textdateien (*.txt)", "*.txt"),
                ("Markdown (*.md)", "*.md"),
                ("PDF Dokumente (*.pdf)", "*.pdf"),
                ("Word Dokumente (*.docx)", "*.docx"),
                ("Untertitel (*.srt)", "*.srt"),
                ("Alle Dateien", "*.*")
            ]
        )
        if not file_path:
            return

        try:
            extracted = extract_text_from_file(Path(file_path))
            if not extracted:
                messagebox.showwarning("Hinweis", "Aus der Datei konnte kein Text extrahiert werden.")
                return

            self.text_input.delete("0.0", "end")
            self.text_input.insert("0.0", extracted)
            self._update_counters()
            messagebox.showinfo("Import erfolgreich", f"Text aus '{Path(file_path).name}' ({len(extracted):,} Zeichen) wurde erfolgreich ins Textfeld geladen!")
        except Exception as e:
            messagebox.showerror("Fehler beim Dokumenten-Import", f"Die Datei konnte nicht geladen werden:\n{e}")

    # ------------------ Batch Mode Actions ------------------

    def _batch_add_files_dialog(self):
        """Allows multi-selecting files and adds them to batch queue."""
        files = filedialog.askopenfilenames(
            title="Dateien für Stapelverarbeitung auswählen",
            filetypes=[
                ("Dokumente (*.txt, *.md, *.pdf, *.docx, *.srt)", "*.txt *.md *.pdf *.docx *.srt"),
                ("Alle Dateien", "*.*")
            ]
        )
        if not files:
            return

        split = self.batch_split_var.get()
        added_count = 0
        for f in files:
            try:
                items = self.batch_processor.add_file(Path(f), split_chapters=split)
                added_count += len(items)
            except Exception as e:
                messagebox.showerror("Importfehler", f"Fehler bei '{Path(f).name}':\n{e}")

        self._refresh_batch_queue_ui()
        if added_count > 0:
            self.batch_status_lbl.configure(text=f"{len(self.batch_processor.items)} Aufgabe(n) in der Warteschlange.", text_color=COLOR_PRIMARY_TEXT)

    def _batch_add_folder_dialog(self):
        """Allows selecting a folder and adds all supported documents."""
        folder = filedialog.askdirectory(title="Ordner für Stapelverarbeitung auswählen")
        if not folder:
            return

        split = self.batch_split_var.get()
        items = self.batch_processor.add_folder(Path(folder), split_chapters=split)
        self._refresh_batch_queue_ui()
        if items:
            self.batch_status_lbl.configure(text=f"{len(self.batch_processor.items)} Aufgabe(n) in der Warteschlange.", text_color=COLOR_PRIMARY_TEXT)
        else:
            messagebox.showinfo("Hinweis", "Im ausgewählten Ordner wurden keine passenden Dokumente gefunden.")

    def _batch_clear_queue(self):
        if self.batch_processor.is_running:
            messagebox.showwarning("Hinweis", "Warteschlange kann während der laufenden Verarbeitung nicht geleert werden.")
            return
        self.batch_processor.clear_queue()
        self._refresh_batch_queue_ui()
        self.batch_status_lbl.configure(text="Warteschlange geleert.", text_color=COLOR_MUTED_TEXT)

    def _batch_choose_outdir(self):
        folder = filedialog.askdirectory(title="Zielordner für Batch-Export wählen", initialdir=str(self.batch_output_dir))
        if folder:
            self.batch_output_dir = Path(folder)
            self.batch_outdir_lbl.configure(text=str(self.batch_output_dir))

    def _batch_open_outdir(self):
        self.batch_output_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(self.batch_output_dir))
        except Exception:
            subprocess.Popen(["explorer", str(self.batch_output_dir)])

    def _refresh_batch_queue_ui(self):
        """Redraws the queue table with updated item states."""
        for widget in self.queue_frame.winfo_children():
            widget.destroy()

        if not self.batch_processor.items:
            self.queue_empty_lbl = ctk.CTkLabel(
                self.queue_frame,
                text="Keine Dateien in der Warteschlange. Klicke auf '➕ Dateien hinzufügen...', um Dokumente (.txt, .pdf, .docx, .md, .srt) zu laden.",
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                text_color=COLOR_MUTED_TEXT
            )
            self.queue_empty_lbl.pack(pady=20)
            return

        for item in self.batch_processor.items:
            item_row = ctk.CTkFrame(
                self.queue_frame,
                fg_color=("#CBD5E1", "#1E293B"),
                corner_radius=6,
                border_width=1,
                border_color=COLOR_CARD_BORDER
            )
            item_row.pack(fill="x", padx=6, pady=3)
            item_row.grid_columnconfigure(1, weight=1)

            # Icon & Title
            icon_lbl = ctk.CTkLabel(item_row, text="📄", font=ctk.CTkFont(size=14))
            icon_lbl.grid(row=0, column=0, padx=(10, 6), pady=6)

            title_txt = f"{item.title}  ({item.char_count:,} Zeichen | {item.word_count:,} Wörter)"
            name_lbl = ctk.CTkLabel(
                item_row,
                text=title_txt,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                text_color=COLOR_PRIMARY_TEXT,
                anchor="w"
            )
            name_lbl.grid(row=0, column=1, sticky="w", padx=6, pady=6)

            # Status Badge
            status_color = "#94A3B8"
            if "Fertig" in item.status:
                status_color = "#10B981"
            elif "Fehler" in item.status:
                status_color = "#EF4444"
            elif "generiert" in item.status or "Konvertiere" in item.status:
                status_color = "#38BDF8"

            status_lbl = ctk.CTkLabel(
                item_row,
                text=item.status,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                text_color=status_color
            )
            status_lbl.grid(row=0, column=2, padx=10, pady=6)

            # Play Button for completed items
            if item.output_audio and item.output_audio.exists():
                play_item_btn = ctk.CTkButton(
                    item_row,
                    text="▶ Anhören",
                    command=lambda path=item.output_audio: self._play_batch_item_audio(path),
                    width=80,
                    height=26,
                    font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                    fg_color=COLOR_ACCENT,
                    hover_color=COLOR_ACCENT_HOVER,
                    text_color="#FFFFFF"
                )
                play_item_btn.grid(row=0, column=3, padx=6, pady=6)

            # Remove button
            if not self.batch_processor.is_running:
                del_btn = ctk.CTkButton(
                    item_row,
                    text="✕",
                    command=lambda it_id=item.id: self._remove_batch_item(it_id),
                    width=28,
                    height=26,
                    font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                    fg_color="#DC2626",
                    hover_color="#B91C1C",
                    text_color="#FFFFFF"
                )
                del_btn.grid(row=0, column=4, padx=(0, 6), pady=6)

    def _remove_batch_item(self, item_id: str):
        self.batch_processor.remove_item(item_id)
        self._refresh_batch_queue_ui()
        self.batch_status_lbl.configure(text=f"{len(self.batch_processor.items)} Aufgabe(n) in der Warteschlange.", text_color=COLOR_PRIMARY_TEXT)

    def _play_batch_item_audio(self, audio_path: Path):
        self.current_converted_file = audio_path
        self.player.load(audio_path)
        self.play_btn.configure(state="normal", text="▶ Abspielen")
        self.stop_btn.configure(state="normal")
        self.export_btn.configure(state="normal")
        self.timeline_slider.configure(state="normal")
        self._toggle_playback()

    def _batch_start_processing(self):
        if not self.batch_processor.items:
            messagebox.showwarning("Hinweis", "Keine Dateien in der Warteschlange vorhanden.")
            return

        if not get_api_key():
            self._open_api_key_dialog()
            return

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

        encoding_settings = self._get_current_encoding_settings()

        self.batch_start_btn.configure(state="disabled", text="⏳ Batch-Generierung läuft...")
        self.batch_cancel_btn.configure(state="normal")
        self.batch_progress_bar.pack(fill="x", padx=18, pady=(0, 8))
        self.batch_progress_bar.set(0.0)

        self.batch_processor.process_queue(
            tts_service=self.tts_service,
            voice_name=voice_choice,
            model=model_id,
            language=lang_id,
            encoding_settings=encoding_settings,
            output_directory=self.batch_output_dir,
            on_item_update=lambda item: self.after(0, self._refresh_batch_queue_ui),
            on_batch_update=lambda curr, total, prog: self.after(0, self._on_batch_progress_ui, curr, total, prog),
            on_batch_complete=lambda items: self.after(0, self._on_batch_finished_ui, items)
        )

    def _on_batch_progress_ui(self, current: int, total: int, prog_val: float):
        self.batch_progress_bar.set(prog_val)
        self.batch_status_lbl.configure(
            text=f"Verarbeite Aufgabe {current} von {total}...",
            text_color="#38BDF8"
        )

    def _on_batch_finished_ui(self, items: List[BatchItem]):
        self.batch_start_btn.configure(state="normal", text="⚡ Alle Dateien in Warteschlange generieren")
        self.batch_cancel_btn.configure(state="disabled")
        self.batch_progress_bar.set(1.0)
        self.after(1000, lambda: self.batch_progress_bar.pack_forget())
        
        success_count = sum(1 for i in items if i.status == "Fertig ✅")
        self.batch_status_lbl.configure(
            text=f"✅ Batch abgeschlossen! {success_count} von {len(items)} Dateien erfolgreich generiert.",
            text_color="#10B981"
        )
        self._refresh_batch_queue_ui()
        messagebox.showinfo("Batch abgeschlossen", f"Stapelverarbeitung abgeschlossen!\n{success_count} von {len(items)} Audiodateien wurden in '{self.batch_output_dir.name}' gespeichert.")

    def _batch_cancel(self):
        if self.batch_processor.is_running:
            self.batch_processor.cancel()
            self.batch_status_lbl.configure(text="Abbruch angefordert... bitte warten.", text_color="#EF4444")
            self.batch_cancel_btn.configure(state="disabled")

    # ------------------ Collapsible Format Helper Methods ------------------

    def _toggle_format_panel(self):
        """Toggle collapsible Audio Format settings panel."""
        if self.is_format_collapsed:
            self.format_body_frame.pack(fill="x", padx=0, pady=(0, 0))
            self.format_toggle_btn.configure(text="▴ Zuklappen")
            self.format_title_lbl.configure(text="🎛️ Audioformat & Enkodierung")
            self.is_format_collapsed = False
        else:
            self.format_body_frame.pack_forget()
            preset_name = self.preset_var.get().split("(")[0].replace("🌐", "").replace("🎵", "").replace("🎧", "").replace("📻", "").replace("💿", "").strip()
            self.format_title_lbl.configure(text=f"🎛️ Audioformat: {preset_name}")
            self.format_toggle_btn.configure(text="▾ Einstellungen anpassen")
            self.is_format_collapsed = True

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
        self.char_counter_lbl.configure(text=f"{chars:,} Zeichen | {words:,} Wörter")

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

    # ------------------ Single Generation & Processing ------------------

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
        self.status_lbl.configure(text="Initialisiere Sprachgenerierung...", text_color="#38BDF8")
        
        thread = threading.Thread(target=self._run_generation, args=(text,), daemon=True)
        thread.start()

    def _update_generation_progress(self, progress_val: float, message: str):
        self.after(0, self._set_progress_ui, progress_val, message)

    def _set_progress_ui(self, progress_val: float, message: str):
        self.progress_bar.set(progress_val)
        self.status_lbl.configure(text=message, text_color="#38BDF8")

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
