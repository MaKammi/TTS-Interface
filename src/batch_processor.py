"""
Batch Processing Engine for Gemini TTS Studio
Manages document queuing, chapter splitting, multi-file sequential TTS generation, and progress events.
"""

import time
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Callable, Dict, Any

from .document_parser import extract_text_from_file, split_into_chapters
from .tts_service import GeminiTTSService
from .audio_converter import convert_audio
from .config import OUTPUT_DIR, TEMP_DIR


@dataclass
class BatchItem:
    """Represents a single audio generation task in the batch queue."""
    id: str
    source_file: Path
    title: str
    text: str
    char_count: int
    word_count: int
    status: str = "Wartend"
    progress: float = 0.0
    output_audio: Optional[Path] = None
    error_msg: Optional[str] = None


class BatchProcessor:
    """Manages queuing and processing of multiple files / chapters."""

    def __init__(self):
        self.items: List[BatchItem] = []
        self.is_running = False
        self.cancel_requested = False
        self._counter = 1

    def clear_queue(self):
        """Clears the current batch item queue."""
        if not self.is_running:
            self.items.clear()
            self._counter = 1

    def add_file(self, file_path: Path, split_chapters: bool = False) -> List[BatchItem]:
        """
        Parses a document file and adds it (or its chapters) as BatchItems to the queue.
        """
        file_path = Path(file_path)
        extracted_text = extract_text_from_file(file_path)
        if not extracted_text:
            raise ValueError(f"Datei '{file_path.name}' enthält keinen extrahierbaren Text.")

        new_items: List[BatchItem] = []
        base_name = file_path.stem

        if split_chapters:
            chapters = split_into_chapters(extracted_text, default_title=base_name)
            for ch_title, ch_text in chapters:
                if not ch_text.strip():
                    continue
                item_title = f"{base_name}_{ch_title}" if len(chapters) > 1 else base_name
                item = BatchItem(
                    id=str(self._counter),
                    source_file=file_path,
                    title=item_title,
                    text=ch_text,
                    char_count=len(ch_text),
                    word_count=len(ch_text.split()),
                    status="Wartend"
                )
                self.items.append(item)
                new_items.append(item)
                self._counter += 1
        else:
            item = BatchItem(
                id=str(self._counter),
                source_file=file_path,
                title=base_name,
                text=extracted_text,
                char_count=len(extracted_text),
                word_count=len(extracted_text.split()),
                status="Wartend"
            )
            self.items.append(item)
            new_items.append(item)
            self._counter += 1

        return new_items

    def add_folder(self, folder_path: Path, split_chapters: bool = False) -> List[BatchItem]:
        """Scans a directory for supported documents and adds them to the queue."""
        folder_path = Path(folder_path)
        supported_exts = {".txt", ".md", ".pdf", ".docx", ".srt"}
        all_added: List[BatchItem] = []

        for p in sorted(folder_path.iterdir()):
            if p.is_file() and p.suffix.lower() in supported_exts:
                try:
                    items = self.add_file(p, split_chapters=split_chapters)
                    all_added.extend(items)
                except Exception as e:
                    print(f"Warning: Could not parse {p.name}: {e}")

        return all_added

    def remove_item(self, item_id: str):
        """Removes a specific item from the queue."""
        if not self.is_running:
            self.items = [item for item in self.items if item.id != item_id]

    def cancel(self):
        """Signals the batch worker to stop after the current chunk/item."""
        self.cancel_requested = True

    def process_queue(
        self,
        tts_service: GeminiTTSService,
        voice_name: str,
        model: str,
        language: str,
        encoding_settings: Dict[str, Any],
        system_prompt: Optional[str] = None,
        target_languages: Optional[List[str]] = None,
        output_directory: Optional[Path] = None,
        on_item_update: Optional[Callable[[BatchItem], None]] = None,
        on_batch_update: Optional[Callable[[int, int, float], None]] = None,
        on_batch_complete: Optional[Callable[[List[BatchItem]], None]] = None,
    ):
        """
        Executes TTS synthesis and audio conversion for all pending items in the queue sequentially.
        Supports system_prompt and multiple target languages with automatic translation.
        """
        if self.is_running:
            return

        self.is_running = True
        self.cancel_requested = False

        out_dir = output_directory or OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        total_items = len(self.items)
        langs = target_languages if target_languages and len(target_languages) > 0 else [language]

        from .translation_service import TranslationService
        translator = TranslationService()

        def worker():
            for idx, item in enumerate(self.items):
                if self.cancel_requested:
                    item.status = "Abgebrochen ⏹"
                    if on_item_update:
                        on_item_update(item)
                    continue

                if item.status == "Fertig ✅":
                    continue

                clean_title = "".join(c for c in item.title if c.isalnum() or c in (" ", "_", "-")).strip()
                clean_title = clean_title.replace(" ", "_")
                ext = encoding_settings.get("extension", ".mp4")

                last_converted = None

                try:
                    for lang_code in langs:
                        if self.cancel_requested:
                            break

                        # Text to synthesize: translate if target language is specified and not auto/de
                        text_to_speak = item.text
                        lang_suffix = f"_{lang_code}" if len(langs) > 1 else ""

                        if lang_code != "auto" and lang_code != "de":
                            item.status = f"Übersetze nach {lang_code.upper()}..."
                            if on_item_update:
                                on_item_update(item)
                            try:
                                text_to_speak = translator.translate_text(item.text, target_lang_id=lang_code)
                            except Exception as trans_err:
                                print(f"Translation warning: {trans_err}")

                        item.status = f"Generiere Audio ({lang_code.upper()})..."
                        item.progress = 0.10
                        if on_item_update:
                            on_item_update(item)

                        if on_batch_update:
                            on_batch_update(idx + 1, total_items, idx / max(1, total_items))

                        def item_chunk_callback(chunk_prog: float, msg: str):
                            item.progress = max(0.10, min(0.90, chunk_prog * 0.90))
                            if on_item_update:
                                on_item_update(item)

                        # 1. Synthesize RAW WAV with chunking
                        raw_wav = tts_service.generate_speech(
                            text=text_to_speak,
                            voice_name=voice_name,
                            model=model,
                            language=lang_code,
                            system_prompt=system_prompt,
                            progress_callback=item_chunk_callback
                        )

                        if self.cancel_requested:
                            item.status = "Abgebrochen ⏹"
                            if on_item_update:
                                on_item_update(item)
                            break

                        # 2. Convert Audio to target profile
                        item.status = f"Konvertiere ({lang_code.upper()})..."
                        if on_item_update:
                            on_item_update(item)

                        target_file = out_dir / f"{clean_title}{lang_suffix}{ext}"
                        dup_idx = 1
                        while target_file.exists():
                            target_file = out_dir / f"{clean_title}{lang_suffix}_{dup_idx}{ext}"
                            dup_idx += 1

                        converted = convert_audio(
                            input_file=raw_wav,
                            output_file=target_file,
                            codec=encoding_settings.get("codec", "aac"),
                            channels=encoding_settings.get("channels", 1),
                            sample_rate=encoding_settings.get("sample_rate", 44100),
                            bitrate=encoding_settings.get("bitrate", "64k"),
                            faststart=encoding_settings.get("faststart", True)
                        )
                        last_converted = converted

                    if not self.cancel_requested:
                        item.output_audio = last_converted
                        item.status = "Fertig ✅"
                        item.progress = 1.0

                except Exception as e:
                    item.status = "Fehler ❌"
                    item.error_msg = str(e)
                    print(f"Batch Error on item '{item.title}': {e}")

                if on_item_update:
                    on_item_update(item)

                if on_batch_update:
                    on_batch_update(idx + 1, total_items, (idx + 1) / max(1, total_items))

            self.is_running = False
            if on_batch_complete:
                on_batch_complete(self.items)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
