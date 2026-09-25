"""
Modern, high-contrast GUI for Gemini TTS Studio
Includes Single-Text Mode with Document Importer and Full Batch / Document Queue Processing.
Features Global System-Prompt / Tone Directives with Custom Preset Saving, 32 Languages, and Automatic Translation.
Rock-solid stable layout hierarchy where no elements jump or shift when switching tabs.
"""

import base64
import math
import os
import struct
import subprocess
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

import customtkinter as ctk
from tkinter import filedialog, messagebox

from .config import (
    APP_VERSION,
    GITHUB_REPO,
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
    load_custom_voices,
    save_custom_voice,
    delete_custom_voice,
    get_all_voices,
)
from .tts_service import GeminiTTSService
from .audio_converter import convert_audio
from .player import AudioPlayer
from .document_parser import extract_text_from_file, split_into_chapters
from .batch_processor import BatchProcessor, BatchItem
from .translation_service import TranslationService
from .updater import UpdateService, format_release_notes


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
M3_ON_PRIMARY = ("#FFFFFF", "#003731")
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
        self.parent_app = parent
        self.title("Gemini API-Key & App-Status")
        self.geometry("540x300")
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
        lbl.pack(pady=(16, 4))

        desc = ctk.CTkLabel(
            frame,
            text="Trage hier deinen API-Key aus Google AI Studio ein.\nDer Key wird sicher in deiner lokalen .env Datei gespeichert.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT,
            justify="center"
        )
        desc.pack(pady=(0, 10))

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
        self.key_entry.pack(pady=4)
        self.key_entry.insert(0, get_api_key())

        # Version & Update check row
        info_row = ctk.CTkFrame(frame, fg_color="transparent")
        info_row.pack(fill="x", padx=30, pady=(6, 8))

        ver_lbl = ctk.CTkLabel(
            info_row,
            text=f"Version {APP_VERSION}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        )
        ver_lbl.pack(side="left")

        check_update_btn = ctk.CTkButton(
            info_row,
            text="🔄 Auf Updates prüfen",
            command=self._check_updates,
            height=28,
            corner_radius=14,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=M3_PRIMARY,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        check_update_btn.pack(side="right")

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=(10, 10))

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

    def _check_updates(self):
        if hasattr(self.parent_app, "_check_for_updates_manual"):
            self.parent_app._check_for_updates_manual()

    def _save(self):
        new_key = self.key_entry.get().strip()
        if not new_key:
            messagebox.showwarning("Hinweis", "Bitte gib einen gültigen API-Key ein.")
            return
        save_api_key(new_key)
        if self.on_save_callback:
            self.on_save_callback(new_key)
        self.destroy()


class UpdateDialog(ctk.CTkToplevel):
    """Modern Material 3 Dialog for reviewing release notes and applying app updates."""

    def __init__(self, parent, update_info: Dict[str, Any], update_service: UpdateService):
        super().__init__(parent)
        self.parent_app = parent
        self.update_info = update_info
        self.update_service = update_service
        self.is_downloading = False

        self.title("Gemini TTS Studio Update")
        self.geometry("620x480")
        self.resizable(False, False)

        frame = ctk.CTkFrame(
            self,
            corner_radius=18,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        header_row = ctk.CTkFrame(frame, fg_color="transparent")
        header_row.pack(fill="x", padx=20, pady=(18, 6))

        title_lbl = ctk.CTkLabel(
            header_row,
            text=f"✨ Update verfügbar: {update_info.get('latest_version', '')}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        title_lbl.pack(side="left")

        current_ver_lbl = ctk.CTkLabel(
            header_row,
            text=f"Installiert: v{APP_VERSION}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_MUTED_TEXT
        )
        current_ver_lbl.pack(side="right")

        desc_lbl = ctk.CTkLabel(
            frame,
            text="Eine neue Version von Gemini TTS Studio ist bereit zur Installation.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT,
            anchor="w"
        )
        desc_lbl.pack(fill="x", padx=20, pady=(0, 10))

        # Release Notes Box
        ctk.CTkLabel(
            frame,
            text="Neuerungen & Änderungen:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=M3_PRIMARY,
            anchor="w"
        ).pack(fill="x", padx=20, pady=(0, 4))

        notes_box = ctk.CTkTextbox(
            frame,
            height=150,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            wrap="word",
            corner_radius=12,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT,
            fg_color=M3_SURFACE_CONTAINER,
            text_color=COLOR_PRIMARY_TEXT
        )
        notes_box.pack(fill="x", padx=20, pady=(0, 10))
        raw_notes = update_info.get("release_notes") or update_info.get("release_name") or ""
        notes_content = format_release_notes(raw_notes)
        notes_box.insert("0.0", notes_content)
        notes_box.configure(state="disabled")

        # Progress row
        self.progress_bar = ctk.CTkProgressBar(
            frame,
            height=8,
            corner_radius=4,
            progress_color=M3_PRIMARY[0],
            fg_color=M3_SURFACE_CONTAINER
        )
        self.progress_bar.set(0.0)

        self.status_lbl = ctk.CTkLabel(
            frame,
            text="Bereit zum Aktualisieren. Deine Einstellungen und der API-Key bleiben erhalten.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT,
            anchor="w"
        )
        self.status_lbl.pack(fill="x", padx=20, pady=(0, 8))

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4, 14))

        self.update_btn = ctk.CTkButton(
            btn_row,
            text="🚀 Jetzt aktualisieren & neu starten",
            command=self._start_update,
            height=38,
            corner_radius=19,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=M3_PRIMARY,
            hover_color=M3_PRIMARY_HOVER,
            text_color=("#FFFFFF", "#00201C")
        )
        self.update_btn.pack(side="left", padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(
            btn_row,
            text="Später",
            command=self.destroy,
            height=38,
            corner_radius=19,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=COLOR_MUTED_TEXT,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        self.cancel_btn.pack(side="left")

        self.transient(parent)
        self.grab_set()

    def _start_update(self):
        if self.is_downloading:
            return
        self.is_downloading = True
        self.update_btn.configure(state="disabled", text="⏳ Lade Update herunter...")
        self.cancel_btn.configure(state="disabled")
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 8))
        self.progress_bar.set(0.05)

        def run_download():
            def on_progress(fraction, status_str):
                self.after(0, lambda: self._update_progress(fraction, status_str))

            download_url = self.update_info.get("download_url", "")
            asset_url = self.update_info.get("asset_url", "")
            dest_file = self.update_service.download_update(
                download_url,
                asset_url=asset_url,
                progress_callback=on_progress
            )

            if not dest_file or not dest_file.exists():
                self.after(0, self._on_download_failed)
                return

            self.after(0, lambda: self._on_download_success(dest_file))

        threading.Thread(target=run_download, daemon=True).start()

    def _update_progress(self, fraction, status_str):
        self.progress_bar.set(fraction)
        self.status_lbl.configure(text=f"Lade herunter: {status_str}...")

    def _on_download_failed(self):
        self.is_downloading = False
        self.progress_bar.pack_forget()
        self.update_btn.configure(state="normal", text="🚀 Erneut versuchen")
        self.cancel_btn.configure(state="normal")
        self.status_lbl.configure(text="Fehler beim Herunterladen des Updates.", text_color=M3_ERROR)
        messagebox.showerror("Update fehlgeschlagen", "Das Update konnte nicht heruntergeladen werden. Bitte prüfe deine Internetverbindung.")

    def _on_download_success(self, downloaded_exe: Path):
        self.status_lbl.configure(text="Download erfolgreich! Starte Anwendung neu...", text_color="#10B981")
        self.progress_bar.set(1.0)
        self.after(800, lambda: self.update_service.apply_update_and_restart(downloaded_exe))


class VoiceStudioDialog(ctk.CTkToplevel):
    """
    Modern Google Material 3 Voice Studio Dialog for Gemini 3.8.
    Supports Voice Design (natural-language prompting), Voice Replication (reference + consent audio),
    and custom Voice ID management.
    """

    def __init__(self, parent, tts_service: GeminiTTSService, on_voice_selected_callback: Callable[[str], None]):
        super().__init__(parent)
        self.parent_app = parent
        self.tts_service = tts_service
        self.on_voice_selected_callback = on_voice_selected_callback

        self.title("Gemini 3.8 Voice Studio & Stimm-Klonen")
        self.geometry("780x760")
        self.minsize(720, 640)

        self.audio_player = AudioPlayer()
        self.current_preview_file: Optional[Path] = None
        self.last_created_voice: Optional[Dict[str, Any]] = None

        self.ref_audio_path: Optional[Path] = None
        self.consent_audio_path: Optional[Path] = None

        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.transient(parent)
        self.grab_set()

    def _on_close(self):
        try:
            self.audio_player.stop()
        except Exception:
            pass
        self.destroy()

    def _build_ui(self):
        container = ctk.CTkFrame(
            self,
            corner_radius=18,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        container.pack(padx=16, pady=16, fill="both", expand=True)

        # Header
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 4))

        title_lbl = ctk.CTkLabel(
            header,
            text="🎨 Gemini 3.8 Voice Studio & Stimm-Klonen",
            font=ctk.CTkFont(family=FONT_FAMILY, size=20, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        title_lbl.pack(side="left")

        ver_lbl = ctk.CTkLabel(
            header,
            text="Gemini 3.8 Flash Audio",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=M3_PRIMARY
        )
        ver_lbl.pack(side="right")

        desc_lbl = ctk.CTkLabel(
            container,
            text="Erschaffe maßgeschneiderte Stimmen aus natürlicher Sprache (Voice Design) oder binde geklonte Profile ein.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT,
            anchor="w"
        )
        desc_lbl.pack(fill="x", padx=20, pady=(0, 10))

        # Tab Navigation Bar (Robust Material 3 segmented tabs)
        nav_bar = ctk.CTkFrame(container, fg_color=M3_SURFACE_CONTAINER, corner_radius=14, height=44)
        nav_bar.pack(fill="x", padx=16, pady=(0, 12))

        self.tab_buttons: Dict[str, ctk.CTkButton] = {}
        self.tab_frames: Dict[str, ctk.CTkFrame] = {}

        tabs_info = [
            ("design", "🎨 Voice Design (Prompt)"),
            ("replicate", "🎙️ Voice Replication (Klon)"),
            ("manage", "🔑 Meine Stimmen & IDs")
        ]

        for tab_id, label in tabs_info:
            btn = ctk.CTkButton(
                nav_bar,
                text=label,
                command=lambda t=tab_id: self._switch_tab(t),
                height=36,
                corner_radius=10,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                fg_color="transparent",
                hover_color=M3_SURFACE_CONTAINER_HIGH,
                text_color=COLOR_MUTED_TEXT
            )
            btn.pack(side="left", padx=4, pady=4, fill="x", expand=True)
            self.tab_buttons[tab_id] = btn

        # Tab Content Container
        self.tab_content_area = ctk.CTkFrame(container, fg_color=M3_SURFACE_CONTAINER, corner_radius=14)
        self.tab_content_area.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        self.tab_design = ctk.CTkFrame(self.tab_content_area, fg_color="transparent")
        self.tab_replicate = ctk.CTkFrame(self.tab_content_area, fg_color="transparent")
        self.tab_manage = ctk.CTkFrame(self.tab_content_area, fg_color="transparent")

        self.tab_frames["design"] = self.tab_design
        self.tab_frames["replicate"] = self.tab_replicate
        self.tab_frames["manage"] = self.tab_manage

        self._build_tab_design()
        self._build_tab_replicate()
        self._build_tab_manage()

        self._switch_tab("design")

    def _switch_tab(self, active_tab: str):
        for t_id, frame in self.tab_frames.items():
            if t_id == active_tab:
                frame.pack(fill="both", expand=True, padx=8, pady=8)
            else:
                frame.pack_forget()

        for t_id, btn in self.tab_buttons.items():
            if t_id == active_tab:
                btn.configure(
                    fg_color=M3_PRIMARY,
                    hover_color=M3_PRIMARY_HOVER,
                    text_color=("#FFFFFF", "#00201C")
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    hover_color=M3_SURFACE_CONTAINER_HIGH,
                    text_color=COLOR_MUTED_TEXT
                )

    # =========================================================================
    # TAB 1: VOICE DESIGN (PROMPT-TO-VOICE)
    # =========================================================================
    def _build_tab_design(self):
        info_card = ctk.CTkFrame(
            self.tab_design,
            corner_radius=10,
            fg_color=("#E6F4EA", "#10281F"),
            border_width=1,
            border_color=("#A8DAB5", "#1B4D3E")
        )
        info_card.pack(fill="x", padx=12, pady=(8, 10))

        ctk.CTkLabel(
            info_card,
            text="✨ Weltweit & in Deutschland voll verfügbar: Beschreibe eine Stimme in Alltagssprache. Gemini 3.8 erzeugt daraus ein hochauflösendes, dauerhaftes Stimm-Profil ohne Audioaufnahmen.",
            wraplength=660,
            justify="left",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=("#137333", "#81C995")
        ).pack(padx=12, pady=8, anchor="w")

        # Form fields
        form_frame = ctk.CTkFrame(self.tab_design, fg_color="transparent")
        form_frame.pack(fill="x", padx=12, pady=(0, 8))

        # Row 1: Name, Gender, Language
        row1 = ctk.CTkFrame(form_frame, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))

        name_box = ctk.CTkFrame(row1, fg_color="transparent")
        name_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(name_box, text="Name der Stimme:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", pady=(0, 4))
        self.vd_name_entry = ctk.CTkEntry(
            name_box,
            placeholder_text="z. B. Sophie - Hörbuch-Erzählerin",
            height=36,
            corner_radius=10,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE,
            border_color=M3_OUTLINE_VARIANT
        )
        self.vd_name_entry.pack(fill="x")

        gender_box = ctk.CTkFrame(row1, fg_color="transparent")
        gender_box.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(gender_box, text="Geschlecht:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", pady=(0, 4))
        self.vd_gender_menu = ctk.CTkOptionMenu(
            gender_box,
            values=["Weiblich (female)", "Männlich (male)"],
            height=36,
            width=150,
            corner_radius=10,
            fg_color=M3_SURFACE,
            button_color=("#D9E3E0", "#243834"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.vd_gender_menu.pack()

        lang_box = ctk.CTkFrame(row1, fg_color="transparent")
        lang_box.pack(side="left")
        ctk.CTkLabel(lang_box, text="Basissprache:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", pady=(0, 4))
        self.vd_lang_menu = ctk.CTkOptionMenu(
            lang_box,
            values=["🇩🇪 Deutsch (de-DE)", "🇺🇸 Englisch US (en-US)", "🇬🇧 Englisch UK (en-GB)", "🇫🇷 Französisch (fr-FR)", "🇪🇸 Spanisch (es-ES)", "🇮🇹 Italienisch (it-IT)"],
            height=36,
            width=160,
            corner_radius=10,
            fg_color=M3_SURFACE,
            button_color=("#D9E3E0", "#243834"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.vd_lang_menu.pack()

        # Row 2: Schnellvorlage
        row2 = ctk.CTkFrame(form_frame, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(row2, text="📋 Schnellvorlage wählen:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(side="left", padx=(0, 10))
        self.vd_templates = {
            "✨ Eigene Beschreibung (Freitext)": "",
            "📖 Hörbuch-Erzähler (Warm & Sonor)": "Eine warme, sonore und beruhigende männliche Erzählerstimme Mitte 50 mit tiefer Resonanz, getragenem Sprechtempo und exzellenter deutscher Artikulation.",
            "📰 Seriöse Nachrichtensprecherin": "Eine sachliche, präzise und klar artikulierte weibliche Sprecherin Mitte 30 im Stil seriöser Audio-Dokumentationen und Nachrichten.",
            "🎙️ Tech-Podcaster (Dynamisch)": "Eine dynamische, energiegeladene und nahbare Stimme Ende 20, enthusiastisch, freundlich und sympathisch.",
            "🧘 Meditations-Leiterin (Sanft & Beruhigend)": "Eine sehr sanfte, leise, melodische und einfühlsame weibliche Stimme mit beruhigendem Fluss und entspannter Atmung.",
            "🕵️ Krimi- & Hörspiel-Sprecher": "Eine markante, tiefe, leicht rauchige und geheimnisvolle Stimme mit spürbarer Spannung und erzählerischer Dramatik.",
            "🛍️ Moderner Werbesprecher": "Eine frische, sympathische, einladende und überzeugende Stimme für moderne Audio-Spots und Erklärvideos.",
        }
        self.vd_template_menu = ctk.CTkOptionMenu(
            row2,
            values=list(self.vd_templates.keys()),
            command=self._on_template_selected,
            height=30,
            corner_radius=10,
            fg_color=M3_SURFACE,
            button_color=("#D9E3E0", "#243834"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.vd_template_menu.pack(side="left", fill="x", expand=True)

        # Row 3: Stimm-Beschreibung Prompt
        ctk.CTkLabel(
            self.tab_design,
            text="Stimm-Beschreibung (Charakter, Alter, Timbre, Tempo):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", padx=12, pady=(0, 4))

        self.vd_prompt_box = ctk.CTkTextbox(
            self.tab_design,
            height=85,
            corner_radius=10,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT,
            text_color=COLOR_PRIMARY_TEXT
        )
        self.vd_prompt_box.pack(fill="x", padx=12, pady=(0, 10))
        self.vd_prompt_box.insert("0.0", "Eine freundliche, ruhige deutsche Sprecherin mit warmer und klarer Stimme.")

        # Action Button & Status
        action_row = ctk.CTkFrame(self.tab_design, fg_color="transparent")
        action_row.pack(fill="x", padx=12, pady=(0, 10))

        self.vd_btn_create = ctk.CTkButton(
            action_row,
            text="✨ Stimme erschaffen & Probehören",
            command=self._create_prompted_voice,
            height=40,
            corner_radius=20,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=M3_PRIMARY,
            hover_color=M3_PRIMARY_HOVER,
            text_color=M3_ON_PRIMARY
        )
        self.vd_btn_create.pack(side="left")

        self.vd_status_lbl = ctk.CTkLabel(
            action_row,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        )
        self.vd_status_lbl.pack(side="left", padx=14)

        # Result & Preview Box
        self.vd_result_frame = ctk.CTkFrame(
            self.tab_design,
            corner_radius=12,
            fg_color=M3_SURFACE,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        self.vd_result_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.vd_result_info_lbl = ctk.CTkLabel(
            self.vd_result_frame,
            text="Noch keine neue Stimme in dieser Sitzung generiert.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT,
            anchor="w"
        )
        self.vd_result_info_lbl.pack(fill="x", padx=14, pady=(10, 8))

        ctrl_row = ctk.CTkFrame(self.vd_result_frame, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=14, pady=(0, 10))

        self.vd_btn_play = ctk.CTkButton(
            ctrl_row,
            text="▶️ Hörprobe abspielen",
            command=self._play_preview,
            state="disabled",
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_SECONDARY_CONTAINER,
            text_color=M3_ON_SECONDARY_CONTAINER
        )
        self.vd_btn_play.pack(side="left", padx=(0, 8))

        self.vd_btn_stop = ctk.CTkButton(
            ctrl_row,
            text="⏹️ Stopp",
            command=self._stop_preview,
            state="disabled",
            height=34,
            width=70,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="transparent",
            border_width=1,
            border_color=M3_OUTLINE,
            text_color=COLOR_PRIMARY_TEXT
        )
        self.vd_btn_stop.pack(side="left", padx=(0, 14))

        self.vd_btn_save = ctk.CTkButton(
            ctrl_row,
            text="💾 Zu meinen Stimmen hinzufügen & Aktivieren",
            command=self._save_and_activate_created_voice,
            state="disabled",
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_PRIMARY,
            hover_color=M3_PRIMARY_HOVER,
            text_color=M3_ON_PRIMARY
        )
        self.vd_btn_save.pack(side="right")

    def _on_template_selected(self, choice: str):
        prompt = self.vd_templates.get(choice, "")
        if prompt:
            self.vd_prompt_box.delete("0.0", "end")
            self.vd_prompt_box.insert("0.0", prompt)
            suggested_name = choice.split("(")[0].replace("✨", "").replace("📖", "").replace("📰", "").replace("🎙️", "").replace("🧘", "").replace("🕵️", "").replace("🛍️", "").strip()
            self.vd_name_entry.delete(0, "end")
            self.vd_name_entry.insert(0, suggested_name)
            if "weiblich" in prompt.lower() or "nachrichtensprecherin" in prompt.lower() or "leiterin" in prompt.lower():
                self.vd_gender_menu.set("Weiblich (female)")
            else:
                self.vd_gender_menu.set("Männlich (male)")

    def _create_prompted_voice(self):
        name = self.vd_name_entry.get().strip()
        if not name:
            messagebox.showwarning("Fehlender Name", "Bitte gib einen Namen für die Stimme ein.")
            return

        prompt = self.vd_prompt_box.get("0.0", "end").strip()
        if not prompt:
            messagebox.showwarning("Fehlende Beschreibung", "Bitte gib eine Beschreibung der Stimme ein.")
            return

        gender = "female" if "weiblich" in self.vd_gender_menu.get().lower() else "male"
        lang_raw = self.vd_lang_menu.get()
        lang_code = "de-DE"
        if "en-US" in lang_raw:
            lang_code = "en-US"
        elif "en-GB" in lang_raw:
            lang_code = "en-GB"
        elif "fr-FR" in lang_raw:
            lang_code = "fr-FR"
        elif "es-ES" in lang_raw:
            lang_code = "es-ES"
        elif "it-IT" in lang_raw:
            lang_code = "it-IT"

        self.vd_btn_create.configure(state="disabled", text="⏳ Gemini trainiert Stimm-Profil...")
        self.vd_status_lbl.configure(text="Sende Anfrage an Google Cloud... Bitte kurz warten (ca. 20-30 Sek.).", text_color=M3_PRIMARY)

        def run_create():
            try:
                res = self.tts_service.create_prompted_voice(
                    display_name=name,
                    prompt=prompt,
                    gender=gender,
                    language_code=lang_code,
                    model="gemini-3.8-flash-tts"
                )
                self.after(0, lambda: self._on_prompted_voice_success(res, name, prompt, gender, lang_code))
            except Exception as e:
                self.after(0, lambda: self._on_prompted_voice_error(str(e)))

        threading.Thread(target=run_create, daemon=True).start()

    def _on_prompted_voice_success(self, res: dict, name: str, prompt: str, gender: str, lang_code: str):
        self.vd_btn_create.configure(state="normal", text="✨ Stimme erschaffen & Probehören")
        self.vd_status_lbl.configure(text="✅ Stimme erfolgreich erschaffen!", text_color="#10B981")

        voice_id = res.get("id", f"voice_{int(time.time())}")
        self.last_created_voice = {
            "id": voice_id,
            "name": name,
            "desc": f"{prompt[:120]}... (Voice Design)",
            "type": "prompted",
            "gender": gender,
            "language_code": lang_code,
            "created_at": datetime.now().isoformat()
        }

        # Check for sample audio
        sample_audio = res.get("sample_audio", {})
        if sample_audio and "data" in sample_audio:
            try:
                audio_bytes = base64.b64decode(sample_audio["data"])
                preview_file = TEMP_DIR / f"preview_{voice_id}.wav"
                with open(preview_file, "wb") as f:
                    f.write(audio_bytes)
                self.current_preview_file = preview_file
                self.vd_btn_play.configure(state="normal")
                self.vd_btn_stop.configure(state="normal")
                # Auto-play preview
                self._play_preview()
            except Exception as e:
                print(f"Fehler beim Speichern der Hörprobe: {e}")

        self.vd_btn_save.configure(state="normal")
        self.vd_result_info_lbl.configure(
            text=f"🎉 Bereit: '{name}' | ID: {voice_id} | {lang_code} ({gender})",
            text_color=COLOR_PRIMARY_TEXT
        )

    def _on_prompted_voice_error(self, err_msg: str):
        self.vd_btn_create.configure(state="normal", text="✨ Stimme erschaffen & Probehören")
        self.vd_status_lbl.configure(text="Fehler bei der Generierung.", text_color=M3_ERROR)
        messagebox.showerror("Fehler beim Erschaffen der Stimme", f"Die Stimme konnte nicht erstellt werden:\n\n{err_msg}")

    def _play_preview(self):
        if self.current_preview_file and self.current_preview_file.exists():
            try:
                self.audio_player.load(self.current_preview_file)
                self.audio_player.play()
            except Exception as e:
                messagebox.showerror("Wiedergabefehler", f"Konnte Hörprobe nicht abspielen: {e}")

    def _stop_preview(self):
        try:
            self.audio_player.stop()
        except Exception:
            pass

    def _save_and_activate_created_voice(self):
        if not self.last_created_voice:
            return
        save_custom_voice(self.last_created_voice)
        voice_id = self.last_created_voice["id"]
        if self.on_voice_selected_callback:
            self.on_voice_selected_callback(voice_id)
        messagebox.showinfo(
            "Stimme gespeichert",
            f"Die Stimme '{self.last_created_voice['name']}' wurde erfolgreich gespeichert und als aktive Stimme ausgewählt!"
        )
        self._refresh_custom_voices_list()
        self._on_close()

    # =========================================================================
    # TAB 2: VOICE REPLICATION (KLONEN MIT AUDIO-DATEIEN)
    # =========================================================================
    def _build_tab_replicate(self):
        info_card = ctk.CTkFrame(
            self.tab_replicate,
            corner_radius=10,
            fg_color=("#FEF7E0", "#332701"),
            border_width=1,
            border_color=("#FEEFC3", "#5C4600")
        )
        info_card.pack(fill="x", padx=12, pady=(8, 10))

        ctk.CTkLabel(
            info_card,
            text="ℹ️ Voice Replication klont die biometrischen Merkmale einer realen Person anhand von Referenz- und Verifizierungsaufnahmen.\n\n⚠️ Regionaler Hinweis (EWR/EU): Google schränkt das Hochladen biometrischer Stimmdateien im europäischen Wirtschaftsraum derzeit ein (API blockiert mit 'Location not supported'). Für Projekte mit Standort Deutschland/EU nutzen Sie bitte den Reiter 'Voice Design'!",
            wraplength=660,
            justify="left",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("#B06000", "#FDD663")
        ).pack(padx=12, pady=8, anchor="w")

        # Name
        name_row = ctk.CTkFrame(self.tab_replicate, fg_color="transparent")
        name_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(name_row, text="Name des Stimm-Klons:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(side="left", padx=(0, 10))
        self.vr_name_entry = ctk.CTkEntry(
            name_row,
            placeholder_text="z. B. Mein Stimm-Klon",
            height=36,
            corner_radius=10,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE,
            border_color=M3_OUTLINE_VARIANT
        )
        self.vr_name_entry.pack(side="left", fill="x", expand=True)

        # File 1: Reference Audio
        ref_box = ctk.CTkFrame(self.tab_replicate, corner_radius=10, fg_color=M3_SURFACE, border_width=1, border_color=M3_OUTLINE_VARIANT)
        ref_box.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(ref_box, text="1. Referenz-Audiodatei (ca. 10–30s saubere Sprache):", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", padx=12, pady=(8, 4))
        
        ref_btn_row = ctk.CTkFrame(ref_box, fg_color="transparent")
        ref_btn_row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkButton(
            ref_btn_row,
            text="📁 Referenz-Audio auswählen...",
            command=self._pick_ref_audio,
            height=32,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_SECONDARY_CONTAINER,
            text_color=M3_ON_SECONDARY_CONTAINER
        ).pack(side="left")

        self.vr_ref_lbl = ctk.CTkLabel(
            ref_btn_row,
            text="Keine Datei ausgewählt",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT
        )
        self.vr_ref_lbl.pack(side="left", padx=10)

        # File 2: Consent Audio
        consent_box = ctk.CTkFrame(self.tab_replicate, corner_radius=10, fg_color=M3_SURFACE, border_width=1, border_color=M3_OUTLINE_VARIANT)
        consent_box.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(consent_box, text="2. Einverständniserklärung (Consent-Audio des Sprechers):", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", padx=12, pady=(8, 4))
        
        statement_frame = ctk.CTkFrame(consent_box, corner_radius=8, fg_color=M3_SURFACE_CONTAINER)
        statement_frame.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(
            statement_frame,
            text='Der Sprecher muss folgenden Verifizierungssatz aufnehmen:\n"I am the owner of this voice and I consent to Google using this voice to create a synthetic voice model."',
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, slant="italic"),
            text_color=COLOR_PRIMARY_TEXT,
            justify="left"
        ).pack(padx=10, pady=6, anchor="w")

        consent_btn_row = ctk.CTkFrame(consent_box, fg_color="transparent")
        consent_btn_row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkButton(
            consent_btn_row,
            text="📁 Consent-Audio auswählen...",
            command=self._pick_consent_audio,
            height=32,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_SECONDARY_CONTAINER,
            text_color=M3_ON_SECONDARY_CONTAINER
        ).pack(side="left")

        self.vr_consent_lbl = ctk.CTkLabel(
            consent_btn_row,
            text="Keine Datei ausgewählt",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT
        )
        self.vr_consent_lbl.pack(side="left", padx=10)

        # Clone Action
        vr_action_row = ctk.CTkFrame(self.tab_replicate, fg_color="transparent")
        vr_action_row.pack(fill="x", padx=12, pady=(6, 10))

        self.vr_btn_clone = ctk.CTkButton(
            vr_action_row,
            text="🧬 Stimme jetzt klonen",
            command=self._clone_voice,
            height=40,
            corner_radius=20,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=M3_PRIMARY,
            hover_color=M3_PRIMARY_HOVER,
            text_color=M3_ON_PRIMARY
        )
        self.vr_btn_clone.pack(side="left")

        self.vr_status_lbl = ctk.CTkLabel(
            self.tab_replicate,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            wraplength=660,
            justify="left"
        )
        self.vr_status_lbl.pack(fill="x", padx=12, pady=(4, 0))

    def _pick_ref_audio(self):
        file_path = filedialog.askopenfilename(
            title="Referenz-Audiodatei auswählen",
            filetypes=[("Audiodateien", "*.wav;*.mp3;*.m4a;*.ogg"), ("Alle Dateien", "*.*")]
        )
        if file_path:
            p = Path(file_path)
            self.ref_audio_path = p
            size_mb = p.stat().st_size / (1024 * 1024)
            self.vr_ref_lbl.configure(text=f"✓ {p.name} ({size_mb:.2f} MB)", text_color="#10B981")

    def _pick_consent_audio(self):
        file_path = filedialog.askopenfilename(
            title="Consent-Audiodatei auswählen",
            filetypes=[("Audiodateien", "*.wav;*.mp3;*.m4a;*.ogg"), ("Alle Dateien", "*.*")]
        )
        if file_path:
            p = Path(file_path)
            self.consent_audio_path = p
            size_mb = p.stat().st_size / (1024 * 1024)
            self.vr_consent_lbl.configure(text=f"✓ {p.name} ({size_mb:.2f} MB)", text_color="#10B981")

    def _clone_voice(self):
        name = self.vr_name_entry.get().strip()
        if not name:
            messagebox.showwarning("Fehlender Name", "Bitte gib einen Namen für den Stimm-Klon ein.")
            return

        if not self.ref_audio_path or not self.ref_audio_path.exists():
            messagebox.showwarning("Referenz fehlt", "Bitte wähle eine Referenz-Audiodatei aus.")
            return

        if not self.consent_audio_path or not self.consent_audio_path.exists():
            messagebox.showwarning("Einverständnis fehlt", "Bitte wähle die Consent-Audiodatei aus.")
            return

        self.vr_btn_clone.configure(state="disabled", text="⏳ Sende Audiodaten an Google...")
        self.vr_status_lbl.configure(text="Google verifiziert Sprecher-Biometrie und Consent...", text_color=M3_PRIMARY)

        def run_clone():
            try:
                with open(self.ref_audio_path, "rb") as f:
                    ref_bytes = f.read()
                with open(self.consent_audio_path, "rb") as f:
                    consent_bytes = f.read()

                res = self.tts_service.create_replicated_voice(
                    display_name=name,
                    source_audio_bytes=ref_bytes,
                    consent_audio_bytes=consent_bytes,
                    model="gemini-3.8-flash-tts"
                )
                self.after(0, lambda: self._on_clone_success(res, name))
            except Exception as e:
                self.after(0, lambda: self._on_clone_error(str(e)))

        threading.Thread(target=run_clone, daemon=True).start()

    def _on_clone_success(self, res: dict, name: str):
        self.vr_btn_clone.configure(state="normal", text="🧬 Stimme jetzt klonen")
        self.vr_status_lbl.configure(text="✅ Stimme erfolgreich geklont!", text_color="#10B981")

        voice_id = res.get("id", f"voice_{int(time.time())}")
        voice_data = {
            "id": voice_id,
            "name": name,
            "desc": f"Geklonte Stimme ({Path(self.ref_audio_path).name})",
            "type": "replicated",
            "gender": "unknown",
            "language_code": "auto",
            "created_at": datetime.now().isoformat()
        }
        save_custom_voice(voice_data)
        if self.on_voice_selected_callback:
            self.on_voice_selected_callback(voice_id)

        messagebox.showinfo(
            "Stimmklon erstellt",
            f"Die Stimme '{name}' ({voice_id}) wurde erfolgreich geklont und als aktive Stimme ausgewählt!"
        )
        self._refresh_custom_voices_list()
        self._on_close()

    def _on_clone_error(self, err_msg: str):
        self.vr_btn_clone.configure(state="normal", text="🧬 Stimme jetzt klonen")
        self.vr_status_lbl.configure(text=f"Fehler: {err_msg[:180]}...", text_color=M3_ERROR)
        messagebox.showerror(
            "Fehler beim Klonen",
            f"{err_msg}"
        )

    # =========================================================================
    # TAB 3: MEINE STIMMEN & MANUELLE IDS
    # =========================================================================
    def _build_tab_manage(self):
        # Section 1: Manual import
        import_card = ctk.CTkFrame(self.tab_manage, corner_radius=10, fg_color=M3_SURFACE, border_width=1, border_color=M3_OUTLINE_VARIANT)
        import_card.pack(fill="x", padx=12, pady=(8, 10))

        ctk.CTkLabel(import_card, text="🔑 Vorhandene Voice-ID hinzufügen (z. B. aus Google AI Studio):", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", padx=12, pady=(8, 6))

        row = ctk.CTkFrame(import_card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 8))

        self.man_id_entry = ctk.CTkEntry(
            row,
            placeholder_text="Voice-ID (z. B. voice_abc123... oder voicekey_...)",
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE_CONTAINER,
            border_color=M3_OUTLINE_VARIANT
        )
        self.man_id_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.man_name_entry = ctk.CTkEntry(
            row,
            placeholder_text="Anzeigename (z. B. Studio-Stimme)",
            height=34,
            width=200,
            corner_radius=8,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE_CONTAINER,
            border_color=M3_OUTLINE_VARIANT
        )
        self.man_name_entry.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row,
            text="➕ Hinzufügen",
            command=self._add_manual_voice,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_PRIMARY,
            text_color=M3_ON_PRIMARY
        ).pack(side="left")

        # Sync button row
        sync_row = ctk.CTkFrame(self.tab_manage, fg_color="transparent")
        sync_row.pack(fill="x", padx=12, pady=(0, 8))

        self.sync_btn = ctk.CTkButton(
            sync_row,
            text="🔄 Aus Google Cloud synchronisieren",
            command=self._sync_cloud_voices,
            height=32,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=M3_SECONDARY_CONTAINER,
            text_color=M3_ON_SECONDARY_CONTAINER
        )
        self.sync_btn.pack(side="left")

        self.sync_status_lbl = ctk.CTkLabel(
            sync_row,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT
        )
        self.sync_status_lbl.pack(side="left", padx=10)

        # Scrollable voice list
        ctk.CTkLabel(
            self.tab_manage,
            text="Gespeicherte Stimmen:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", padx=12, pady=(4, 4))

        self.voices_scroll_frame = ctk.CTkScrollableFrame(
            self.tab_manage,
            corner_radius=12,
            fg_color=M3_SURFACE,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        self.voices_scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self._refresh_custom_voices_list()

    def _add_manual_voice(self):
        voice_id = self.man_id_entry.get().strip()
        name = self.man_name_entry.get().strip() or voice_id
        if not voice_id:
            messagebox.showwarning("Fehlende ID", "Bitte gib eine Voice-ID ein.")
            return

        voice_data = {
            "id": voice_id,
            "name": name,
            "desc": f"Benutzerdefinierte Voice-ID ({voice_id})",
            "type": "custom",
            "created_at": datetime.now().isoformat()
        }
        save_custom_voice(voice_data)
        self.man_id_entry.delete(0, "end")
        self.man_name_entry.delete(0, "end")
        self._refresh_custom_voices_list()
        messagebox.showinfo("Hinzugefügt", f"Stimme '{name}' wurde erfolgreich hinterlegt!")

    def _sync_cloud_voices(self):
        self.sync_btn.configure(state="disabled", text="⏳ Synchronisiere...")
        self.sync_status_lbl.configure(text="Frage Stimmen aus Google Cloud ab...")

        def run_sync():
            try:
                cloud_voices = self.tts_service.fetch_cloud_voices()
                for cv in cloud_voices:
                    cid = cv.get("id")
                    if cid:
                        save_custom_voice({
                            "id": cid,
                            "name": cv.get("display_name", cid),
                            "desc": cv.get("description", cv.get("prompted", {}).get("input", "Aus Google Cloud synchronisiert")),
                            "type": cv.get("type", "prompted"),
                            "gender": cv.get("gender", "unknown"),
                            "language_code": cv.get("language_code", "auto"),
                            "created_at": datetime.now().isoformat()
                        })
                count = len(cloud_voices)
                self.after(0, lambda: self._on_sync_done(count))
            except Exception as e:
                self.after(0, lambda: self._on_sync_error(str(e)))

        threading.Thread(target=run_sync, daemon=True).start()

    def _on_sync_done(self, count: int):
        self.sync_btn.configure(state="normal", text="🔄 Aus Google Cloud synchronisieren")
        self.sync_status_lbl.configure(text=f"✓ {count} Stimme(n) synchronisiert", text_color="#10B981")
        self._refresh_custom_voices_list()

    def _on_sync_error(self, err: str):
        self.sync_btn.configure(state="normal", text="🔄 Aus Google Cloud synchronisieren")
        self.sync_status_lbl.configure(text=f"Fehler: {err[:60]}", text_color=M3_ERROR)

    def _refresh_custom_voices_list(self):
        for widget in self.voices_scroll_frame.winfo_children():
            widget.destroy()

        voices = load_custom_voices()
        if not voices:
            empty_lbl = ctk.CTkLabel(
                self.voices_scroll_frame,
                text="Noch keine benutzerdefinierten Stimmen gespeichert.\nNutze 'Voice Design', um eine neue Stimme zu erschaffen!",
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                text_color=COLOR_MUTED_TEXT,
                justify="center"
            )
            empty_lbl.pack(pady=30)
            return

        for v in voices:
            card = ctk.CTkFrame(
                self.voices_scroll_frame,
                corner_radius=10,
                fg_color=M3_SURFACE_CONTAINER,
                border_width=1,
                border_color=M3_OUTLINE_VARIANT
            )
            card.pack(fill="x", padx=6, pady=4)

            info_col = ctk.CTkFrame(card, fg_color="transparent")
            info_col.pack(side="left", fill="x", expand=True, padx=12, pady=8)

            title_row = ctk.CTkFrame(info_col, fg_color="transparent")
            title_row.pack(fill="x")

            vtype = v.get("type", "prompted")
            type_tag = "🎨 Voice Design" if vtype == "prompted" else ("🎙️ Stimmklon" if vtype == "replicated" else "🔑 Voice-ID")

            ctk.CTkLabel(
                title_row,
                text=v.get("name", "Unbenannt"),
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
                text_color=COLOR_PRIMARY_TEXT
            ).pack(side="left")

            ctk.CTkLabel(
                title_row,
                text=f" [{type_tag}]",
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                text_color=M3_PRIMARY
            ).pack(side="left", padx=4)

            sub_txt = f"ID: {v.get('id', '')} | {v.get('language_code', 'auto')} ({v.get('gender', '')})"
            ctk.CTkLabel(
                info_col,
                text=sub_txt,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                text_color=COLOR_MUTED_TEXT,
                anchor="w"
            ).pack(fill="x", pady=(2, 0))

            btn_col = ctk.CTkFrame(card, fg_color="transparent")
            btn_col.pack(side="right", padx=10, pady=8)

            vid = v.get("id")
            ctk.CTkButton(
                btn_col,
                text="⭐ Aktivieren",
                command=lambda target_id=vid: self._activate_voice_by_id(target_id),
                height=30,
                corner_radius=15,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                fg_color=M3_PRIMARY,
                text_color=M3_ON_PRIMARY
            ).pack(side="left", padx=(0, 6))

            ctk.CTkButton(
                btn_col,
                text="🗑️",
                command=lambda target_id=vid: self._delete_voice_by_id(target_id),
                height=30,
                width=34,
                corner_radius=15,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                fg_color="transparent",
                hover_color=M3_ERROR_HOVER,
                border_width=1,
                border_color=M3_OUTLINE,
                text_color=M3_ERROR
            ).pack(side="left")

    def _activate_voice_by_id(self, voice_id: str):
        if self.on_voice_selected_callback:
            self.on_voice_selected_callback(voice_id)
        messagebox.showinfo("Aktiviert", f"Stimme '{voice_id}' wurde als aktive Stimme in der Hauptoberfläche gewählt!")
        self._on_close()

    def _delete_voice_by_id(self, voice_id: str):
        if messagebox.askyesno("Stimme löschen", f"Möchtest du die Stimme '{voice_id}' wirklich entfernen?"):
            delete_custom_voice(voice_id)
            # Try cloud delete if stateful
            threading.Thread(target=lambda: self.tts_service.delete_cloud_voice(voice_id), daemon=True).start()
            self._refresh_custom_voices_list()
            if self.on_voice_selected_callback:
                self.on_voice_selected_callback("Puck")


class _StyleInputProxy:
    """Proxy object providing backward compatibility for any legacy code calling self.style_input."""
    def __init__(self, app):
        self.app = app

    def get(self, *args, **kwargs):
        return getattr(self.app, "system_prompt_text", "")

    def delete(self, *args, **kwargs):
        self.app.system_prompt_text = ""

    def insert(self, idx, text):
        self.app.system_prompt_text = text


class SettingsDialog(ctk.CTkToplevel):
    """
    Modern Google Material 3 Settings Dialog for Gemini TTS Studio v2.2.
    Provides 4 organized tabs:
    1. Stimme & Sprache: Category filter, Voice selector with description, Language selector, Voice Studio launcher
    2. Regie & Ton: 1-click tone presets, System-Prompt textarea, Save/Delete custom presets, hints
    3. Audio-Format: 1-click profile cards (Web AAC 64k, Podcast HQ M4A 128k, MP3 96k, Studio WAV 48kHz), fine-tuning controls
    4. KI-Engine & API: Model selection, API Key input & verification test, background auto-update toggle
    """

    def __init__(self, parent: "GeminiTTSApp", initial_tab: str = "voice"):
        super().__init__(parent)
        self.parent_app = parent
        self.title("Gemini TTS Studio - Einstellungen")
        self.geometry("780x720")
        self.minsize(720, 620)

        # Working variables initialized from parent
        self.voice_cat_var = ctk.StringVar(value=parent.voice_category_var.get())
        self.voice_var = ctk.StringVar(value=parent.voice_var.get())
        self.lang_var = ctk.StringVar(value=parent.lang_var.get())
        self.model_var = ctk.StringVar(value=parent.model_var.get())

        self.codec_var = ctk.StringVar(value=parent.codec_var.get())
        self.channels_var = ctk.StringVar(value=parent.channels_var.get())
        self.rate_var = ctk.StringVar(value=parent.rate_var.get())
        self.bitrate_var = ctk.StringVar(value=parent.bitrate_var.get())
        self.faststart_var = ctk.BooleanVar(value=parent.faststart_var.get())
        self.active_style_preset = getattr(parent, "active_style_preset_name", "Sachlich & Seriös")
        self.auto_update_var = ctk.BooleanVar(value=getattr(parent, "auto_update_on_start", True))

        self.tab_buttons: Dict[str, ctk.CTkButton] = {}
        self.tab_frames: Dict[str, ctk.CTkFrame] = {}

        self._build_ui()
        self._switch_tab(initial_tab)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.transient(parent)
        self.grab_set()

    def _on_close(self):
        if self.parent_app:
            self.parent_app.settings_dialog = None
        self.destroy()

    def _build_ui(self):
        container = ctk.CTkFrame(
            self,
            corner_radius=18,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        container.pack(padx=16, pady=16, fill="both", expand=True)

        # Header
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 12))

        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.pack(side="left")

        dlg_title = ctk.CTkLabel(
            title_col,
            text="⚙️ Studio-Einstellungen",
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        dlg_title.pack(anchor="w")

        dlg_sub = ctk.CTkLabel(
            title_col,
            text="Stimme, Regieanweisungen, Format und KI-Engine konfigurieren",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        )
        dlg_sub.pack(anchor="w")

        close_btn = ctk.CTkButton(
            header,
            text="✕",
            command=self._on_close,
            width=32,
            height=32,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=COLOR_MUTED_TEXT
        )
        close_btn.pack(side="right")

        # Tab Navigation Bar
        nav_bar = ctk.CTkFrame(container, fg_color=M3_SURFACE_CONTAINER, corner_radius=14, height=44)
        nav_bar.pack(fill="x", padx=20, pady=(0, 12))

        tabs_info = [
            ("voice", "🗣️ Stimme & Sprache"),
            ("style", "🎭 Regie & Ton"),
            ("format", "🎛️ Audio-Format & Web"),
            ("model", "🤖 KI-Engine & API")
        ]

        for tab_id, label in tabs_info:
            btn = ctk.CTkButton(
                nav_bar,
                text=label,
                command=lambda t=tab_id: self._switch_tab(t),
                height=36,
                corner_radius=10,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                fg_color="transparent",
                hover_color=M3_SURFACE_CONTAINER_HIGH,
                text_color=COLOR_MUTED_TEXT
            )
            btn.pack(side="left", padx=4, pady=4, fill="x", expand=True)
            self.tab_buttons[tab_id] = btn

        # Tab Content Area
        self.content_area = ctk.CTkFrame(container, fg_color="transparent")
        self.content_area.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Build individual tab views
        self._build_tab_voice()
        self._build_tab_style()
        self._build_tab_format()
        self._build_tab_model()

        # Footer Actions
        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(6, 16))

        reset_btn = ctk.CTkButton(
            footer,
            text="Standardwerte wiederherstellen",
            command=self._reset_defaults,
            height=36,
            corner_radius=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=COLOR_MUTED_TEXT
        )
        reset_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            footer,
            text="💾 Einstellungen übernehmen",
            command=self._save_and_apply,
            height=38,
            corner_radius=19,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=M3_PRIMARY,
            hover_color=M3_PRIMARY_HOVER,
            text_color=("#FFFFFF", "#00201C")
        )
        save_btn.pack(side="right", padx=(8, 0))

        cancel_btn = ctk.CTkButton(
            footer,
            text="Abbrechen",
            command=self._on_close,
            height=38,
            corner_radius=19,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="transparent",
            hover_color=M3_SURFACE_CONTAINER,
            text_color=COLOR_PRIMARY_TEXT,
            border_width=1.5,
            border_color=M3_OUTLINE
        )
        cancel_btn.pack(side="right")

    def _build_tab_voice(self):
        f = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["voice"] = f
        f.grid_columnconfigure((0, 1), weight=1)

        # Left Column: Category & Voice Selector
        left = ctk.CTkFrame(f, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(
            left,
            text="📁 Stimmen-Kategorie filtern:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        self.voice_cat_menu = ctk.CTkOptionMenu(
            left,
            values=["Alle Stimmen", "🎙️ Eigene / Geklonte Stimmen", "⭐ Favoriten & Allrounder", "🇩🇪 Deutsche Stimmen & Rollen", "📖 Erzähler & Storytelling"],
            variable=self.voice_cat_var,
            command=self._on_category_changed,
            height=36,
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
        self.voice_cat_menu.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            left,
            text="🗣️ Aktive Sprecherstimme:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        all_v = get_all_voices()
        v_opts = [f"{v['id']} ({v['desc'].split('(')[-1].replace(')', '')})" for v in all_v]
        self.voice_menu = ctk.CTkOptionMenu(
            left,
            values=v_opts,
            variable=self.voice_var,
            command=self._on_voice_changed,
            height=36,
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
        self.voice_menu.pack(fill="x", pady=(0, 12))

        # Bio Preview Card
        self.bio_card = ctk.CTkFrame(
            left,
            fg_color=M3_SURFACE_CONTAINER,
            corner_radius=14,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        self.bio_card.pack(fill="x", pady=(0, 10))

        bio_top = ctk.CTkFrame(self.bio_card, fg_color="transparent")
        bio_top.pack(fill="x", padx=12, pady=(10, 4))

        self.voice_bio_title = ctk.CTkLabel(
            bio_top,
            text=self.voice_var.get(),
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.voice_bio_title.pack(side="left")

        self.voice_bio_badge = ctk.CTkLabel(
            bio_top,
            text="Standard",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=M3_SURFACE_CONTAINER_HIGH,
            text_color=COLOR_MUTED_TEXT,
            corner_radius=6,
            padx=6,
            pady=1
        )
        self.voice_bio_badge.pack(side="right")

        self.voice_desc_lbl = ctk.CTkLabel(
            self.bio_card,
            text=all_v[0]["desc"] if all_v else "",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT,
            wraplength=310,
            justify="left"
        )
        self.voice_desc_lbl.pack(anchor="w", padx=12, pady=(0, 10))

        # Right Column: Language & Voice Studio Launcher
        right = ctk.CTkFrame(f, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(
            right,
            text="🌐 Sprache der Vertonung:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        l_opts = [l["name"] for l in SUPPORTED_LANGUAGES]
        self.lang_menu = ctk.CTkOptionMenu(
            right,
            values=l_opts,
            variable=self.lang_var,
            height=36,
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
        self.lang_menu.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            right,
            text="32 Sprachen für Gemini 3.8 Flash TTS voll unterstützt.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(0, 14))

        # Voice Studio Promotion Card
        vs_card = ctk.CTkFrame(
            right,
            fg_color=M3_SECONDARY_CONTAINER,
            corner_radius=16,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        vs_card.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            vs_card,
            text="🎨 Gemini 3.8 Voice Studio",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=M3_ON_SECONDARY_CONTAINER
        ).pack(anchor="w", padx=14, pady=(12, 4))

        ctk.CTkLabel(
            vs_card,
            text="Erstelle individuelle Stimmen über natürliches Prompting (Voice Design) oder klone vorhandene Audio-Referenzen (Replication) mit Consent-Nachweis.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=M3_ON_SECONDARY_CONTAINER,
            wraplength=310,
            justify="left"
        ).pack(anchor="w", padx=14, pady=(0, 10))

        vs_btn = ctk.CTkButton(
            vs_card,
            text="✨ Voice Studio & Stimmklon öffnen...",
            command=self._open_voice_studio,
            height=34,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_PRIMARY,
            hover_color=M3_PRIMARY_HOVER,
            text_color=("#FFFFFF", "#00201C")
        )
        vs_btn.pack(fill="x", padx=14, pady=(0, 12))

        self._on_voice_changed(self.voice_var.get())

    def _build_tab_style(self):
        f = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["style"] = f

        head_row = ctk.CTkFrame(f, fg_color="transparent")
        head_row.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            head_row,
            text="⚡ Schnell-Vorlagen (Presets mit 1 Klick anwenden):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left")

        clear_btn = ctk.CTkButton(
            head_row,
            text="Eingabe leeren",
            command=self._clear_style,
            width=90,
            height=26,
            corner_radius=13,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=M3_ERROR_HOVER,
            text_color=M3_ERROR
        )
        clear_btn.pack(side="right")

        # Quick Preset Buttons Frame
        presets_bar = ctk.CTkFrame(f, fg_color="transparent")
        presets_bar.pack(fill="x", pady=(0, 10))

        quick_presets = [
            ("💼 Sachlich & Seriös", "Sprich in einem ruhigen, sachlichen und hochprofessionellen Tonfall wie ein erfahrener Nachrichtensprecher. Achte auf präzise Artikulation und deutliche Satzakzente."),
            ("🔥 Begeistert & Dynamisch", "Sprich voller Energie, enthusiastisch und ansteckend wie bei einer spannenden Produktpräsentation."),
            ("🌿 Doku-Erzähler", "Sprich mit tiefer, getragener und faszinierender Stimme wie der Sprecher einer anspruchsvollen Naturdokumentation."),
            ("🎙️ Podcast Host", "Sprich entspannt, natürlich, nahbar und im Plauderton wie ein erfahrener Podcaster."),
            ("🌙 Sanft & Beruhigend", "Sprich mit leiser, warmer und beruhigender Stimme, ideal für Meditation oder Einschlafgeschichten.")
        ]

        for p_name, p_text in quick_presets:
            p_btn = ctk.CTkButton(
                presets_bar,
                text=p_name,
                command=lambda name=p_name, text=p_text: self._apply_tone_preset(name, text),
                height=30,
                corner_radius=15,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                fg_color=M3_SURFACE_CONTAINER,
                hover_color=M3_PRIMARY_CONTAINER,
                text_color=COLOR_PRIMARY_TEXT,
                border_width=1,
                border_color=M3_OUTLINE_VARIANT
            )
            p_btn.pack(side="left", padx=3)

        # Directive Text Box
        prompt_head = ctk.CTkFrame(f, fg_color="transparent")
        prompt_head.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            prompt_head,
            text="📝 Detaillierte Regieanweisung (System-Prompt):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left")

        save_p_btn = ctk.CTkButton(
            prompt_head,
            text="💾 Als neue Vorlage speichern...",
            command=self._save_style_preset,
            height=26,
            corner_radius=13,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=M3_PRIMARY_CONTAINER,
            hover_color=("#B6E4DA", "#00645A"),
            text_color=M3_ON_PRIMARY_CONTAINER
        )
        save_p_btn.pack(side="right")

        self.prompt_box = ctk.CTkTextbox(
            f,
            height=120,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            wrap="word",
            corner_radius=14,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT,
            fg_color=("#FFFFFF", "#0E1A18"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.prompt_box.pack(fill="x", pady=(0, 10))
        current_p = self.parent_app._get_current_system_prompt()
        if current_p:
            self.prompt_box.insert("0.0", current_p)

        # Custom Presets Management Row
        custom_row = ctk.CTkFrame(f, fg_color="transparent")
        custom_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            custom_row,
            text="Eigene Vorlagen:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left", padx=(0, 8))

        self.custom_style_var = ctk.StringVar(value="-- Gespeicherte Vorlagen --")
        self.custom_preset_menu = ctk.CTkOptionMenu(
            custom_row,
            values=["-- Gespeicherte Vorlagen --"],
            variable=self.custom_style_var,
            command=self._on_custom_style_selected,
            height=32,
            corner_radius=10,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            fg_color=M3_SURFACE_CONTAINER,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT,
            dropdown_fg_color=M3_SURFACE,
            dropdown_hover_color=("#E0ECE9", "#1C302D"),
            dropdown_text_color=COLOR_PRIMARY_TEXT
        )
        self.custom_preset_menu.pack(side="left", fill="x", expand=True, padx=(0, 8))

        del_preset_btn = ctk.CTkButton(
            custom_row,
            text="🗑️ Löschen",
            command=self._delete_style_preset,
            width=80,
            height=32,
            corner_radius=10,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent",
            hover_color=M3_ERROR_HOVER,
            text_color=M3_ERROR,
            border_width=1,
            border_color=M3_ERROR_CONTAINER
        )
        del_preset_btn.pack(side="left")

        # Hint Box
        hint_box = ctk.CTkFrame(
            f,
            fg_color=("#FEF3C7", "#2D2410"),
            corner_radius=12,
            border_width=1,
            border_color=("#FDE68A", "#453818")
        )
        hint_box.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(
            hint_box,
            text="💡 Tipp zur Sprachkonsistenz: Halte Regieanweisungen vorzugsweise in derselben Sprache wie den Haupttext. Gemini 3.8 nutzt diesen Text als Regieanweisung – er wird nicht als gesprochener Text ausgegeben.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("#92400E", "#FCD34D"),
            wraplength=680,
            justify="left"
        ).pack(anchor="w", padx=12, pady=8)

        self._refresh_custom_presets_list()

    def _build_tab_format(self):
        f = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["format"] = f

        ctk.CTkLabel(
            f,
            text="Wähle ein vorkonfiguriertes Profil für Web, Podcast oder Nachbearbeitung:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(0, 10))

        # 4 Preset Cards in 2x2 Grid
        cards_grid = ctk.CTkFrame(f, fg_color="transparent")
        cards_grid.pack(fill="x", pady=(0, 12))
        cards_grid.grid_columnconfigure((0, 1), weight=1)

        # Profile 1: Web AAC 64k
        c1 = ctk.CTkFrame(cards_grid, fg_color=M3_SURFACE_CONTAINER, corner_radius=14, border_width=1.5, border_color=M3_OUTLINE_VARIANT)
        c1.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(c1, text="🌐 Web-Optimiert (AAC 64k)", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(c1, text="Mono, 64 kbps, MP4 FastStart. Extrem kompakt, sofortiges Streaming.", font=ctk.CTkFont(family=FONT_FAMILY, size=10), text_color=COLOR_MUTED_TEXT, wraplength=300, justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        ctk.CTkButton(c1, text="Anwenden", command=lambda: self._apply_format_preset("aac", "64 kbit/s", "Mono (1)", True, "48.000 Hz", "Web AAC 64k"), height=26, corner_radius=13, font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"), fg_color=M3_PRIMARY, hover_color=M3_PRIMARY_HOVER, text_color=("#FFFFFF", "#00201C")).pack(anchor="e", padx=12, pady=(0, 10))

        # Profile 2: Podcast HQ M4A 128k
        c2 = ctk.CTkFrame(cards_grid, fg_color=M3_SURFACE_CONTAINER, corner_radius=14, border_width=1.5, border_color=M3_OUTLINE_VARIANT)
        c2.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(c2, text="🎙️ Podcast HQ (M4A 128k)", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(c2, text="Stereo, 128 kbps, AAC-LC. Kristallklare Sprachqualität für Audiotouren.", font=ctk.CTkFont(family=FONT_FAMILY, size=10), text_color=COLOR_MUTED_TEXT, wraplength=300, justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        ctk.CTkButton(c2, text="Anwenden", command=lambda: self._apply_format_preset("aac", "128 kbit/s", "Stereo (2)", True, "48.000 Hz", "Podcast HQ 128k"), height=26, corner_radius=13, font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"), fg_color=M3_PRIMARY, hover_color=M3_PRIMARY_HOVER, text_color=("#FFFFFF", "#00201C")).pack(anchor="e", padx=12, pady=(0, 10))

        # Profile 3: Universell MP3 96k
        c3 = ctk.CTkFrame(cards_grid, fg_color=M3_SURFACE_CONTAINER, corner_radius=14, border_width=1.5, border_color=M3_OUTLINE_VARIANT)
        c3.grid(row=1, column=0, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(c3, text="📻 Universell (MP3 96k)", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(c3, text="Mono, 96 kbps MP3. Höchste Kompatibilität auf ausnahmslos jedem Endgerät.", font=ctk.CTkFont(family=FONT_FAMILY, size=10), text_color=COLOR_MUTED_TEXT, wraplength=300, justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        ctk.CTkButton(c3, text="Anwenden", command=lambda: self._apply_format_preset("libmp3lame", "96 kbit/s", "Mono (1)", False, "44.100 Hz", "MP3 96k"), height=26, corner_radius=13, font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"), fg_color=M3_PRIMARY, hover_color=M3_PRIMARY_HOVER, text_color=("#FFFFFF", "#00201C")).pack(anchor="e", padx=12, pady=(0, 10))

        # Profile 4: Studio Master WAV 48kHz
        c4 = ctk.CTkFrame(cards_grid, fg_color=M3_SURFACE_CONTAINER, corner_radius=14, border_width=1.5, border_color=M3_OUTLINE_VARIANT)
        c4.grid(row=1, column=1, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(c4, text="🎼 Studio Master (WAV 48kHz)", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color=COLOR_PRIMARY_TEXT).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(c4, text="PCM 16-Bit unkomprimiert, 48 kHz. Reines Studio-Rohmaterial ohne Verluste.", font=ctk.CTkFont(family=FONT_FAMILY, size=10), text_color=COLOR_MUTED_TEXT, wraplength=300, justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        ctk.CTkButton(c4, text="Anwenden", command=lambda: self._apply_format_preset("pcm_s16le", "128 kbit/s", "Stereo (2)", False, "48.000 Hz", "WAV 48kHz"), height=26, corner_radius=13, font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"), fg_color=M3_PRIMARY, hover_color=M3_PRIMARY_HOVER, text_color=("#FFFFFF", "#00201C")).pack(anchor="e", padx=12, pady=(0, 10))

        # Detail parameters box
        detail_box = ctk.CTkFrame(f, fg_color=M3_SURFACE_CONTAINER, corner_radius=14, border_width=1, border_color=M3_OUTLINE_VARIANT)
        detail_box.pack(fill="x", pady=(0, 4))
        detail_box.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(detail_box, text="Detaillierte Encoding-Parameter:", font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"), text_color=COLOR_PRIMARY_TEXT).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 4))

        # Codec
        ctk.CTkLabel(detail_box, text="Codec:", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_MUTED_TEXT).grid(row=1, column=0, padx=10, sticky="w")
        self.codec_menu = ctk.CTkOptionMenu(detail_box, values=["aac", "libmp3lame", "pcm_s16le"], variable=self.codec_var, height=30, corner_radius=8, font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"))
        self.codec_menu.grid(row=2, column=0, padx=10, pady=(2, 8), sticky="ew")

        # Channels
        ctk.CTkLabel(detail_box, text="Kanäle:", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_MUTED_TEXT).grid(row=1, column=1, padx=10, sticky="w")
        self.channels_menu = ctk.CTkOptionMenu(detail_box, values=["Mono (1)", "Stereo (2)"], variable=self.channels_var, height=30, corner_radius=8, font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"))
        self.channels_menu.grid(row=2, column=1, padx=10, pady=(2, 8), sticky="ew")

        # Rate
        ctk.CTkLabel(detail_box, text="Abtastrate:", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_MUTED_TEXT).grid(row=1, column=2, padx=10, sticky="w")
        self.rate_menu = ctk.CTkOptionMenu(detail_box, values=["44.100 Hz", "48.000 Hz", "24.000 Hz"], variable=self.rate_var, height=30, corner_radius=8, font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"))
        self.rate_menu.grid(row=2, column=2, padx=10, pady=(2, 8), sticky="ew")

        # Bitrate
        ctk.CTkLabel(detail_box, text="Datenrate:", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_MUTED_TEXT).grid(row=1, column=3, padx=10, sticky="w")
        self.bitrate_menu = ctk.CTkOptionMenu(detail_box, values=["48 kbit/s", "64 kbit/s", "96 kbit/s", "128 kbit/s", "192 kbit/s", "256 kbit/s", "320 kbit/s"], variable=self.bitrate_var, height=30, corner_radius=8, font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"))
        self.bitrate_menu.grid(row=2, column=3, padx=10, pady=(2, 8), sticky="ew")

        # FastStart Checkbox
        self.faststart_check = ctk.CTkCheckBox(
            detail_box,
            text="MP4 FastStart Flag setzen (sofortiges Abspielen ohne Vorab-Download)",
            variable=self.faststart_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT,
            fg_color=M3_PRIMARY[0],
            hover_color=M3_PRIMARY_HOVER[0]
        )
        self.faststart_check.grid(row=3, column=0, columnspan=4, padx=10, pady=(4, 10), sticky="w")

    def _build_tab_model(self):
        f = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["model"] = f

        # Model selection
        ctk.CTkLabel(
            f,
            text="🤖 Aktives Gemini Modell:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w", pady=(0, 4))

        m_opts = [m["name"] for m in AVAILABLE_MODELS]
        self.model_menu = ctk.CTkOptionMenu(
            f,
            values=m_opts,
            variable=self.model_var,
            height=36,
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
        self.model_menu.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            f,
            text="Standard: Gemini 3.8 Flash TTS Engine (Studio-Qualität & Stimmklon-Support)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(0, 16))

        # API Key Section
        key_head = ctk.CTkFrame(f, fg_color="transparent")
        key_head.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            key_head,
            text="🔑 Google AI Studio API-Schlüssel:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(side="left")

        self.key_status_indicator = ctk.CTkLabel(
            key_head,
            text="🟢 Schlüssel aktiv" if get_api_key() else "⚠️ Kein Schlüssel hinterlegt",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color="#10B981" if get_api_key() else M3_ERROR
        )
        self.key_status_indicator.pack(side="right")

        key_row = ctk.CTkFrame(f, fg_color="transparent")
        key_row.pack(fill="x", pady=(0, 4))

        self.key_entry = ctk.CTkEntry(
            key_row,
            show="*",
            height=36,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT,
            fg_color=("#FFFFFF", "#0E1A18"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        current_k = get_api_key()
        if current_k:
            self.key_entry.insert(0, current_k)

        self.key_show_btn = ctk.CTkButton(
            key_row,
            text="👁️",
            command=self._toggle_key_visibility,
            width=38,
            height=36,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=M3_SURFACE_CONTAINER,
            hover_color=M3_SURFACE_CONTAINER_HIGH,
            text_color=COLOR_PRIMARY_TEXT
        )
        self.key_show_btn.pack(side="left", padx=(0, 8))

        self.test_conn_btn = ctk.CTkButton(
            key_row,
            text="Verbindung testen",
            command=self._test_api_key,
            height=36,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=M3_SURFACE_CONTAINER,
            hover_color=M3_PRIMARY_CONTAINER,
            text_color=COLOR_PRIMARY_TEXT,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        self.test_conn_btn.pack(side="left")

        ctk.CTkLabel(
            f,
            text="Der Schlüssel wird sicher lokal in deiner Windows-Benutzerkonfiguration (.env) gespeichert.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w", pady=(0, 16))

        # Auto-Update Box
        up_box = ctk.CTkFrame(
            f,
            fg_color=M3_SURFACE_CONTAINER,
            corner_radius=14,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        up_box.pack(fill="x", pady=(0, 6))

        up_content = ctk.CTkFrame(up_box, fg_color="transparent")
        up_content.pack(fill="x", padx=14, pady=12)

        up_text_col = ctk.CTkFrame(up_content, fg_color="transparent")
        up_text_col.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            up_text_col,
            text="Automatische Updates beim Start",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        ).pack(anchor="w")

        ctk.CTkLabel(
            up_text_col,
            text="Prüft im Hintergrund automatisch auf neue Versionen von Gemini TTS Studio.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_MUTED_TEXT
        ).pack(anchor="w")

        self.auto_up_switch = ctk.CTkSwitch(
            up_content,
            text="",
            variable=self.auto_update_var,
            progress_color=M3_PRIMARY[0]
        )
        self.auto_up_switch.pack(side="right")

    def _switch_tab(self, tab_name: str):
        self.current_tab = tab_name
        for name, frame in self.tab_frames.items():
            if name == tab_name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        for name, btn in self.tab_buttons.items():
            if name == tab_name:
                btn.configure(
                    fg_color=M3_PRIMARY,
                    hover_color=M3_PRIMARY_HOVER,
                    text_color=("#FFFFFF", "#00201C")
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    hover_color=M3_SURFACE_CONTAINER_HIGH,
                    text_color=COLOR_MUTED_TEXT
                )

    def _on_category_changed(self, category: str):
        all_voices = get_all_voices()
        if category == "Alle Stimmen":
            filtered = all_voices
        else:
            filtered = [v for v in all_voices if v.get("category") == category]
        if not filtered:
            filtered = all_voices

        options = [f"{v['id']} ({v['desc'].split('(')[-1].replace(')', '')})" for v in filtered]
        self.voice_menu.configure(values=options)
        if options:
            self.voice_var.set(options[0])
            self._on_voice_changed(options[0])

    def _on_voice_changed(self, choice: str):
        voice_id = choice.split(" (")[0].strip() if " (" in choice else choice.strip()
        for v in get_all_voices():
            if v["id"] == voice_id:
                desc = v.get("desc", "")
                is_custom = (v.get("category") == "🎙️ Eigene / Geklonte Stimmen") or ("(Voice " in choice)
                self.voice_bio_title.configure(text=choice)
                self.voice_desc_lbl.configure(text=desc)
                if is_custom:
                    self.voice_bio_badge.configure(text="Geklont / Custom", fg_color=("#D1FAE5", "#064E3B"), text_color=("#065F46", "#6EE7B7"))
                else:
                    self.voice_bio_badge.configure(text="Gemini Standard", fg_color=M3_SURFACE_CONTAINER_HIGH, text_color=COLOR_MUTED_TEXT)
                break

    def _refresh_voices(self, options: List[str], target_option: Optional[str] = None):
        self.voice_menu.configure(values=options)
        if target_option:
            self.voice_var.set(target_option)
            self._on_voice_changed(target_option)

    def _apply_tone_preset(self, name: str, text: str):
        self.active_style_preset = name
        self.prompt_box.delete("0.0", "end")
        self.prompt_box.insert("0.0", text)

    def _clear_style(self):
        self.active_style_preset = "Standard"
        self.prompt_box.delete("0.0", "end")

    def _save_style_preset(self):
        text = self.prompt_box.get("0.0", "end").strip()
        if not text:
            messagebox.showwarning("Hinweis", "Bitte gib zuerst eine Regieanweisung im Textfeld ein.")
            return
        dialog = ctk.CTkInputDialog(
            text="Name für die neue Stil-Vorlage eingeben:\n(z. B. 'Dokumentation Ruhig', 'Podcast Host')",
            title="Stil-Vorlage speichern"
        )
        name = dialog.get_input()
        if not name or not name.strip():
            return
        name = name.strip()
        save_custom_style(name, text)
        self.active_style_preset = name
        self._refresh_custom_presets_list(select_name=name)
        messagebox.showinfo("Gespeichert", f"Die Vorlage '{name}' wurde erfolgreich gespeichert!")

    def _refresh_custom_presets_list(self, select_name: Optional[str] = None):
        custom_styles = load_custom_styles()
        names = ["-- Gespeicherte Vorlagen --"]
        if custom_styles:
            for k in sorted(custom_styles.keys()):
                names.append(f"⭐ {k}")
        self.custom_preset_menu.configure(values=names)
        if select_name and f"⭐ {select_name}" in names:
            self.custom_style_var.set(f"⭐ {select_name}")
        else:
            self.custom_style_var.set(names[0])

    def _on_custom_style_selected(self, choice: str):
        if choice.startswith("⭐ "):
            raw = choice[2:]
            styles = load_custom_styles()
            if raw in styles:
                self.prompt_box.delete("0.0", "end")
                self.prompt_box.insert("0.0", styles[raw])
                self.active_style_preset = raw

    def _delete_style_preset(self):
        choice = self.custom_style_var.get()
        if not choice.startswith("⭐ "):
            messagebox.showinfo("Hinweis", "Bitte wähle zuerst eine gespeicherte Vorlage (mit ⭐) zum Löschen aus.")
            return
        raw = choice[2:]
        if messagebox.askyesno("Vorlage löschen", f"Möchtest du die Vorlage '{raw}' wirklich entfernen?"):
            delete_custom_style(raw)
            self._refresh_custom_presets_list()
            self._clear_style()
            messagebox.showinfo("Gelöscht", f"Die Vorlage '{raw}' wurde gelöscht.")

    def _apply_format_preset(self, codec: str, bitrate: str, channels: str, faststart: bool, rate: str, label: str):
        self.codec_var.set(codec)
        self.bitrate_var.set(bitrate)
        self.channels_var.set(channels)
        self.faststart_var.set(faststart)
        self.rate_var.set(rate)

    def _toggle_key_visibility(self):
        if self.key_entry.cget("show") == "*":
            self.key_entry.configure(show="")
            self.key_show_btn.configure(text="🔒")
        else:
            self.key_entry.configure(show="*")
            self.key_show_btn.configure(text="👁️")

    def _test_api_key(self):
        k = self.key_entry.get().strip()
        if not k:
            messagebox.showwarning("Hinweis", "Bitte gib zuerst einen API-Schlüssel ein.")
            return
        self.test_conn_btn.configure(state="disabled", text="Teste...")

        def run_test():
            try:
                from google import genai
                client = genai.Client(api_key=k)
                client.models.get(model="gemini-2.5-flash")
                self.after(0, lambda: self._on_key_test_result(True, "Verbindung erfolgreich!"))
            except Exception as e:
                err = str(e)
                if "API_KEY_INVALID" in err or "400" in err:
                    msg = "Ungültiger API-Key."
                else:
                    msg = f"Fehler: {err[:50]}..."
                self.after(0, lambda: self._on_key_test_result(False, msg))

        threading.Thread(target=run_test, daemon=True).start()

    def _on_key_test_result(self, success: bool, msg: str):
        self.test_conn_btn.configure(state="normal", text="Verbindung testen")
        if success:
            self.key_status_indicator.configure(text="🟢 Schlüssel verifiziert", text_color="#10B981")
            messagebox.showinfo("Verbindung erfolgreich", "Der Google AI Studio API-Key ist gültig und funktionsfähig!")
        else:
            self.key_status_indicator.configure(text="❌ Verbindungsfehler", text_color=M3_ERROR)
            messagebox.showerror("Verbindung fehlgeschlagen", f"Test nicht erfolgreich:\n{msg}")

    def _open_voice_studio(self):
        def on_custom_voice_chosen(voice_id: str):
            self.parent_app._refresh_voice_options(select_voice_id=voice_id)
            self.voice_cat_var.set("🎙️ Eigene / Geklonte Stimmen")
            self._on_category_changed("🎙️ Eigene / Geklonte Stimmen")

        VoiceStudioDialog(
            self,
            self.parent_app.tts_service,
            on_voice_selected_callback=on_custom_voice_chosen
        )

    def _reset_defaults(self):
        if messagebox.askyesno("Zurücksetzen", "Möchtest du alle Einstellungen auf die Standardwerte zurücksetzen?"):
            self.voice_cat_var.set("Alle Stimmen")
            self._on_category_changed("Alle Stimmen")
            self.lang_var.set(SUPPORTED_LANGUAGES[0]["name"])
            self.model_var.set(AVAILABLE_MODELS[0]["name"])
            self._apply_tone_preset("Sachlich & Seriös", "Sprich in einem ruhigen, sachlichen und hochprofessionellen Tonfall wie ein erfahrener Nachrichtensprecher. Achte auf präzise Artikulation und deutliche Satzakzente.")
            self._apply_format_preset("aac", "64 kbit/s", "Mono (1)", True, "48.000 Hz", "Web AAC 64k")
            self.auto_update_var.set(True)

    def _save_and_apply(self):
        new_k = self.key_entry.get().strip()
        if new_k and new_k != get_api_key():
            save_api_key(new_k)
            self.parent_app._on_key_saved(new_k)

        # Propagate to parent app
        self.parent_app.voice_category_var.set(self.voice_cat_var.get())
        self.parent_app.voice_var.set(self.voice_var.get())
        self.parent_app.lang_var.set(self.lang_var.get())
        self.parent_app.model_var.set(self.model_var.get())

        self.parent_app.codec_var.set(self.codec_var.get())
        self.parent_app.channels_var.set(self.channels_var.get())
        self.parent_app.rate_var.set(self.rate_var.get())
        self.parent_app.bitrate_var.set(self.bitrate_var.get())
        self.parent_app.faststart_var.set(self.faststart_var.get())

        self.parent_app.system_prompt_text = self.prompt_box.get("0.0", "end").strip()
        self.parent_app.active_style_preset_name = self.active_style_preset
        self.parent_app.auto_update_on_start = self.auto_update_var.get()

        self.parent_app._update_header_status_pills()
        self._on_close()


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
        self.geometry("1020x720")
        self.minsize(860, 540)

        self.tts_service = GeminiTTSService()
        self.player = AudioPlayer()
        self.batch_processor = BatchProcessor()
        self.translation_service = TranslationService()
        self.update_service = UpdateService()
        self.pending_update: Optional[Dict[str, Any]] = None
        self.update_btn: Optional[ctk.CTkButton] = None
        
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

        # Voice & Language State
        self.voice_categories = ["Alle Stimmen", "🎙️ Eigene / Geklonte Stimmen", "⭐ Favoriten & Allrounder", "🇩🇪 Deutsche Stimmen & Rollen", "📖 Erzähler & Storytelling"]
        self.voice_category_var = ctk.StringVar(value="Alle Stimmen")
        all_initial_voices = get_all_voices()
        voice_options = [f"{v['id']} ({v['desc'].split('(')[-1].replace(')', '')})" for v in all_initial_voices]
        self.voice_var = ctk.StringVar(value=voice_options[0] if voice_options else "Erinome (Weiblich)")
        lang_options = [l["name"] for l in SUPPORTED_LANGUAGES]
        self.lang_var = ctk.StringVar(value=lang_options[0] if lang_options else "🇩🇪 Deutsch (Standard)")

        # Model State
        model_options = [m["name"] for m in AVAILABLE_MODELS]
        self.model_var = ctk.StringVar(value=model_options[0] if model_options else "Gemini 3.8 Flash TTS")

        # Directives / System-Prompt State
        self.system_prompt_text = "Sprich in einem ruhigen, sachlichen und hochprofessionellen Tonfall wie ein erfahrener Nachrichtensprecher. Achte auf präzise Artikulation und deutliche Satzakzente."
        self.active_style_preset_name = "Sachlich & Seriös"
        self.style_input = _StyleInputProxy(self)

        # Audio Format State
        self.preset_var = ctk.StringVar(value=list(AUDIO_PRESETS.values())[0]["name"])
        self.codec_var = ctk.StringVar(value="aac")
        self.channels_var = ctk.StringVar(value="Mono (1)")
        self.rate_var = ctk.StringVar(value="48.000 Hz")
        self.bitrate_var = ctk.StringVar(value="64 kbit/s")
        self.faststart_var = ctk.BooleanVar(value=True)

        # Settings & Updater State
        self.auto_update_on_start = True
        self.settings_dialog: Optional[SettingsDialog] = None

        self._build_ui()
        self._setup_player_timer()

        # Keyboard Shortcut: Strg+Enter triggers audio generation
        self.bind_all("<Control-Return>", lambda e: self._start_generation_thread())

        # Start silent background update check after 2 seconds
        threading.Thread(target=self._check_for_updates_background, daemon=True).start()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ------------------ Header Bar ------------------
        self.header_frame = ctk.CTkFrame(self, height=64, corner_radius=0, fg_color=M3_SURFACE)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 10))
        self.header_frame.grid_columnconfigure(1, weight=1)

        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=20, pady=14, sticky="w")

        title_label = ctk.CTkLabel(
            title_box,
            text="🎙️ Gemini TTS Studio",
            font=ctk.CTkFont(family=FONT_FAMILY, size=20, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        title_label.pack(side="left")

        version_badge = ctk.CTkLabel(
            title_box,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=M3_PRIMARY_CONTAINER,
            text_color=M3_ON_PRIMARY_CONTAINER,
            corner_radius=8,
            padx=8,
            pady=2
        )
        version_badge.pack(side="left", padx=(10, 0))

        # Status Pills (Clickable shortcuts to Settings)
        pills_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        pills_frame.grid(row=0, column=1, padx=10, pady=14, sticky="w")

        self.pill_voice = ctk.CTkButton(
            pills_frame,
            text="🗣️ Stimme ▾",
            command=lambda: self._open_settings_dialog("voice"),
            height=32,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=M3_SURFACE_CONTAINER,
            hover_color=M3_SURFACE_CONTAINER_HIGH,
            text_color=COLOR_PRIMARY_TEXT,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        self.pill_voice.pack(side="left", padx=(0, 6))

        self.pill_style = ctk.CTkButton(
            pills_frame,
            text="🎭 Regie ▾",
            command=lambda: self._open_settings_dialog("style"),
            height=32,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=M3_SURFACE_CONTAINER,
            hover_color=M3_SURFACE_CONTAINER_HIGH,
            text_color=COLOR_PRIMARY_TEXT,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        self.pill_style.pack(side="left", padx=(0, 6))

        self.pill_format = ctk.CTkButton(
            pills_frame,
            text="🎵 Format ▾",
            command=lambda: self._open_settings_dialog("format"),
            height=32,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=M3_SURFACE_CONTAINER,
            hover_color=M3_SURFACE_CONTAINER_HIGH,
            text_color=COLOR_PRIMARY_TEXT,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        self.pill_format.pack(side="left")

        # Action Buttons on Right
        actions_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        actions_frame.grid(row=0, column=2, padx=(0, 10), pady=14, sticky="e")

        self.btn_settings = ctk.CTkButton(
            actions_frame,
            text="⚙️ Studio-Einstellungen",
            command=lambda: self._open_settings_dialog("voice"),
            height=36,
            corner_radius=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_PRIMARY_CONTAINER,
            hover_color=("#B6E4DA", "#00645A"),
            text_color=M3_ON_PRIMARY_CONTAINER,
            border_width=0
        )
        self.btn_settings.pack(side="left", padx=(0, 6))

        self.theme_switch = ctk.CTkSwitch(
            self.header_frame,
            text="Dunkelmodus",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT,
            progress_color=M3_PRIMARY[0]
        )
        self.theme_switch.grid(row=0, column=3, padx=20, pady=14, sticky="e")

        self._update_header_status_pills()

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

        # Expressive Quick-Tag Bar (Fast 1-click chip buttons directly above text area)
        quick_tag_bar = ctk.CTkFrame(self.single_text_card, fg_color="transparent")
        quick_tag_bar.pack(fill="x", padx=20, pady=(0, 6))

        ctk.CTkLabel(
            quick_tag_bar,
            text="🎭 Regie-Cues:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=M3_PRIMARY
        ).pack(side="left", padx=(0, 6))

        quick_tags = [
            ("😂 Lachen", "[lachen]"),
            ("😮‍💨 Seufzen", "[seufzen]"),
            ("😮 Einatmen", "[einatmen]"),
            ("🗣️ Räuspern", "[räuspern]"),
            ("🤝 mhm", "[mhm]"),
            ("🤫 Flüstern", "[flüstern]"),
            ("⏸️ Pause", "[Pause]"),
            ("✨ Begeistert", "[begeistert]"),
        ]

        for display, tag_code in quick_tags:
            q_btn = ctk.CTkButton(
                quick_tag_bar,
                text=display,
                command=lambda t=tag_code: self._insert_tag(t),
                height=26,
                corner_radius=13,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                fg_color=M3_SURFACE_CONTAINER,
                hover_color=M3_PRIMARY_CONTAINER,
                text_color=COLOR_PRIMARY_TEXT,
                border_width=1,
                border_color=M3_OUTLINE_VARIANT
            )
            q_btn.pack(side="left", padx=2)

        self.more_tags_menu = ctk.CTkOptionMenu(
            quick_tag_bar,
            values=["+ Mehr Tags ▾", "🤔 [nachdenklich]", "😢 [traurig]", "🐢 [langsam]", "🐇 [schnell]"],
            command=self._on_more_tag_selected,
            height=26,
            width=120,
            corner_radius=13,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            fg_color=M3_SURFACE_CONTAINER,
            button_color=("#D9E3E0", "#243834"),
            button_hover_color=("#C8D7D3", "#304843"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.more_tags_menu.pack(side="left", padx=3)

        # Main text input area (Compact height 165px so everything fits on screen without scrollbar)
        self.text_input = ctk.CTkTextbox(
            self.single_text_card,
            height=165,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            wrap="word",
            corner_radius=14,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT,
            fg_color=("#FFFFFF", "#0E1A18"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.text_input.pack(fill="x", padx=20, pady=(0, 6))
        self.text_input.insert("0.0", "Hallo! Dies ist ein Test mit Gemini 3.8 Flash TTS. [lachen] Es ist wirklich erstaunlich, wie lebendig die Stimme klingt! [flüstern] Kannst du ein Geheimnis für dich behalten?")
        self.text_input.bind("<KeyRelease>", self._update_counters)
        self._update_counters()

        # Integrated Action Footer Bar (Directly inside script card)
        script_footer = ctk.CTkFrame(self.single_text_card, fg_color="transparent")
        script_footer.pack(fill="x", padx=20, pady=(2, 10))

        # Left: Translation checkbox
        self.auto_translate_var = ctk.BooleanVar(value=False)
        self.auto_translate_check = ctk.CTkCheckBox(
            script_footer,
            text="Vor Vertonung übersetzen",
            variable=self.auto_translate_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT,
            fg_color=M3_PRIMARY[0],
            hover_color=M3_PRIMARY_HOVER[0]
        )
        self.auto_translate_check.pack(side="left")

        # Center: Live status indicator
        self.status_lbl = ctk.CTkLabel(
            script_footer,
            text="Bereit zur Sprachgenerierung. (Strg+Enter)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_MUTED_TEXT,
            anchor="w"
        )
        self.status_lbl.pack(side="left", padx=(14, 10))

        # Right: Prominent Generate CTA Button (Merged right into the card!)
        self.generate_btn = ctk.CTkButton(
            script_footer,
            text="⚡ Audio generieren",
            command=self._start_generation_thread,
            width=180,
            height=38,
            corner_radius=19,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=M3_CTA,
            hover_color=M3_CTA_HOVER,
            text_color="#FFFFFF",
            text_color_disabled="#FFFFFF"
        )
        self.generate_btn.pack(side="right")

        # Progress bar directly inside script card
        self.progress_bar = ctk.CTkProgressBar(
            self.single_text_card,
            height=6,
            corner_radius=3,
            progress_color=M3_PRIMARY[0],
            fg_color=M3_SURFACE_CONTAINER
        )
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 6))
        self.progress_bar.set(0.0)
        self.progress_bar.pack_forget()

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

        # ------------------ Action Container (Permanent Slot) ------------------
        self.action_container = ctk.CTkFrame(main_content, fg_color="transparent")
        self.action_container.pack(fill="x", pady=(0, 0))

        # 6A: Single action controls are integrated directly into single_text_card footer
        self.single_action_card = ctk.CTkFrame(self, width=0, height=0)

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
            corner_radius=18,
            fg_color=M3_SURFACE,
            border_width=1.5,
            border_color=M3_OUTLINE_VARIANT
        )
        player_card.pack(fill="x", pady=(0, 6))

        player_header_row = ctk.CTkFrame(player_card, fg_color="transparent")
        player_header_row.pack(fill="x", padx=18, pady=(8, 4))

        player_header = ctk.CTkLabel(
            player_header_row,
            text="🔊 Integrierter Audio-Player & Export",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        player_header.pack(side="left")

        # Row 1: Visual Audio Waveform Canvas Display (Slim 38px)
        waveform_container = ctk.CTkFrame(
            player_card,
            fg_color=M3_SURFACE_CONTAINER,
            corner_radius=12,
            border_width=1,
            border_color=M3_OUTLINE_VARIANT
        )
        waveform_container.pack(fill="x", padx=18, pady=(0, 6))
        waveform_container.grid_columnconfigure(0, weight=1)

        self.waveform_view = WaveformCanvas(
            waveform_container,
            on_seek_callback=self._on_waveform_seek,
            height=38
        )
        self.waveform_view.grid(row=0, column=0, sticky="ew", padx=4, pady=4)

        # Row 2: Unified Controls Row (All playback controls + Export in 1 line!)
        controls_frame = ctk.CTkFrame(player_card, fg_color="transparent")
        controls_frame.pack(fill="x", padx=18, pady=(0, 10))
        controls_frame.grid_columnconfigure(2, weight=1)

        self.play_btn = ctk.CTkButton(
            controls_frame,
            text="▶ Abspielen",
            command=self._toggle_playback,
            width=115,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            state="disabled",
            fg_color=M3_PRIMARY,
            hover_color=M3_PRIMARY_HOVER,
            text_color=("#FFFFFF", "#00201C"),
            text_color_disabled=COLOR_MUTED_TEXT
        )
        self.play_btn.grid(row=0, column=0, padx=(0, 6))

        self.stop_btn = ctk.CTkButton(
            controls_frame,
            text="■ Stopp",
            command=self._stop_playback,
            width=80,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            state="disabled",
            fg_color="transparent",
            hover_color=M3_ERROR_HOVER,
            text_color=M3_ERROR,
            text_color_disabled=COLOR_MUTED_TEXT,
            border_width=1.5,
            border_color=M3_ERROR_CONTAINER
        )
        self.stop_btn.grid(row=0, column=1, padx=(0, 10))

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
        self.timeline_slider.grid(row=0, column=2, sticky="ew", padx=8)

        self.timeline_slider.bind("<Button-1>", self._on_slider_press)
        self.timeline_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        # Time label
        self.time_lbl = ctk.CTkLabel(
            controls_frame,
            text="00:00 / 00:00",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_PRIMARY_TEXT
        )
        self.time_lbl.grid(row=0, column=3, padx=(6, 12))

        # Volume control
        vol_box = ctk.CTkFrame(controls_frame, fg_color="transparent")
        vol_box.grid(row=0, column=4, padx=(0, 10))
        ctk.CTkLabel(
            vol_box,
            text="🔊",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLOR_MUTED_TEXT
        ).pack(side="left", padx=(0, 4))
        self.volume_slider = ctk.CTkSlider(
            vol_box,
            from_=0.0,
            to=1.0,
            width=70,
            command=self._on_volume_changed,
            button_color=M3_PRIMARY[0],
            button_hover_color=M3_PRIMARY_HOVER[0],
            progress_color=M3_PRIMARY[0]
        )
        self.volume_slider.set(0.8)
        self.volume_slider.pack(side="left")

        # Export Button (Seamlessly integrated into controls row!)
        self.export_btn = ctk.CTkButton(
            controls_frame,
            text="💾 Speichern...",
            command=self._export_audio,
            height=34,
            corner_radius=17,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=M3_SECONDARY_CONTAINER,
            hover_color=("#BDDFD8", "#24403C"),
            text_color=M3_ON_SECONDARY_CONTAINER,
            text_color_disabled=COLOR_MUTED_TEXT,
            border_width=0,
            state="disabled"
        )
        self.export_btn.grid(row=0, column=5, padx=(4, 0))

    # ------------------ Settings Dialog & Header Status Pills ------------------

    def _open_settings_dialog(self, initial_tab: str = "voice"):
        """Opens or focuses the modern Studio Settings Dialog."""
        if self.settings_dialog and self.settings_dialog.winfo_exists():
            self.settings_dialog.lift()
            self.settings_dialog.focus_force()
            self.settings_dialog._switch_tab(initial_tab)
            return
        self.settings_dialog = SettingsDialog(self, initial_tab=initial_tab)

    def _update_header_status_pills(self):
        """Updates the status pills in the header bar based on current configuration."""
        if not hasattr(self, "pill_voice") or not self.pill_voice.winfo_exists():
            return

        # 1. Voice Pill
        raw_voice = self.voice_var.get()
        short_voice = raw_voice.split(" (")[0].strip() if " (" in raw_voice else raw_voice.strip()
        self.pill_voice.configure(text=f"🗣️ {short_voice} ▾")

        # 2. Style Pill
        style_text = self._get_current_system_prompt()
        if not style_text:
            style_label = "Standard"
        else:
            style_label = getattr(self, "active_style_preset_name", "Regie")
            if not style_label:
                style_label = "Regie"
        self.pill_style.configure(text=f"🎭 {style_label} ▾")

        # 3. Format Pill
        codec_name = self.codec_var.get().replace("libmp3lame", "mp3").replace("pcm_s16le", "wav").upper()
        bitrate_raw = self.bitrate_var.get().replace(" kbit/s", "k").replace(" ", "")
        self.pill_format.configure(text=f"🎵 {codec_name} {bitrate_raw} ▾")

    # ------------------ Mode Switching (Zero Position Shift) ------------------

    def _on_mode_switched(self, mode_value: str):
        """Switches between Single-Text and Batch mode in-place without moving other cards."""
        if "Einzeltext" in mode_value:
            self.current_mode = "single"
            self.batch_card.pack_forget()
            self.batch_action_card.pack_forget()
            self.single_text_card.pack(fill="x", in_=self.input_container, pady=(0, 8))
        else:
            self.current_mode = "batch"
            self.single_text_card.pack_forget()
            self.batch_card.pack(fill="x", in_=self.input_container, pady=(0, 8))
            self.batch_action_card.pack(fill="x", in_=self.action_container, pady=(0, 8))

    def _on_more_tag_selected(self, val: str):
        """Inserts selected tag from the '+ Mehr Tags ▾' dropdown into script."""
        if "[" in val and "]" in val:
            tag = val[val.find("["):val.find("]")+1]
            self._insert_tag(tag)
        self.more_tags_menu.set("+ Mehr Tags ▾")

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
        self.status_lbl.configure(text=f"Übersetze Text nach {selected_lang_name} (Gemini)...", text_color="#38BDF8")

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
        # Uncheck auto-translate so subsequent generation will not re-translate already translated text
        self.auto_translate_var.set(False)
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
        prompt = getattr(self, "system_prompt_text", "").strip()
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

        voice_choice = self._get_selected_voice_id()
        model_id = self._get_selected_model_id()

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
        self._open_settings_dialog("model")

    def _on_key_saved(self, new_key: str):
        self.tts_service.set_api_key(new_key)
        self.translation_service.set_api_key(new_key)
        if hasattr(self, "key_status_btn") and self.key_status_btn and self.key_status_btn.winfo_exists():
            self.key_status_btn.configure(text=self._get_key_status_text())
        messagebox.showinfo("Erfolg", "API-Key wurde erfolgreich gespeichert!")

    # ------------------ Auto-Update Methods ------------------

    def _check_for_updates_background(self):
        """Silently checks for updates in background on launch."""
        time.sleep(1.5)  # Wait for GUI to settle
        try:
            update_info = self.update_service.check_for_updates()
            if update_info and update_info.get("update_available"):
                self.pending_update = update_info
                self.after(0, lambda: self._show_update_badge(update_info))
                self.after(600, lambda: self._open_update_dialog(update_info))
        except Exception as e:
            print(f"[Updater] Fehler bei Update-Prüfung: {e}")

    def _show_update_badge(self, update_info: Dict[str, Any]):
        """Renders an eye-catching update button in the header bar."""
        if self.update_btn and self.update_btn.winfo_exists():
            self.update_btn.grid()
            return

        latest_ver = update_info.get("latest_version", "")
        self.update_btn = ctk.CTkButton(
            self.header_frame,
            text=f"✨ Update {latest_ver} verfügbar",
            command=lambda: self._open_update_dialog(update_info),
            height=36,
            corner_radius=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="#D97706",  # Warm Amber CTA
            hover_color="#B45309",
            text_color="#FFFFFF",
            border_width=0
        )
        self.update_btn.grid(row=0, column=1, padx=(10, 14), pady=14, sticky="e")

    def _open_update_dialog(self, update_info: Dict[str, Any]):
        """Opens the full UpdateDialog."""
        UpdateDialog(self, update_info, self.update_service)

    def _check_for_updates_manual(self):
        """Triggered manually by user from settings."""
        def run_check():
            try:
                update_info = self.update_service.check_for_updates()
                if update_info and update_info.get("update_available"):
                    self.pending_update = update_info
                    self.after(0, lambda: self._show_update_badge(update_info))
                    self.after(100, lambda: self._open_update_dialog(update_info))
                else:
                    self.after(0, lambda: messagebox.showinfo(
                        "Kein Update verfügbar",
                        f"Du nutzt bereits die neueste Version von Gemini TTS Studio (v{APP_VERSION})."
                    ))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(
                    "Update-Prüfung",
                    f"Fehler bei der Verbindung zu GitHub: {e}"
                ))

        threading.Thread(target=run_check, daemon=True).start()

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
        self.text_input.insert("insert", f"{tag} ")
        self.text_input.focus_set()
        self._update_counters()

    def _get_selected_voice_id(self) -> str:
        raw = self.voice_var.get()
        if " (" in raw:
            return raw.split(" (")[0].strip()
        return raw.strip()

    def _get_selected_model_id(self) -> str:
        selected_model_name = self.model_var.get()
        for m in AVAILABLE_MODELS:
            if m["name"] == selected_model_name:
                return m["id"]
        return AVAILABLE_MODELS[0]["id"]

    def _open_voice_studio_dialog(self):
        def on_voice_selected(voice_id: str):
            self._refresh_voice_options(select_voice_id=voice_id)

        VoiceStudioDialog(self, self.tts_service, on_voice_selected)

    def _refresh_voice_options(self, select_voice_id: Optional[str] = None):
        all_voices = get_all_voices()
        category = self.voice_category_var.get()
        if category == "Alle Stimmen":
            filtered = all_voices
        else:
            filtered = [v for v in all_voices if v.get("category") == category]

        if not filtered:
            filtered = all_voices
            self.voice_category_var.set("Alle Stimmen")

        options = [f"{v['id']} ({v['desc'].split('(')[-1].replace(')', '')})" for v in filtered]
        self.voice_menu.configure(values=options)

        target_option = None
        if select_voice_id:
            for opt in options:
                if opt.startswith(select_voice_id + " ") or opt == select_voice_id or select_voice_id in opt:
                    target_option = opt
                    break

        if not target_option and options:
            target_option = options[0]

        if target_option:
            self.voice_var.set(target_option)
            self._on_voice_changed(target_option)

    def _on_voice_changed(self, choice: str):
        voice_id = self._get_selected_voice_id()
        for v in get_all_voices():
            if v["id"] == voice_id:
                self.voice_desc_lbl.configure(text=v["desc"])
                break

    def _on_voice_category_changed(self, category: str):
        all_voices = get_all_voices()
        if category == "Alle Stimmen":
            filtered = all_voices
        else:
            filtered = [v for v in all_voices if v.get("category") == category]

        if not filtered:
            filtered = all_voices

        options = [f"{v['id']} ({v['desc'].split('(')[-1].replace(')', '')})" for v in filtered]
        self.voice_menu.configure(values=options)
        if options:
            self.voice_var.set(options[0])
            self._on_voice_changed(options[0])

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

        # Safely capture GUI variables on the main thread
        auto_translate = bool(self.auto_translate_var.get())
        selected_lang_name = self.lang_var.get()
        lang_id = "auto"
        for l in SUPPORTED_LANGUAGES:
            if l["name"] == selected_lang_name:
                lang_id = l["id"]
                break

        # If user checked auto-translate, require selecting a concrete target language
        if auto_translate and lang_id == "auto":
            messagebox.showwarning(
                "Zielsprache wählen",
                "Du hast die automatische Übersetzung aktiviert, aber als Sprache '🌐 Automatisch erkennen' gewählt.\n\n"
                "Bitte wähle unter '🌐 Sprache' eine konkrete Zielsprache aus (z. B. Englisch, Französisch, Spanisch etc.)."
            )
            return

        voice_choice = self._get_selected_voice_id()
        model_id = self._get_selected_model_id()

        system_prompt = self._get_current_system_prompt()
        settings = self._get_current_encoding_settings()

        self.is_generating = True
        self.generate_btn.configure(state="disabled", text="⏳ Generiere Audio...")
        self.progress_bar.pack(fill="x", padx=18, pady=(0, 8))
        self.progress_bar.set(0.05)
        self.status_lbl.configure(text="Initialisiere Sprachgenerierung...", text_color="#38BDF8")
        
        thread = threading.Thread(
            target=self._run_generation,
            args=(text, auto_translate, lang_id, selected_lang_name, voice_choice, model_id, system_prompt, settings),
            daemon=True
        )
        thread.start()

    def _update_generation_progress(self, progress_val: float, message: str):
        self.after(0, self._set_progress_ui, progress_val, message)

    def _set_progress_ui(self, progress_val: float, message: str):
        self.progress_bar.set(progress_val)
        self.status_lbl.configure(text=message, text_color="#38BDF8")

    def _sync_translated_text_to_ui(self, translated_text: str, target_lang_name: str):
        """Updates the text_input field after automatic translation so the UI is synchronized with spoken audio."""
        self.text_input.delete("0.0", "end")
        self.text_input.insert("0.0", translated_text)
        self._update_counters()
        # Uncheck auto-translate so subsequent generations won't re-translate already translated text
        self.auto_translate_var.set(False)
        self.status_lbl.configure(
            text=f"✅ Text automatisch nach {target_lang_name} übersetzt. Generiere Sprache...",
            text_color="#10B981"
        )

    def _run_generation(
        self,
        text: str,
        auto_translate: bool,
        lang_id: str,
        selected_lang_name: str,
        voice_choice: str,
        model_id: str,
        system_prompt: Optional[str],
        settings: Dict[str, Any]
    ):
        try:
            start_time = time.time()

            # Automatic translation if checkbox checked and a concrete target language is selected
            if auto_translate and lang_id != "auto":
                self._update_generation_progress(0.08, f"Übersetze Text automatisch nach {selected_lang_name}...")
                translated = self.translation_service.translate_text(text, target_lang_id=lang_id)
                text = translated
                # Immediately sync translated text back into the GUI Skriptfeld
                self.after(0, self._sync_translated_text_to_ui, translated, selected_lang_name)

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
        self.generate_btn.configure(state="normal", text="⚡ Audio generieren")
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
        self.generate_btn.configure(state="normal", text="⚡ Audio generieren")
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
