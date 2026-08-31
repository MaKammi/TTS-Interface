"""
Verification script for Gemini TTS API and FFmpeg conversion
"""

import os
import sys
from pathlib import Path

# Ensure root on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.tts_service import GeminiTTSService
from src.audio_converter import convert_audio, get_ffmpeg_path
from src.config import OUTPUT_DIR, AUDIO_PRESETS


def test_tts_and_conversion():
    print("=== Testing FFmpeg Location ===")
    ffmpeg_exe = get_ffmpeg_path()
    print(f"FFmpeg binary: {ffmpeg_exe}")

    print("\n=== Testing Gemini TTS Audio Generation ===")
    service = GeminiTTSService()
    test_text = "Hallo! [lachen] Das ist ein automatisierter Test des Gemini TTS Interfaces. [flüstern] Alles funktioniert hervorragend!"
    
    print(f"Generating speech for text: {test_text}")
    wav_path = service.generate_speech(
        text=test_text,
        voice_name="Puck",
        model="gemini-2.5-flash-preview-tts",
        language="de"
    )
    print(f"Generated WAV file: {wav_path} (Size: {wav_path.stat().st_size} bytes)")

    print("\n=== Testing FFmpeg Conversion to AAC-LC Mono 64k FastStart MP4 ===")
    output_mp4 = OUTPUT_DIR / "test_output.mp4"
    preset = AUDIO_PRESETS["web_aac_mono_64k"]
    
    converted_path = convert_audio(
        input_file=wav_path,
        output_file=output_mp4,
        codec=preset["codec"],
        channels=preset["channels"],
        sample_rate=preset["sample_rate"],
        bitrate=preset["bitrate"],
        faststart=preset["faststart"]
    )
    print(f"Converted MP4 file: {converted_path} (Size: {converted_path.stat().st_size} bytes)")

    print("\n=== Verification Successful! ===")


if __name__ == "__main__":
    test_tts_and_conversion()
