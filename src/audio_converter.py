"""
Audio converter module using FFmpeg
"""

import subprocess
import shutil
import os
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import imageio_ffmpeg
    IMAGEIO_FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    IMAGEIO_FFMPEG_EXE = None


def get_ffmpeg_path() -> str:
    """Find FFmpeg binary (imageio-ffmpeg bundle or system PATH)."""
    if IMAGEIO_FFMPEG_EXE and os.path.exists(IMAGEIO_FFMPEG_EXE):
        return IMAGEIO_FFMPEG_EXE
    
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    
    raise RuntimeError(
        "FFmpeg wurde nicht gefunden. Bitte installiere FFmpeg oder imageio-ffmpeg."
    )


def convert_audio(
    input_file: Path | str,
    output_file: Path | str,
    codec: str = "aac",
    channels: int = 1,
    sample_rate: int = 44100,
    bitrate: Optional[str] = "64k",
    faststart: bool = True,
) -> Path:
    """
    Convert an audio file to target format with specified encoding parameters.
    
    Default parameters adhere to web-streaming standard:
    - Codec: AAC (AAC-LC)
    - Channels: 1 (Mono)
    - Sample rate: 44100 Hz
    - Bitrate: 64 kbit/s
    - Container: MP4/M4A with +faststart
    """
    ffmpeg_exe = get_ffmpeg_path()
    input_path = Path(input_file).resolve()
    output_path = Path(output_file).resolve()
    
    if not input_path.exists():
        raise FileNotFoundError(f"Eingabedatei nicht gefunden: {input_path}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Build FFmpeg command arguments
    cmd = [
        ffmpeg_exe,
        "-y",               # Overwrite output
        "-i", str(input_path),
        "-c:a", codec,
        "-ac", str(channels),
        "-ar", str(sample_rate),
    ]
    
    # Add bitrate if applicable
    if bitrate and codec != "pcm_s16le":
        cmd.extend(["-b:a", str(bitrate)])
    
    # Add FastStart flag for MP4/M4A containers
    ext = output_path.suffix.lower()
    if faststart and ext in [".mp4", ".m4a", ".mov"]:
        cmd.extend(["-movflags", "+faststart"])
    
    cmd.append(str(output_path))
    
    # Run FFmpeg conversion
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg Fehler beim Konvertieren: {process.stderr}")
    
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Ausgabedatei wurde nicht erfolgreich erstellt: {output_path}")
    
    return output_path


def get_command_preview(
    input_file: str = "eingabe.wav",
    output_file: str = "ausgabe.mp4",
    codec: str = "aac",
    channels: int = 1,
    sample_rate: int = 44100,
    bitrate: Optional[str] = "64k",
    faststart: bool = True
) -> str:
    """Generate the human-readable FFmpeg command string for display."""
    ext = Path(output_file).suffix.lower()
    flags = f"-c:a {codec}"
    if bitrate and codec != "pcm_s16le":
        flags += f" -b:a {bitrate}"
    flags += f" -ac {channels} -ar {sample_rate}"
    if faststart and ext in [".mp4", ".m4a"]:
        flags += " -movflags +faststart"
    return f"ffmpeg -i {input_file} {flags} {output_file}"
