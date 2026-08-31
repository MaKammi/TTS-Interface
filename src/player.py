"""
Audio player module using pygame.mixer with support for WAV/MP3/M4A/MP4 playback.
"""

import os
import time
import wave
from pathlib import Path
from typing import Optional, Callable
import pygame

from .audio_converter import convert_audio
from .config import TEMP_DIR


class AudioPlayer:
    """Audio player for previewing generated audio files."""

    def __init__(self):
        self._is_initialized = False
        self._current_file: Optional[Path] = None
        self._playback_file: Optional[Path] = None
        self._is_playing = False
        self._is_paused = False
        self._duration: float = 0.0
        self._start_time: float = 0.0
        self._pause_time: float = 0.0
        self._elapsed_offset: float = 0.0
        self._volume: float = 0.8
        self._init_mixer()

    def _init_mixer(self):
        """Safely initialize pygame mixer."""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            pygame.mixer.music.set_volume(self._volume)
            self._is_initialized = True
        except Exception as e:
            print(f"Warnung: Audio Mixer konnte nicht initialisiert werden: {e}")
            self._is_initialized = False

    def load(self, file_path: Path | str):
        """Load an audio file for playback."""
        if not self._is_initialized:
            self._init_mixer()

        self.stop()
        src_path = Path(file_path).resolve()
        if not src_path.exists():
            raise FileNotFoundError(f"Audiodatei nicht gefunden: {src_path}")

        self._current_file = src_path
        ext = src_path.suffix.lower()

        # Pygame mixer plays WAV, OGG, and MP3 natively.
        # For MP4 / M4A containers, convert a temporary WAV/OGG copy for lossless player preview
        if ext in [".mp4", ".m4a", ".aac"]:
            temp_preview_wav = TEMP_DIR / f"preview_{src_path.stem}.wav"
            try:
                convert_audio(
                    input_file=src_path,
                    output_file=temp_preview_wav,
                    codec="pcm_s16le",
                    channels=2,
                    sample_rate=44100,
                    bitrate=None,
                    faststart=False
                )
                self._playback_file = temp_preview_wav
            except Exception:
                # Fallback to direct load attempt
                self._playback_file = src_path
        else:
            self._playback_file = src_path

        # Determine audio duration
        self._duration = self._calculate_duration(self._playback_file)

        try:
            pygame.mixer.music.load(str(self._playback_file))
        except Exception as e:
            raise RuntimeError(f"Konnte Audiodatei nicht laden: {e}")

    def _calculate_duration(self, path: Path) -> float:
        """Calculate duration of audio file in seconds."""
        try:
            if path.suffix.lower() == ".wav":
                with wave.open(str(path), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    return frames / float(rate)
            # Pygame Sound object can give length for mp3/wav
            sound = pygame.mixer.Sound(str(path))
            return sound.get_length()
        except Exception:
            return 0.0

    def play(self):
        """Start or restart audio playback."""
        if not self._playback_file:
            return
        if not self._is_initialized:
            self._init_mixer()

        try:
            pygame.mixer.music.play()
            self._is_playing = True
            self._is_paused = False
            self._start_time = time.time()
            self._elapsed_offset = 0.0
        except Exception as e:
            print(f"Fehler bei der Audiowiedergabe: {e}")

    def pause(self):
        """Pause playback."""
        if self._is_playing and not self._is_paused:
            pygame.mixer.music.pause()
            self._is_paused = True
            self._pause_time = time.time()

    def resume(self):
        """Resume paused playback."""
        if self._is_playing and self._is_paused:
            pygame.mixer.music.unpause()
            self._is_paused = False
            self._start_time += (time.time() - self._pause_time)

    def toggle_play_pause(self):
        """Toggle between play, pause, and resume."""
        if not self._is_playing:
            self.play()
        elif self._is_paused:
            self.resume()
        else:
            self.pause()

    def stop(self):
        """Stop playback completely."""
        if self._is_initialized and pygame.mixer.get_init():
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self._is_playing = False
        self._is_paused = False
        self._start_time = 0.0
        self._elapsed_offset = 0.0

    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        self._volume = max(0.0, min(1.0, volume))
        if self._is_initialized and pygame.mixer.get_init():
            pygame.mixer.music.set_volume(self._volume)

    def get_volume(self) -> float:
        return self._volume

    def get_position(self) -> float:
        """Get current playback position in seconds."""
        if not self._is_playing:
            return 0.0
        if self._is_paused:
            return max(0.0, min(self._duration, self._pause_time - self._start_time))
        
        # Check if music finished playing
        if not pygame.mixer.music.get_busy() and not self._is_paused:
            self._is_playing = False
            return self._duration
            
        pos = time.time() - self._start_time
        return max(0.0, min(self._duration, pos))

    def get_duration(self) -> float:
        return self._duration

    def is_playing(self) -> bool:
        if self._is_playing and not self._is_paused:
            if not pygame.mixer.music.get_busy():
                self._is_playing = False
        return self._is_playing

    def is_paused(self) -> bool:
        return self._is_paused
