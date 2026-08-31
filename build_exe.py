"""
PyInstaller Build Script for Gemini TTS Studio
Creates a standalone Windows Executable (.exe)
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"


def build_executable():
    print("=== Building Gemini TTS Studio Windows Executable ===")

    # Ensure output and temp directories exist
    (BASE_DIR / "output").mkdir(exist_ok=True)
    (BASE_DIR / "temp").mkdir(exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=GeminiTTSStudio",
        "--noconsole",          # Windows GUI application (no black command window)
        "--onefile",            # Standalone single .exe
        "--clean",
        "--collect-all=customtkinter",
        "--collect-all=imageio_ffmpeg",
        "--collect-all=pygame",
        "--add-data=.env.example;.",
        "main.py"
    ]

    print(f"Running PyInstaller command:\n{' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    
    if result.returncode == 0:
        exe_path = DIST_DIR / "GeminiTTSStudio.exe"
        if exe_path.exists():
            print("\n=======================================================")
            print("[+] Build SUCCESSFUL!")
            print(f"Ausfuehrbare Datei erstellt unter:")
            print(f"Path: {exe_path.resolve()}")
            print(f"Dateigroesse: {exe_path.stat().st_size / (1024 * 1024):.1f} MB")
            print("=======================================================")
            return True
    
    print("\n[-] Build fehlgeschlagen!")
    return False


if __name__ == "__main__":
    build_executable()
