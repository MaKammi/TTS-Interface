"""
Modern, high-contrast GUI for Gemini TTS Studio
Includes Single-Text Mode with Document Importer and Full Batch / Document Queue Processing.
Features Global System-Prompt / Tone Directives with Custom Preset Saving, 32 Languages, and Automatic Translation.
Rock-solid stable layout hierarchy where no elements jump or shift when switching tabs.
"""

import math
import os
import struct
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Optional, Dict, Any, List

import customtkinter as ctk
from tkinter import filedialog, messagebox

from .config import (
    AVAILABLE_VOICES,
    AVAILABLE_MODELS,
    SUPPORTED_LANGUAGES,
    STYLE_SUGGESTIONS,
    AUDIO_TAGS,
    AUDIO_PRESETS,
    get_api_key,
    save_api_key,
    OUTPUT_DIR,
    TEMP_DIR,
    load_custom_styles,
    save_custom_style,
    delete_custom_style,
)
from .tts_service import GeminiTTSService
from .audio_converter import convert_audio
from .player import AudioPlayer
from .document_parser import extract_text_from_file, split_into_chapters
from .batch_processor import BatchProcessor, BatchItem
from .translation_service import TranslationService


ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

# Typography & Color Constants for Google Material 3 Expressive System (ZQP Edition)
FONT_FAMILY = "Segoe UI"

# High-contrast Text Constants (WCAG AAA compliant)
COLOR_PRIMARY_TEXT = ("#191C1B", "#E0E8E6")       # Deep Charcoal (Light) / Off-White (Dark)
COLOR_MUTED_TEXT = ("#3F4946", "#A2B2AE")         # Slate Teal Secondary Text

# Material 3 Tonal Roles (derived from ZQP Brand DNA)
M3_PRIMARY = ("#17534A", "#52DBCA")               # ZQP Forest Teal / Mint Teal
M3_PRIMARY_HOVER = ("#10413A", "#38C2B0")
M3_PRIMARY_CONTAINER = ("#C8ECE4", "#005048")     # Soft Tonal Teal
M3_ON_PRIMARY_CONTAINER = ("#00201C", "#74F8E6")

M3_SECONDARY = ("#48635E", "#AFC9C3")
M3_SECONDARY_CONTAINER = ("#CCE8E2", "#1C302D")   # M3 Soft Sage Tonal
M3_ON_SECONDARY_CONTAINER = ("#05201B", "#C0D8D2")

M3_CTA = "#D45524"                                 # ZQP Terracotta / Warm Coral
M3_CTA_HOVER = "#B84315"
M3_CTA_CONTAINER = ("#FFDBCF", "#380D00")

M3_SURFACE = ("#FFFFFF", "#152422")               # Card Surface
M3_SURFACE_DIM = ("#F4F7F6", "#0E1715")           # App Window Background
M3_SURFACE_CONTAINER = ("#EEF4F2", "#182826")     # Dropdown & Inset Field Background
M3_SURFACE_CONTAINER_HIGH = ("#E7EFEF", "#203431")

M3_OUTLINE = ("#BFC9C6", "#384C48")               # Outlined Button Borders
M3_OUTLINE_VARIANT = ("#D9E3E0", "#243834")       # Subtle Card & Field Borders

M3_ERROR = ("#BA1A1A", "#FFB4AB")
M3_ERROR_CONTAINER = ("#FFDAD6", "#5C1D1D")
M3_ERROR_HOVER = ("#FFEDEA", "#2D1010")

# Aliases for compatibility
COLOR_ACCENT = M3_PRIMARY
COLOR_ACCENT_HOVER = M3_PRIMARY_HOVER
COLOR_CTA = M3_CTA
COLOR_CTA_HOVER = M3_CTA_HOVER
COLOR_CARD_BG = M3_SURFACE
COLOR_CARD_BORDER = M3_OUTLINE_VARIANT
COLOR_APP_BG = M3_SURFACE_DIM
COLOR_SUBCARD_BG = M3_SURFACE_CONTAINER


class WaveformCanvas(ctk.CTkCanvas):
    """
    Visual audio waveform display composed of vertical amplitude bars.
    Supports real audio peak extraction, interactive scrubbing, and theme adaptation.
    """

    def __init__(self, parent, on_seek_callback=None, **kwargs):
        super().__init__(parent, highlightthickness=0, **kwargs)
        self.on_seek_callback = on_seek_callback
        self.amplitudes: List[float] = self._generate_idle_wave()
        self.progress: float = 0.0
        self.is_scrubbing = False

        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda e: self.config(cursor="hand2"))
        self.bind("<Leave>", lambda e: self.config(cursor=""))

    def _generate_idle_wave(self, num_bars: int = 80) -> List[float]:
        """Generate a gentle baseline wave when no audio is loaded."""
        wave_pts = []
        for i in range(num_bars):
            v = 0.28 + 0.18 * math.sin(i * 0.22) + 0.09 * math.cos(i * 0.44)
            wave_pts.append(max(0.12, min(0.75, v)))
        return wave_pts

    def load_audio(self, wav_path: Path | str, num_bars: int = 80):
        """Extract peak amplitudes from a WAV audio file."""
        try:
            p = Path(wav_path)
            if not p.exists():
                return
            with wave.open(str(p), "rb") as wf:
                width = wf.getsampwidth()
                frames = wf.getnframes()
                if frames == 0 or width != 2:
                    return
                chunk_size = max(1, frames // num_bars)
                peaks = []
                for _ in range(num_bars):
                    data = wf.readframes(chunk_size)
                    if not data:
                        break
                    count = len(data) // 2
                    samples = struct.unpack(f"<{count}h", data)
                    step = max(1, count // 40)
                    sub = [abs(s) for s in samples[::step]]
                    avg = sum(sub) / len(sub) if sub else 0
                    peaks.append(avg)

                max_p = max(peaks) if peaks and max(peaks) > 0 else 1
                self.amplitudes = [max(0.12, min(0.95, p / max_p)) for p in peaks]
        except Exception as e:
            print(f"Hinweis: Waveform konnte nicht aus Audio geladen werden: {e}")
            self.amplitudes = self._generate_idle_wave(num_bars)

        self.redraw()

    def set_progress(self, progress: float):
        self.progress = max(0.0, min(1.0, progress))
        self.redraw()

    def _on_resize(self, event=None):
        self.redraw()

    def _on_click(self, event):
        self.is_scrubbing = True
        self._seek_from_event(event)

    def _on_drag(self, event):
        if self.is_scrubbing:
            self._seek_from_event(event)

    def _on_release(self, event):
        self.is_scrubbing = False
        self._seek_from_event(event)

    def _seek_from_event(self, event):
        w = self.winfo_width()
        if w > 0:
            pct = max(0.0, min(1.0, event.x / float(w)))
            self.progress = pct
            self.redraw()
            if self.on_seek_callback:
                self.on_seek_callback(pct)

    def redraw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        is_dark = (ctk.get_appearance_mode() == "Dark")
        bg_color = "#182826" if is_dark else "#EEF4F2"
        self.configure(bg=bg_color)

        color_active = "#52DBCA" if is_dark else "#17534A"
        color_inactive = "#28403C" if is_dark else "#D0E0DC"
        color_playhead = "#D45524"

        n = len(self.amplitudes)
        if n == 0:
            return

        gap = 2.0
        bar_width = max(2.0, (w - (n * gap)) / float(n))
        total_bar_slot = bar_width + gap

        center_y = h / 2.0
        max_half_h = (h / 2.0) - 3.0

        for i, amp in enumerate(self.amplitudes):
            x0 = i * total_bar_slot + (gap / 2.0)
            x1 = x0 + bar_width
            bar_h = max(2.5, amp * max_half_h)
            y0 = center_y - bar_h
            y1 = center_y + bar_h

            bar_pct = i / float(n)
            fill_col = color_active if bar_pct <= self.progress else color_inactive

            self.create_rectangle(x0, y0, x1, y1, fill=fill_col, outline="", width=0)

        # Playhead indicator
        playhead_x = self.progress * w
        self.create_line(playhead_x, 1, playhead_x, h - 1, fill=color_playhead, width=2.5)


class MaterialSegmentedControl(ctk.CTkFrame):
    """
    Google Material 3 Expressive Segmented Control with stadium pill buttons
    and guaranteed high contrast ratio in both selected and unselected states.
    """

    def __init__(self, parent, values: List[str], command=None, height: int = 46, **kwargs):
        super().__init__(
            parent,
            height=height,
            corner_radius=23,
            fg_color=M3_SURFACE_CONTAINER,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT,
            **kwargs
        )
        self.command = command
        self.values = values
        self.current_value = values[0]
        self.buttons: List[tuple] = []

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(tuple(range(len(values))), weight=1)

        for i, val in enumerate(values):
            btn = ctk.CTkButton(
                self,
                text=val,
                height=height - 8,
                corner_radius=19,
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
                command=lambda v=val: self.set(v)
            )
            btn.grid(row=0, column=i, padx=4, pady=4, sticky="nsew")
            self.buttons.append((val, btn))

        self._update_button_styles()

    def set(self, value: str):
        self.current_value = value
        self._update_button_styles()
        if self.command:
            self.command(value)

    def get(self) -> str:
        return self.current_value

    def _update_button_styles(self):
        for val, btn in self.buttons:
            if val == self.current_value:
                btn.configure(
                    fg_color=M3_PRIMARY,
                    hover_color=M3_PRIMARY_HOVER,
                    text_color=("#FFFFFF", "#00201C")
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    hover_color=("#E0ECE9", "#243834"),
                    text_color=COLOR_PRIMARY_TEXT
                )



class APIKeyDialog(ctk.CTkToplevel):
    """Dialog for viewing and editing the Gemini API Key."""

    def __init__(self, parent, on_save_callback):
        super().__init__(parent)
        self.title("Gemini API-Key Einstellungen")
        self.geometry("540x260")
        self.resizable(False, False)
        self.on_save_callback = on_save_callback

        frame = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        lbl = ctk.CTkLabel(
            frame,
            text="Google Gemini API-Key",
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        lbl.pack(pady=(18, 6))

        desc = ctk.CTkLabel(
            frame,
            text="Trage hier deinen API-Key aus Google AI Studio ein.\nDer Key wird sicher in deiner lokalen .env Datei gespeichert.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT,
            justify="center"
        )
        desc.pack(pady=(0, 14))

        self.key_entry = ctk.CTkEntry(
            frame,
            placeholder_text="AQ... oder AIzaSy...",
            show="*",
            width=440,
            height=40,
            corner_radius=12,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT,
            fg_color=M3_SURFACE_CONTAINER,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.key_entry.pack(pady=6)
        self.key_entry.insert(0, get_api_key())

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=(18, 12))

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Speichern",
            command=self._save,
            width=130,
            height=36,
            corner_radius=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=M3_PRIMARY,
            hover_color=M3_PRIMARY_HOVER,
            text_color=("#FFFFFF", "#00201C")
        )
        save_btn.pack(side="left", padx=8)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            command=self.destroy,
            width=110,
            height=36,
            corner_radius=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=COLOR_MUTED_TEXT,
            border_width=1.5,
            border_color=M3_OUTLINE
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
        self.geometry("1120x920")
        self.minsize(860, 560)

        self.tts_service = GeminiTTSService()
        self.player = AudioPlayer()
        self.batch_processor = BatchProcessor()
        self.translation_service = TranslationService()
        
        self.current_generated_wav: Optional[Path] = None
        self.current_converted_file: Optional[Path] = None
        self.is_generating = False
        self.is_user_scrubbing = False
        self.is_format_collapsed = True   # Collapsed by default
        self.is_style_collapsed = False   # Open by default as requested
        self.is_tags_collapsed = True     # Tags under main text field collapsed by default
        self.is_batch_lang_collapsed = True # Collapsed by default
        self.current_mode = "single"       # "single" or "batch"
        self.batch_output_dir = OUTPUT_DIR / "batch_exports"

        self._build_ui()
        self._setup_player_timer()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ------------------ Header Bar ------------------
        header_frame = ctk.CTkFrame(self, height=64, corner_radius=0, fg_color=M3_SURFACE)
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        title_label = ctk.CTkLabel(
            header_frame,
            text="🎙️ Gemini TTS Studio",
            font=ctk.CTkFont(family=FONT_FAMILY, size=21, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        title_label.grid(row=0, column=0, padx=24, pady=14, sticky="w")

        # API-Key Badge & Settings Button (M3 Tonal Pill)
        self.key_status_btn = ctk.CTkButton(
            header_frame,
            text=self._get_key_status_text(),
            command=self._open_api_key_dialog,
            width=180,
            height=36,
            corner_radius=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_PRIMARY_CONTAINER,
            hover_color=("#B6E4DA", "#00645A"),
            text_color=M3_ON_PRIMARY_CONTAINER,
            border_width=0
        )
        self.key_status_btn.grid(row=0, column=2, padx=(0, 14), pady=14, sticky="e")

        self.theme_switch = ctk.CTkSwitch(
            header_frame,
            text="Dunkelmodus",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT,
            progress_color=M3_PRIMARY[0]
        )
        # Default is Light mode (unselected)
        self.theme_switch.grid(row=0, column=3, padx=20, pady=14, sticky="e")

        # ------------------ Main Auto-Scrollable Content Frame ------------------
        main_content = AutoScrollableFrame(self, fg_color="transparent")
        main_content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        main_content.grid_columnconfigure(0, weight=1)

        # ------------------ 1. Mode Selector (Permanent Top) ------------------
        mode_frame = ctk.CTkFrame(main_content, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(0, 12))

        self.mode_segmented = MaterialSegmentedControl(
            mode_frame,
            values=["✍️ Einzeltext-Modus", "📂 Dokumenten- & Batch-Import"],
            command=self._on_mode_switched,
            height=46
        )
        self.mode_segmented.pack(fill="x")

        # ------------------ 2. Input Container (Permanent Slot) ------------------
        self.input_container = ctk.CTkFrame(main_content, fg_color="transparent")
        self.input_container.pack(fill="x", pady=(0, 0))

        # 2A: Single-Text Card (M3 Elevated Card)
        self.single_text_card = ctk.CTkFrame(
            self.input_container,
            corner_radius=20,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        self.single_text_card.pack(fill="x", pady=(0, 12))

        text_header_frame = ctk.CTkFrame(self.single_text_card, fg_color="transparent")
        text_header_frame.pack(fill="x", padx=20, pady=(16, 8))

        text_title = ctk.CTkLabel(
            text_header_frame,
            text="📝 Haupttext zur Sprachausgabe (Skriptfeld)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        text_title.pack(side="left")

        # Translation Button (M3 Tonal Pill)
        self.translate_single_btn = ctk.CTkButton(
            text_header_frame,
            text="🌐 In Zielsprache übersetzen",
            command=self._translate_single_text,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_SECONDARY_CONTAINER,
            hover_color=("#BDDFD8", "#24403C"),
            text_color=M3_ON_SECONDARY_CONTAINER,
            border_width=0
        )
        self.translate_single_btn.pack(side="right", padx=(8, 0))

        # Quick Document Loader Button (M3 Outlined Pill)
        load_doc_btn = ctk.CTkButton(
            text_header_frame,
            text="📂 Dokument laden",
            command=self._load_document_to_single_text,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=M3_PRIMARY,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        load_doc_btn.pack(side="right", padx=(8, 0))

        self.char_counter_lbl = ctk.CTkLabel(
            text_header_frame,
            text="0 Zeichen | 0 Wörter",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        )
        self.char_counter_lbl.pack(side="right", padx=(0, 8))

        # Main text input area (Enlarged to 250px as dominant Hero field)
        self.text_input = ctk.CTkTextbox(
            self.single_text_card,
            height=250,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            wrap="word",
            corner_radius=16,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT,
            fg_color=("#FFFFFF", "#0E1A18"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.text_input.pack(fill="x", padx=20, pady=(0, 8))
        self.text_input.insert("0.0", "Hallo! Dies ist ein Test mit Gemini TTS. [lachen] Es ist wirklich erstaunlich, wie lebendig die Stimme klingt! [flüstern] Kannst du ein Geheimnis für dich behalten?")
        self.text_input.bind("<KeyRelease>", self._update_counters)
        self._update_counters()

        # Translation check row
        trans_options_frame = ctk.CTkFrame(self.single_text_card, fg_color="transparent")
        trans_options_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.auto_translate_var = ctk.BooleanVar(value=False)
        self.auto_translate_check = ctk.CTkCheckBox(
            trans_options_frame,
            text="Text vor Vertonung automatisch in die ausgewählte Zielsprache übersetzen",
            variable=self.auto_translate_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT,
            fg_color=M3_PRIMARY[0],
            hover_color=M3_PRIMARY_HOVER[0]
        )
        self.auto_translate_check.pack(side="left")

        # Audio-Tags Toolbar (Collapsible by default as requested)
        self.tag_section_frame = ctk.CTkFrame(self.single_text_card, fg_color="transparent")
        self.tag_section_frame.pack(fill="x", padx=20, pady=(0, 14))

        tag_header_row = ctk.CTkFrame(self.tag_section_frame, fg_color="transparent")
        tag_header_row.pack(fill="x", pady=(0, 4))

        tag_title_lbl = ctk.CTkLabel(
            tag_header_row,
            text="🎭 Audio-Tags einfügen (z. B. [lachen], [flüstern], [Pause]):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=M3_PRIMARY
        )
        tag_title_lbl.pack(side="left")

        self.tag_toggle_btn = ctk.CTkButton(
            tag_header_row,
            text="▾ Audio-Tags anzeigen",
            command=self._toggle_tags_panel,
            height=32,
            width=170,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=M3_PRIMARY,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        self.tag_toggle_btn.pack(side="right")

        self.tag_buttons_frame = ctk.CTkFrame(self.tag_section_frame, fg_color="transparent")
        self.tag_buttons_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        # Collapsed by default

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

        for i, (tag_code, label_text) in enumerate(tags_display_list):
            row_idx = i // 5
            col_idx = i % 5
            btn = ctk.CTkButton(
                self.tag_buttons_frame,
                text=label_text,
                command=lambda t=tag_code: self._insert_tag(t),
                height=34,
                corner_radius=12,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                fg_color=M3_SURFACE_CONTAINER,
                hover_color=M3_PRIMARY_CONTAINER,
                text_color=COLOR_PRIMARY_TEXT,
                border_width=1,
                border_color=M3_OUTLINE_VARIANT
            )
            btn.grid(row=row_idx, column=col_idx, padx=3, pady=3, sticky="ew")

        # 2B: Batch Card (Instantiated, packed only in batch mode)
        self.batch_card = ctk.CTkFrame(
            self.input_container,
            corner_radius=20,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )

        batch_header = ctk.CTkFrame(self.batch_card, fg_color="transparent")
        batch_header.pack(fill="x", padx=20, pady=(16, 8))

        ctk.CTkLabel(
            batch_header,
            text="📂 Dokumenten- & Stapelverarbeitung (Batch)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left")

        # Toolbar
        toolbar_frame = ctk.CTkFrame(self.batch_card, fg_color="transparent")
        toolbar_frame.pack(fill="x", padx=20, pady=(0, 12))

        add_files_btn = ctk.CTkButton(
            toolbar_frame,
            text="➕ Dateien hinzufügen...",
            command=self._batch_add_files_dialog,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_PRIMARY_CONTAINER,
            hover_color=("#B6E4DA", "#00645A"),
            text_color=M3_ON_PRIMARY_CONTAINER,
            border_width=0
        )
        add_files_btn.pack(side="left", padx=(0, 8))

        add_folder_btn = ctk.CTkButton(
            toolbar_frame,
            text="📁 Ordner importieren...",
            command=self._batch_add_folder_dialog,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=M3_PRIMARY,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        add_folder_btn.pack(side="left", padx=(0, 8))

        clear_btn = ctk.CTkButton(
            toolbar_frame,
            text="🗑️ Liste leeren",
            command=self._batch_clear_queue,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="transparent",
            hover_color=M3_ERROR_HOVER,
            text_color=M3_ERROR,
            border_width=1.5,
            border_color=M3_ERROR_CONTAINER
        )
        clear_btn.pack(side="left")

        # Options Row (Chapter Splitting, Multilingual Export & Output Directory)
        options_frame = ctk.CTkFrame(
            self.batch_card,
            fg_color=M3_SURFACE_CONTAINER,
            corner_radius=14,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        options_frame.pack(fill="x", padx=20, pady=(0, 12))

        self.batch_split_var = ctk.BooleanVar(value=True)
        split_check = ctk.CTkCheckBox(
            options_frame,
            text="Lange Dokumente automatisch in Kapitel aufteilen (# Überschriften)",
            variable=self.batch_split_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT,
            fg_color=M3_PRIMARY[0],
            hover_color=M3_PRIMARY_HOVER[0]
        )
        split_check.pack(anchor="w", padx=14, pady=(12, 8))

        # Multi-Language Collapsible Section for Batch
        self.batch_lang_section = ctk.CTkFrame(options_frame, fg_color="transparent")
        self.batch_lang_section.pack(fill="x", padx=14, pady=(0, 10))

        # Always-visible Header Row
        lang_header_row = ctk.CTkFrame(self.batch_lang_section, fg_color="transparent")
        lang_header_row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            lang_header_row,
            text="🌐 Mehrsprachiger Export (Zielsprachen):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left", padx=(0, 8))

        self.batch_lang_summary_lbl = ctk.CTkLabel(
            lang_header_row,
            text="1 Sprache: 🇩🇪 Deutsch",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=M3_PRIMARY
        )
        self.batch_lang_summary_lbl.pack(side="left", padx=(0, 10))

        self.batch_lang_toggle_btn = ctk.CTkButton(
            lang_header_row,
            text="▾ 31 Sprachen anpassen",
            command=self._toggle_batch_lang_panel,
            height=28,
            width=180,
            corner_radius=14,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=M3_PRIMARY,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        self.batch_lang_toggle_btn.pack(side="right")

        # Collapsible Body Frame (Hidden by default)
        self.batch_lang_body_frame = ctk.CTkFrame(
            self.batch_lang_section,
            fg_color=M3_SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )

        # Quick Actions Bar inside collapsible body
        quick_bar = ctk.CTkFrame(self.batch_lang_body_frame, fg_color="transparent")
        quick_bar.pack(fill="x", padx=12, pady=(10, 8))

        ctk.CTkLabel(
            quick_bar,
            text="Schnellauswahl:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        ).pack(side="left", padx=(0, 8))

        for q_label, q_type in [
            ("🇩🇪 Nur Deutsch", "de_only"),
            ("🌍 Top 5 (DE, EN, ES, FR, IT)", "top5"),
            ("🌐 Alle 31 Sprachen", "all"),
            ("✕ Alle abwählen", "none")
        ]:
            q_btn = ctk.CTkButton(
                quick_bar,
                text=q_label,
                command=lambda t=q_type: self._set_batch_langs_preset(t),
                height=26,
                corner_radius=13,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                fg_color=M3_SURFACE_CONTAINER,
                hover_color=M3_PRIMARY_CONTAINER,
                text_color=COLOR_PRIMARY_TEXT,
                border_width=1,
                border_color=M3_OUTLINE_VARIANT
            )
            q_btn.pack(side="left", padx=3)

        # Checkbox Grid for all 31 supported languages
        grid_frame = ctk.CTkFrame(self.batch_lang_body_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=12, pady=(0, 12))
        grid_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.batch_lang_vars = {}
        batch_langs = [l for l in SUPPORTED_LANGUAGES if l["id"] != "auto"]

        for i, lang in enumerate(batch_langs):
            col = i % 4
            row = i // 4
            l_code = lang["id"]
            var = ctk.BooleanVar(value=(l_code == "de"))
            self.batch_lang_vars[l_code] = var

            cb = ctk.CTkCheckBox(
                grid_frame,
                text=lang["name"],
                variable=var,
                command=self._update_batch_lang_summary,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                text_color=COLOR_PRIMARY_TEXT,
                fg_color=M3_PRIMARY[0],
                hover_color=M3_PRIMARY_HOVER[0]
            )
            cb.grid(row=row, column=col, sticky="w", padx=6, pady=4)

        outdir_row = ctk.CTkFrame(options_frame, fg_color="transparent")
        outdir_row.pack(fill="x", padx=14, pady=(0, 12))

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
            text_color=M3_PRIMARY
        )
        self.batch_outdir_lbl.pack(side="left", fill="x", expand=True, padx=(0, 8))

        change_outdir_btn = ctk.CTkButton(
            outdir_row,
            text="Ändern...",
            command=self._batch_choose_outdir,
            width=90,
            height=30,
            corner_radius=15,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=M3_PRIMARY,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        change_outdir_btn.pack(side="right", padx=(0, 6))

        open_outdir_btn = ctk.CTkButton(
            outdir_row,
            text="📂 Ordner öffnen",
            command=self._batch_open_outdir,
            width=120,
            height=30,
            corner_radius=15,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=M3_SECONDARY_CONTAINER,
            hover_color=("#BDDFD8", "#24403C"),
            text_color=M3_ON_SECONDARY_CONTAINER,
            border_width=0
        )
        open_outdir_btn.pack(side="right", padx=(0, 6))

        # Batch Queue Table / List
        self.queue_frame = ctk.CTkScrollableFrame(
            self.batch_card,
            height=160,
            fg_color=M3_SURFACE_CONTAINER,
            corner_radius=14,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        self.queue_frame.pack(fill="x", padx=20, pady=(0, 14))

        self.queue_empty_lbl = ctk.CTkLabel(
            self.queue_frame,
            text="Keine Dateien in der Warteschlange. Klicke auf '➕ Dateien hinzufügen...', um Dokumente (.txt, .pdf, .docx, .md, .srt) zu laden.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        )
        self.queue_empty_lbl.pack(pady=20)

        # ------------------ 3. Regieanweisung & Sprechstil (System-Prompt) Card (MOVED UP) ------------------
        # Positioned right below the input container so it is immediately adjacent to the text!
        self.style_card = ctk.CTkFrame(
            main_content,
            corner_radius=20,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        self.style_card.pack(fill="x", pady=(0, 12))

        # Header Row
        self.style_header_frame = ctk.CTkFrame(self.style_card, fg_color="transparent")
        self.style_header_frame.pack(fill="x", padx=20, pady=(16, 8))

        self.style_title_lbl = ctk.CTkLabel(
            self.style_header_frame,
            text="🎭 Regieanweisung & Sprechstil (System-Prompt)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.style_title_lbl.pack(side="left")

        self.style_toggle_btn = ctk.CTkButton(
            self.style_header_frame,
            text="▴ Zuklappen",
            command=self._toggle_style_panel,
            width=130,
            height=32,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=M3_PRIMARY,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        self.style_toggle_btn.pack(side="right")

        # Body Container (Open by default)
        self.style_body_frame = ctk.CTkFrame(self.style_card, fg_color="transparent")
        self.style_body_frame.pack(fill="x", padx=20, pady=(0, 14))

        # Presets Toolbar Row
        preset_style_row = ctk.CTkFrame(self.style_body_frame, fg_color="transparent")
        preset_style_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            preset_style_row,
            text="Stil-Vorlage:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left", padx=(0, 8))

        self.style_preset_var = ctk.StringVar(value=STYLE_SUGGESTIONS[0][0])
        self.style_preset_menu = ctk.CTkOptionMenu(
            preset_style_row,
            values=[p[0] for p in STYLE_SUGGESTIONS],
            variable=self.style_preset_var,
            command=self._on_style_preset_changed,
            height=34,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE_CONTAINER,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
        )
        self.style_preset_menu.pack(side="left", fill="x", expand=True, padx=(0, 8))

        save_style_btn = ctk.CTkButton(
            preset_style_row,
            text="💾 Als Vorlage speichern...",
            command=self._save_current_style_preset,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_PRIMARY_CONTAINER,
            hover_color=("#B6E4DA", "#00645A"),
            text_color=M3_ON_PRIMARY_CONTAINER,
            border_width=0
        )
        save_style_btn.pack(side="left", padx=(0, 6))

        delete_style_btn = ctk.CTkButton(
            preset_style_row,
            text="🗑️ Vorlage löschen",
            command=self._delete_current_style_preset,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="transparent",
            hover_color=M3_ERROR_HOVER,
            text_color=M3_ERROR,
            border_width=1.5,
            border_color=M3_ERROR_CONTAINER
        )
        delete_style_btn.pack(side="left", padx=(0, 6))

        clear_style_btn = ctk.CTkButton(
            preset_style_row,
            text="Leeren",
            command=self._clear_style,
            width=80,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=COLOR_MUTED_TEXT,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        clear_style_btn.pack(side="left")

        # Multi-line Textarea for Regieanweisung
        self.style_input = ctk.CTkTextbox(
            self.style_body_frame,
            height=68,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            wrap="word",
            corner_radius=14,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT,
            fg_color=("#FFFFFF", "#0E1A18"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.style_input.pack(fill="x", pady=(0, 6))

        style_hint_lbl = ctk.CTkLabel(
            self.style_body_frame,
            text="💡 Beschreibe Tonfall, Sprechrolle oder Atmosphäre (z. B. 'Ruhig und gelassen wie in einer Dokumentation', 'Aufgeregt und enthusiastisch', etc.). Wird von Gemini TTS tonal umgesetzt, aber nicht vorgelesen.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT,
            wraplength=800,
            justify="left"
        )
        style_hint_lbl.pack(anchor="w")

        # Refresh presets menu with user saved presets
        self._refresh_style_presets()

        # ------------------ 4. Permanent Voice, Language & Model Card ------------------
        voice_card = ctk.CTkFrame(
            main_content,
            corner_radius=20,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        voice_card.pack(fill="x", pady=(0, 12))
        voice_card.grid_columnconfigure((0, 1, 2), weight=1)

        # Voice Selector
        voice_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        voice_box.grid(row=0, column=0, padx=18, pady=16, sticky="nsew")
        
        ctk.CTkLabel(
            voice_box,
            text="🗣️ Stimme",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 6))

        voice_options = [f"{v['id']} ({v['desc'].split('(')[-1].replace(')', '')})" for v in AVAILABLE_VOICES]
        self.voice_var = ctk.StringVar(value=voice_options[0])
        self.voice_menu = ctk.CTkOptionMenu(
            voice_box,
            values=voice_options,
            variable=self.voice_var,
            command=self._on_voice_changed,
            height=38,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=M3_SURFACE_CONTAINER,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
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
        self.voice_desc_lbl.pack(anchor="w", pady=(6, 0))

        # Language Selector (32 Languages)
        lang_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        lang_box.grid(row=0, column=1, padx=18, pady=16, sticky="nsew")

        ctk.CTkLabel(
            lang_box,
            text="🌐 Sprache",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 6))

        lang_options = [l["name"] for l in SUPPORTED_LANGUAGES]
        self.lang_var = ctk.StringVar(value=lang_options[0])
        self.lang_menu = ctk.CTkOptionMenu(
            lang_box,
            values=lang_options,
            variable=self.lang_var,
            height=38,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=M3_SURFACE_CONTAINER,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
        )
        self.lang_menu.pack(fill="x")

        ctk.CTkLabel(
            lang_box,
            text="32 Sprachen unterstützt (Auto-Detect oder Zielsprache).",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(6, 0))

        # Model Selector (Defaults to Gemini 3.1 Flash TTS)
        model_box = ctk.CTkFrame(voice_card, fg_color="transparent")
        model_box.grid(row=0, column=2, padx=18, pady=16, sticky="nsew")

        ctk.CTkLabel(
            model_box,
            text="🤖 Gemini TTS Modell",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 6))

        model_options = [m["name"] for m in AVAILABLE_MODELS]
        self.model_var = ctk.StringVar(value=model_options[0])
        self.model_menu = ctk.CTkOptionMenu(
            model_box,
            values=model_options,
            variable=self.model_var,
            height=38,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=M3_SURFACE_CONTAINER,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
        )
        self.model_menu.pack(fill="x")

        ctk.CTkLabel(
            model_box,
            text="Standard: Gemini 3.1 Flash TTS Engine.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(6, 0))

        # ------------------ 5. Permanent Collapsible Audio Format Card ------------------
        self.format_card = ctk.CTkFrame(
            main_content,
            corner_radius=20,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        self.format_card.pack(fill="x", pady=(0, 12))

        # Collapsible Header
        self.format_header_frame = ctk.CTkFrame(self.format_card, fg_color="transparent")
        self.format_header_frame.pack(fill="x", padx=20, pady=12)

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
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=M3_PRIMARY,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        self.format_toggle_btn.pack(side="right")

        # Collapsible Body Container (hidden by default)
        self.format_body_frame = ctk.CTkFrame(self.format_card, fg_color="transparent")

        # Preset Selector Row
        preset_frame = ctk.CTkFrame(self.format_body_frame, fg_color="transparent")
        preset_frame.pack(fill="x", padx=20, pady=(0, 10))

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
            corner_radius=12,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=M3_SURFACE_CONTAINER,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
        )
        self.preset_menu.pack(side="left", fill="x", expand=True)

        # Settings panel
        self.custom_settings_frame = ctk.CTkFrame(
            self.format_body_frame,
            fg_color=M3_SURFACE_CONTAINER,
            corner_radius=14,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        self.custom_settings_frame.pack(fill="x", padx=20, pady=(0, 14))
        self.custom_settings_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        # Codec
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Codec:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=0, padx=8, pady=(8, 2), sticky="w")
        
        self.codec_var = ctk.StringVar(value="aac")
        self.codec_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["aac", "libmp3lame", "pcm_s16le"],
            variable=self.codec_var,
            height=30,
            corner_radius=10,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
        )
        self.codec_menu.grid(row=1, column=0, padx=8, pady=(0, 10), sticky="ew")

        # Channels
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Kanäle:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=1, padx=8, pady=(8, 2), sticky="w")
        
        self.channels_var = ctk.StringVar(value="Mono (1)")
        self.channels_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["Mono (1)", "Stereo (2)"],
            variable=self.channels_var,
            height=30,
            corner_radius=10,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
        )
        self.channels_menu.grid(row=1, column=1, padx=8, pady=(0, 10), sticky="ew")

        # Sample Rate
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Abtastrate:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=2, padx=8, pady=(8, 2), sticky="w")
        
        self.rate_var = ctk.StringVar(value="44.100 Hz")
        self.rate_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["44.100 Hz", "48.000 Hz", "24.000 Hz"],
            variable=self.rate_var,
            height=30,
            corner_radius=10,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
        )
        self.rate_menu.grid(row=1, column=2, padx=8, pady=(0, 10), sticky="ew")

        # Bitrate
        ctk.CTkLabel(
            self.custom_settings_frame,
            text="Datenrate:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).grid(row=0, column=3, padx=8, pady=(8, 2), sticky="w")
        
        self.bitrate_var = ctk.StringVar(value="64 kbit/s")
        self.bitrate_menu = ctk.CTkOptionMenu(
            self.custom_settings_frame,
            values=["64 kbit/s", "96 kbit/s", "128 kbit/s", "192 kbit/s", "320 kbit/s"],
            variable=self.bitrate_var,
            height=30,
            corner_radius=10,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
        )
        self.bitrate_menu.grid(row=1, column=3, padx=8, pady=(0, 10), sticky="ew")

        # FastStart Checkbox
        self.faststart_var = ctk.BooleanVar(value=True)
        self.faststart_check = ctk.CTkCheckBox(
            self.custom_settings_frame,
            text="+faststart (Web-Streaming)",
            variable=self.faststart_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT,
            fg_color=M3_PRIMARY[0],
            hover_color=M3_PRIMARY_HOVER[0]
        )
        self.faststart_check.grid(row=1, column=4, padx=8, pady=(0, 10), sticky="w")

        # ------------------ 6. Action Container (Permanent Slot) ------------------
        self.action_container = ctk.CTkFrame(main_content, fg_color="transparent")
        self.action_container.pack(fill="x", pady=(0, 0))

        # 6A: Single-Text Action Card
        self.single_action_card = ctk.CTkFrame(
            self.action_container,
            corner_radius=20,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        self.single_action_card.pack(fill="x", pady=(0, 12))

        self.generate_btn = ctk.CTkButton(
            self.single_action_card,
            text="⚡ Sprache generieren & konvertieren",
            command=self._start_generation_thread,
            height=54,
            corner_radius=20,
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            fg_color=M3_CTA,
            hover_color=M3_CTA_HOVER,
            text_color="#FFFFFF",
            text_color_disabled="#FFFFFF"
        )
        self.generate_btn.pack(fill="x", padx=20, pady=(16, 10))

        self.progress_bar = ctk.CTkProgressBar(
            self.single_action_card,
            height=10,
            corner_radius=5,
            progress_color=M3_PRIMARY[0],
            fg_color=M3_SURFACE_CONTAINER
        )
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 10))
        self.progress_bar.set(0.0)
        self.progress_bar.pack_forget()

        self.status_lbl = ctk.CTkLabel(
            self.single_action_card,
            text="Bereit zur Sprachgenerierung.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        )
        self.status_lbl.pack(padx=20, pady=(0, 14))

        # 6B: Batch Action Card (Instantiated, packed only in batch mode)
        self.batch_action_card = ctk.CTkFrame(
            self.action_container,
            corner_radius=20,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )

        batch_action_btn_row = ctk.CTkFrame(self.batch_action_card, fg_color="transparent")
        batch_action_btn_row.pack(fill="x", padx=20, pady=(16, 10))

        self.batch_start_btn = ctk.CTkButton(
            batch_action_btn_row,
            text="⚡ Alle Dateien in Warteschlange generieren",
            command=self._batch_start_processing,
            height=50,
            corner_radius=20,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            fg_color=M3_CTA,
            hover_color=M3_CTA_HOVER,
            text_color="#FFFFFF"
        )
        self.batch_start_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.batch_cancel_btn = ctk.CTkButton(
            batch_action_btn_row,
            text="⏹ Abbrechen",
            command=self._batch_cancel,
            height=50,
            width=120,
            corner_radius=20,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color="transparent",
            hover_color=M3_ERROR_HOVER,
            text_color=M3_ERROR,
            border_width=1.5,
            border_color=M3_ERROR_CONTAINER,
            state="disabled"
        )
        self.batch_cancel_btn.pack(side="right")

        self.batch_progress_bar = ctk.CTkProgressBar(
            self.batch_action_card,
            height=10,
            corner_radius=5,
            progress_color=M3_PRIMARY[0],
            fg_color=M3_SURFACE_CONTAINER
        )
        self.batch_progress_bar.pack(fill="x", padx=20, pady=(0, 10))
        self.batch_progress_bar.set(0.0)
        self.batch_progress_bar.pack_forget()

        self.batch_status_lbl = ctk.CTkLabel(
            self.batch_action_card,
            text="Warteschlange bereit.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        )
        self.batch_status_lbl.pack(padx=20, pady=(0, 14))

        # ------------------ 7. Permanent Audio Player & Export Card (Bottom) ------------------
        player_card = ctk.CTkFrame(
            main_content,
            corner_radius=20,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        player_card.pack(fill="x", pady=(0, 12))
        player_card.grid_columnconfigure(1, weight=1)

        player_header = ctk.CTkLabel(
            player_card,
            text="🔊 Integrierter Audio-Player & Export",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        player_header.grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(16, 10))

        # Row 1: Visual Audio Waveform Canvas Display
        waveform_container = ctk.CTkFrame(
            player_card,
            fg_color=M3_SURFACE_CONTAINER,
            corner_radius=16,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        waveform_container.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 12))
        waveform_container.grid_columnconfigure(0, weight=1)

        self.waveform_view = WaveformCanvas(
            waveform_container,
            on_seek_callback=self._on_waveform_seek,
            height=56
        )
        self.waveform_view.grid(row=0, column=0, sticky="ew", padx=6, pady=6)

        # Row 2: Controls row
        controls_frame = ctk.CTkFrame(player_card, fg_color="transparent")
        controls_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=20, pady=0)
        controls_frame.grid_columnconfigure(2, weight=1)

        self.play_btn = ctk.CTkButton(
            controls_frame,
            text="▶ Abspielen",
            command=self._toggle_playback,
            width=130,
            height=42,
            corner_radius=21,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            state="disabled",
            fg_color=M3_PRIMARY,
            hover_color=M3_PRIMARY_HOVER,
            text_color=("#FFFFFF", "#00201C"),
            text_color_disabled=COLOR_MUTED_TEXT
        )
        self.play_btn.grid(row=0, column=0, padx=(0, 10))

        self.stop_btn = ctk.CTkButton(
            controls_frame,
            text="■ Stopp",
            command=self._stop_playback,
            width=100,
            height=42,
            corner_radius=21,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            state="disabled",
            fg_color="transparent",
            hover_color=M3_ERROR_HOVER,
            text_color=M3_ERROR,
            text_color_disabled=COLOR_MUTED_TEXT,
            border_width=1.5,
            border_color=M3_ERROR_CONTAINER
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
            button_color=M3_CTA,
            button_hover_color=M3_CTA_HOVER,
            progress_color=M3_PRIMARY[0]
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
            button_color=M3_PRIMARY[0],
            button_hover_color=M3_PRIMARY_HOVER[0],
            progress_color=M3_PRIMARY[0]
        )
        self.volume_slider.set(0.8)
        self.volume_slider.grid(row=0, column=5, padx=(0, 0))

        # Row 3: Export Button (M3 Tonal Stadium)
        self.export_btn = ctk.CTkButton(
            player_card,
            text="💾 Audiodatei speichern unter...",
            command=self._export_audio,
            height=44,
            corner_radius=22,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color=M3_SECONDARY_CONTAINER,
            hover_color=("#BDDFD8", "#24403C"),
            text_color=M3_ON_SECONDARY_CONTAINER,
            text_color_disabled=COLOR_MUTED_TEXT,
            border_width=0,
            state="disabled"
        )
        self.export_btn.grid(row=3, column=0, columnspan=3, sticky="ew", padx=20, pady=(14, 18))

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

    # ------------------ Collapsible Audio-Tags Panel ------------------

    def _toggle_tags_panel(self):
        """Toggle collapsible Audio-Tags panel under main text field."""
        if self.is_tags_collapsed:
            self.tag_buttons_frame.pack(fill="x", anchor="w", pady=(6, 0))
            self.tag_toggle_btn.configure(text="▴ Tags verbergen")
            self.is_tags_collapsed = False
        else:
            self.tag_buttons_frame.pack_forget()
            self.tag_toggle_btn.configure(text="▾ Audio-Tags anzeigen")
            self.is_tags_collapsed = True

    # ------------------ Collapsible Batch Multi-Language Panel ------------------

    def _toggle_batch_lang_panel(self):
        """Toggle collapsible multi-language target selection panel in batch mode."""
        if self.is_batch_lang_collapsed:
            self.batch_lang_body_frame.pack(fill="x", pady=(6, 0))
            self.batch_lang_toggle_btn.configure(text="▴ Zuklappen")
            self.is_batch_lang_collapsed = False
        else:
            self.batch_lang_body_frame.pack_forget()
            self.batch_lang_toggle_btn.configure(text="▾ 31 Sprachen anpassen")
            self.is_batch_lang_collapsed = True

    def _set_batch_langs_preset(self, preset_type: str):
        top5 = {"de", "en", "es", "fr", "it"}
        for code, var in self.batch_lang_vars.items():
            if preset_type == "de_only":
                var.set(code == "de")
            elif preset_type == "top5":
                var.set(code in top5)
            elif preset_type == "all":
                var.set(True)
            elif preset_type == "none":
                var.set(False)
        self._update_batch_lang_summary()

    def _update_batch_lang_summary(self):
        selected_codes = [code for code, var in self.batch_lang_vars.items() if var.get()]
        count = len(selected_codes)
        if count == 0:
            txt = "Keine Zielsprache gewählt (Originalsprache)"
            color = COLOR_MUTED_TEXT
        elif count == 1:
            name = next((l["name"] for l in SUPPORTED_LANGUAGES if l["id"] == selected_codes[0]), selected_codes[0])
            txt = f"1 Sprache: {name}"
            color = M3_PRIMARY
        elif count <= 4:
            items = []
            for c in selected_codes:
                n = next((l["name"] for l in SUPPORTED_LANGUAGES if l["id"] == c), c)
                flag = n.split(" ")[0]
                items.append(f"{flag} {c.upper()}")
            txt = f"{count} Sprachen: {', '.join(items)}"
            color = M3_PRIMARY
        else:
            txt = f"{count} von 31 Sprachen aktiv"
            color = M3_PRIMARY

        if hasattr(self, "batch_lang_summary_lbl"):
            self.batch_lang_summary_lbl.configure(text=txt, text_color=color)

    # ------------------ Translation (Single Text) ------------------

    def _translate_single_text(self):
        """Translates current text in text_input into the selected target language."""
        text = self.text_input.get("0.0", "end").strip()
        if not text:
            messagebox.showwarning("Hinweis", "Bitte gib zuerst einen Text ein, der übersetzt werden soll.")
            return

        selected_lang_name = self.lang_var.get()
        target_lang_id = "auto"
        for l in SUPPORTED_LANGUAGES:
            if l["name"] == selected_lang_name:
                target_lang_id = l["id"]
                break

        if target_lang_id == "auto":
            messagebox.showinfo("Sprachauswahl", "Bitte wähle im Bereich '🌐 Sprache' eine konkrete Zielsprache aus (z. B. Englisch, Französisch, Spanisch etc.).")
            return

        self.translate_single_btn.configure(state="disabled", text="⏳ Übersetze...")
        self.status_lbl.configure(text=f"Übersetze Text nach {selected_lang_name} (Gemini 3.8 Flash)...", text_color="#38BDF8")

        def run_trans():
            try:
                translated = self.translation_service.translate_text(text, target_lang_id=target_lang_id)
                self.after(0, self._on_single_translation_done, translated, selected_lang_name)
            except Exception as e:
                self.after(0, self._on_single_translation_error, str(e))

        threading.Thread(target=run_trans, daemon=True).start()

    def _on_single_translation_done(self, translated_text: str, target_lang_name: str):
        self.translate_single_btn.configure(state="normal", text="🌐 In Zielsprache übersetzen")
        self.text_input.delete("0.0", "end")
        self.text_input.insert("0.0", translated_text)
        self._update_counters()
        self.status_lbl.configure(text=f"✅ Erfolgreich nach {target_lang_name} übersetzt!", text_color="#10B981")
        messagebox.showinfo("Übersetzung fertig", f"Der Text wurde erfolgreich nach {target_lang_name} übersetzt!\nAlle Regieanweisungen und Audio-Tags blieben erhalten.")

    def _on_single_translation_error(self, err_msg: str):
        self.translate_single_btn.configure(state="normal", text="🌐 In Zielsprache übersetzen")
        self.status_lbl.configure(text=f"❌ Übersetzungsfehler: {err_msg}", text_color="#EF4444")
        messagebox.showerror("Übersetzungsfehler", f"Fehler bei der Übersetzung:\n{err_msg}")

    # ------------------ System-Prompt & Style Panel with Custom Preset Saving ------------------

    def _toggle_style_panel(self):
        """Toggle collapsible Style / System-Prompt panel."""
        if self.is_style_collapsed:
            self.style_body_frame.pack(fill="x", padx=18, pady=(0, 12))
            self.style_toggle_btn.configure(text="▴ Zuklappen")
            self.is_style_collapsed = False
        else:
            self.style_body_frame.pack_forget()
            self.style_toggle_btn.configure(text="▾ Stil anpassen")
            self.is_style_collapsed = True

    def _refresh_style_presets(self, select_name: Optional[str] = None):
        """Reloads built-in suggestions and user custom styles into the OptionMenu."""
        custom_styles = load_custom_styles()
        built_in_names = [p[0] for p in STYLE_SUGGESTIONS]
        
        all_names = list(built_in_names)
        if custom_styles:
            for c_name in sorted(custom_styles.keys()):
                all_names.append(f"⭐ {c_name}")

        self.style_preset_menu.configure(values=all_names)
        if select_name and select_name in all_names:
            self.style_preset_var.set(select_name)
        elif not self.style_preset_var.get() or self.style_preset_var.get() not in all_names:
            self.style_preset_var.set(all_names[0])

    def _on_style_preset_changed(self, choice: str):
        # Check built-in suggestions
        for name, directive in STYLE_SUGGESTIONS:
            if name == choice:
                self.style_input.delete("0.0", "end")
                if directive:
                    self.style_input.insert("0.0", directive)
                return

        # Check user-saved custom styles
        if choice.startswith("⭐ "):
            raw_name = choice[2:]
            custom_styles = load_custom_styles()
            if raw_name in custom_styles:
                self.style_input.delete("0.0", "end")
                self.style_input.insert("0.0", custom_styles[raw_name])

    def _save_current_style_preset(self):
        """Saves current text in style_input as a custom reusable preset."""
        directive = self.style_input.get("0.0", "end").strip()
        if not directive:
            messagebox.showwarning("Hinweis", "Bitte gib zuerst eine Regieanweisung im Textfeld ein.")
            return

        dialog = ctk.CTkInputDialog(
            text="Name für die neue Stil-Vorlage eingeben:\n(z. B. 'Dokumentation Ruhig', 'Podcast Host', 'Märchenerzähler')",
            title="Stil-Vorlage speichern"
        )
        name = dialog.get_input()
        if not name or not name.strip():
            return
        
        name = name.strip()
        save_custom_style(name, directive)
        self._refresh_style_presets(select_name=f"⭐ {name}")
        messagebox.showinfo("Gespeichert", f"Die Vorlage '{name}' wurde erfolgreich gespeichert und zur Auswahl hinzugefügt!")

    def _delete_current_style_preset(self):
        """Deletes currently selected user preset."""
        current_choice = self.style_preset_var.get()
        if not current_choice.startswith("⭐ "):
            messagebox.showinfo("Hinweis", "Nur selbst gespeicherte Vorlagen (mit ⭐ gekennzeichnet) können gelöscht werden.")
            return

        raw_name = current_choice[2:]
        if messagebox.askyesno("Vorlage löschen", f"Möchtest du die Vorlage '{raw_name}' wirklich löschen?"):
            delete_custom_style(raw_name)
            self._refresh_style_presets()
            self._clear_style()
            messagebox.showinfo("Gelöscht", f"Die Vorlage '{raw_name}' wurde gelöscht.")

    def _clear_style(self):
        self.style_preset_var.set(STYLE_SUGGESTIONS[0][0])
        self.style_input.delete("0.0", "end")

    def _get_current_system_prompt(self) -> Optional[str]:
        prompt = self.style_input.get("0.0", "end").strip()
        return prompt if prompt else None

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
                fg_color=M3_SURFACE,
                corner_radius=12,
                border_width=1,
                border_color=M3_OUTLINE_VARIANT
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
            status_color = COLOR_MUTED_TEXT
            if "Fertig" in item.status:
                status_color = "#10B981"
            elif "Fehler" in item.status:
                status_color = M3_ERROR
            elif "generiert" in item.status or "Konvertiere" in item.status or "Übersetze" in item.status:
                status_color = M3_PRIMARY

            status_lbl = ctk.CTkLabel(
                item_row,
                text=item.status,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                text_color=status_color
            )
            status_lbl.grid(row=0, column=2, padx=10, pady=6)

            # Play Button for completed items (M3 Tonal Pill)
            if item.output_audio and item.output_audio.exists():
                play_item_btn = ctk.CTkButton(
                    item_row,
                    text="▶ Anhören",
                    command=lambda path=item.output_audio: self._play_batch_item_audio(path),
                    width=86,
                    height=28,
                    corner_radius=14,
                    font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                    fg_color=M3_PRIMARY_CONTAINER,
                    hover_color=("#B6E4DA", "#00645A"),
                    text_color=M3_ON_PRIMARY_CONTAINER,
                    border_width=0
                )
                play_item_btn.grid(row=0, column=3, padx=6, pady=6)

            # Remove button (M3 Destructive Outlined)
            if not self.batch_processor.is_running:
                del_btn = ctk.CTkButton(
                    item_row,
                    text="✕",
                    command=lambda it_id=item.id: self._remove_batch_item(it_id),
                    width=28,
                    height=28,
                    corner_radius=14,
                    font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                    fg_color="transparent",
                    hover_color=M3_ERROR_HOVER,
                    text_color=M3_ERROR,
                    border_width=1,
                    border_color=M3_ERROR_CONTAINER
                )
                del_btn.grid(row=0, column=4, padx=(0, 8), pady=6)

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
        if hasattr(self, "waveform_view") and self.player._playback_file and self.player._playback_file.exists():
            self.waveform_view.load_audio(self.player._playback_file)
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

        # Collect selected languages from multi-lang checkboxes
        target_langs = [code for code, var in self.batch_lang_vars.items() if var.get()]
        if not target_langs:
            target_langs = [lang_id if lang_id != "auto" else "de"]

        encoding_settings = self._get_current_encoding_settings()
        system_prompt = self._get_current_system_prompt()

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
            system_prompt=system_prompt,
            target_languages=target_langs,
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
        messagebox.showinfo("Batch abgeschlossen", f"Stapelverarbeitung abgeschlossen!\n{success_count} von {len(items)} Dateien wurden erfolgreich verarbeitet und in '{self.batch_output_dir.name}' gespeichert.")

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
        self.translation_service.set_api_key(new_key)
        self.key_status_btn.configure(text=self._get_key_status_text())
        messagebox.showinfo("Erfolg", "API-Key wurde erfolgreich gespeichert!")

    def _toggle_theme(self):
        mode = ctk.get_appearance_mode()
        new_mode = "Light" if mode == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)
        if hasattr(self, "waveform_view"):
            self.waveform_view.redraw()
        if hasattr(self, "mode_segmented") and hasattr(self.mode_segmented, "_update_button_styles"):
            self.mode_segmented._update_button_styles()

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

            # Automatic translation if checkbox checked and language is not auto or de
            if self.auto_translate_var.get() and lang_id not in ("auto", "de"):
                self._update_generation_progress(0.08, f"Übersetze Text automatisch nach {selected_lang_name}...")
                text = self.translation_service.translate_text(text, target_lang_id=lang_id)

            system_prompt = self._get_current_system_prompt()
            
            # Generate speech with chunking & progress updates
            raw_wav_path = self.tts_service.generate_speech(
                text=text,
                voice_name=voice_choice,
                model=model_id,
                language=lang_id,
                system_prompt=system_prompt,
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

        # Load audio into waveform display
        if hasattr(self, "waveform_view"):
            if self.current_generated_wav and self.current_generated_wav.exists():
                self.waveform_view.load_audio(self.current_generated_wav)
            elif self.player._playback_file and self.player._playback_file.exists():
                self.waveform_view.load_audio(self.player._playback_file)

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
            if hasattr(self, "waveform_view"):
                self.waveform_view.set_progress(val)
        self.is_user_scrubbing = False

    def _on_waveform_seek(self, pct: float):
        self.timeline_slider.set(pct)
        total = self.player.get_duration()
        if total > 0:
            target_sec = pct * total
            self.player.seek(target_sec)
            self.time_lbl.configure(text=f"{self._format_time(target_sec)} / {self._format_time(total)}")

    def _on_seek_change(self, value):
        total = self.player.get_duration()
        if total > 0:
            curr = float(value) * total
            self.time_lbl.configure(text=f"{self._format_time(curr)} / {self._format_time(total)}")
            if hasattr(self, "waveform_view") and not getattr(self.waveform_view, "is_scrubbing", False):
                self.waveform_view.set_progress(float(value))
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
        if hasattr(self, "waveform_view"):
            self.waveform_view.set_progress(0.0)
        self.time_lbl.configure(text=f"00:00 / {self._format_time(self.player.get_duration())}")

    def _on_volume_changed(self, value):
        self.player.set_volume(float(value))

    def _setup_player_timer(self):
        """Update playback slider, waveform, and time display periodically when not user scrubbing."""
        if not self.is_user_scrubbing and not getattr(self.waveform_view, "is_scrubbing", False):
            if self.player.is_playing() or self.player.is_paused():
                curr = self.player.get_position()
                total = self.player.get_duration()
                if total > 0:
                    pct = curr / total
                    self.timeline_slider.set(pct)
                    if hasattr(self, "waveform_view"):
                        self.waveform_view.set_progress(pct)
                self.time_lbl.configure(text=f"{self._format_time(curr)} / {self._format_time(total)}")
                
                if not self.player.is_playing() and not self.player.is_paused():
                    self.play_btn.configure(text="▶ Abspielen")
                    self.timeline_slider.set(0.0)
                    if hasattr(self, "waveform_view"):
                        self.waveform_view.set_progress(0.0)
        
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
