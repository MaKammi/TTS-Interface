"""
PyInstaller Build Script for Gemini TTS Studio
Creates a standalone Windows Executable (.exe) with automatic lock detection
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"


def build_executable():
    print("=== Building Gemini TTS Studio Windows Executable ===")

    (BASE_DIR / "output").mkdir(exist_ok=True)
    (BASE_DIR / "temp").mkdir(exist_ok=True)
    DIST_DIR.mkdir(exist_ok=True)

    # Check if existing exe is locked by a running instance
    target_exe = DIST_DIR / "GeminiTTSStudio.exe"
    exe_name = "GeminiTTSStudio"

    if target_exe.exists():
        try:
            # Test if writable
            with open(target_exe, "a+b") as f:
                pass
        except PermissionError:
            print("[!] GeminiTTSStudio.exe ist aktuell geoeffnet. Erstelle alternative Datei...")
            exe_name = "GeminiTTSStudio_Update"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        f"--name={exe_name}",
        "--noconsole",
        "--onefile",
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
        produced_exe = DIST_DIR / f"{exe_name}.exe"
        if produced_exe.exists():
            print("\n=======================================================")
            print("[+] Build SUCCESSFUL!")
            print(f"Ausfuehrbare Datei erstellt unter:")
            print(f"Path: {produced_exe.resolve()}")
            print(f"Dateigroesse: {produced_exe.stat().st_size / (1024 * 1024):.1f} MB")
            print("=======================================================")
            return True
    
    print("\n[-] Build fehlgeschlagen!")
    return False


if __name__ == "__main__":
    build_executable()
