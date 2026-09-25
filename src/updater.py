"""
Auto-Update Service for Gemini TTS Studio
Checks GitHub Releases for newer versions, downloads update assets,
and performs seamless in-place updates with automatic restart on Windows.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import urllib.request
import urllib.error

from .config import BASE_DIR, TEMP_DIR, APP_VERSION, GITHUB_REPO, get_api_key


def parse_semver(version_str: str) -> tuple:
    """Parse a version string (e.g. 'v2.1.0' or '2.1.0') into a tuple of ints."""
    clean = re.sub(r'^[vV]', '', version_str.strip())
    # Extract numeric components
    match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', clean)
    if not match:
        return (0, 0, 0)
    major = int(match.group(1) or 0)
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    return (major, minor, patch)


def is_newer_version(remote_version: str, local_version: str) -> bool:
    """Return True if remote_version is strictly newer than local_version."""
    remote_tuple = parse_semver(remote_version)
    local_tuple = parse_semver(local_version)
    return remote_tuple > local_tuple


def format_release_notes(raw_notes: str) -> str:
    """Format GitHub release markdown into clean, beautiful human-readable text."""
    if not raw_notes:
        return "Keine Versionshinweise hinterlegt."

    lines = raw_notes.replace("\r\n", "\n").split("\n")
    cleaned_lines = []
    for line in lines:
        indent_level = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue

        def clean_md(text: str) -> str:
            # [Link text](url) -> Link text
            text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
            # **bold** or __bold__ -> bold
            text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
            # *italic* or _italic_ -> italic
            text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
            # `code` -> code
            text = re.sub(r"`(.*?)`", r"\1", text)
            return text

        # Headings
        if stripped.startswith("#### "):
            cleaned_lines.append(f"🔹 {clean_md(stripped[5:].strip())}\n")
            continue
        elif stripped.startswith("### "):
            cleaned_lines.append(f"📌 {clean_md(stripped[4:].strip())}\n")
            continue
        elif stripped.startswith("## "):
            cleaned_lines.append(f"📢 {clean_md(stripped[3:].strip())}\n")
            continue
        elif stripped.startswith("# "):
            cleaned_lines.append(f"🚀 {clean_md(stripped[2:].strip())}\n")
            continue

        # List items (- or *)
        if stripped.startswith("- ") or stripped.startswith("* "):
            content = clean_md(stripped[2:].strip())
            indent_prefix = "      " if indent_level >= 2 else "   "
            bullet = "– " if indent_level >= 2 else "• "
            cleaned_lines.append(f"{indent_prefix}{bullet}{content}")
            continue

        cleaned_lines.append(clean_md(stripped))

    res = "\n".join(cleaned_lines)
    res = re.sub(r"\n{3,}", "\n\n", res)
    return res.strip()


class UpdateService:
    """Handles GitHub release querying, downloading, and restarting."""

    def __init__(self, repo: str = GITHUB_REPO, current_version: str = APP_VERSION):
        self.repo = repo
        self.current_version = current_version
        self.github_token = self._resolve_github_token()

    def _resolve_github_token(self) -> str:
        token = os.getenv("GITHUB_TOKEN", os.getenv("GH_TOKEN", ""))
        if token:
            return token.strip()
        # Fallback to local gh CLI if available (e.g. developer environment)
        try:
            import shutil
            if shutil.which("gh"):
                out = subprocess.check_output(["gh", "auth", "token"], timeout=3, stderr=subprocess.DEVNULL)
                t = out.decode("utf-8").strip()
                if t and t.startswith("gh"):
                    return t
        except Exception:
            pass
        return ""

    def check_for_updates(self, custom_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Check GitHub Releases for a newer version.
        Returns a dict with update info if a newer version is found, or None.
        """
        token = custom_token or self.github_token
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"GeminiTTSStudio-Updater/{self.current_version}"
        }
        if token:
            headers["Authorization"] = f"token {token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status != 200:
                    return None
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, Exception):
            # Gracefully handle private repos, offline state, or 404
            return None

        tag_name = data.get("tag_name", "")
        if not tag_name:
            return None

        if not is_newer_version(tag_name, self.current_version):
            return {
                "update_available": False,
                "current_version": self.current_version,
                "latest_version": tag_name,
                "release_name": data.get("name", tag_name),
                "release_notes": data.get("body", "")
            }

        # Look for executable asset
        assets = data.get("assets", [])
        exe_asset = None
        for asset in assets:
            name = asset.get("name", "").lower()
            if name.endswith(".exe") or name.endswith(".zip"):
                exe_asset = asset
                if "geminittsstudio" in name:
                    break

        download_url = exe_asset.get("browser_download_url", "") if exe_asset else data.get("html_url", "")
        asset_name = exe_asset.get("name", "GeminiTTSStudio.exe") if exe_asset else "GeminiTTSStudio.exe"
        size_bytes = exe_asset.get("size", 0) if exe_asset else 0

        return {
            "update_available": True,
            "current_version": self.current_version,
            "latest_version": tag_name,
            "release_name": data.get("name", tag_name),
            "release_notes": data.get("body", ""),
            "download_url": download_url,
            "asset_url": exe_asset.get("url", "") if exe_asset else "",
            "asset_name": asset_name,
            "size_bytes": size_bytes,
            "html_url": data.get("html_url", f"https://github.com/{self.repo}/releases")
        }

    def download_update(
        self,
        download_url: str,
        asset_url: str = "",
        custom_token: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[Path]:
        """
        Download the update executable to TEMP_DIR.
        Supports both public browser_download_url and authenticated private asset_url.
        """
        token = custom_token or self.github_token
        TEMP_DIR.mkdir(exist_ok=True)
        dest_file = TEMP_DIR / "GeminiTTSStudio_Update.exe"

        headers = {
            "User-Agent": f"GeminiTTSStudio-Updater/{self.current_version}"
        }

        # For private repositories, asset download requires octet-stream accept header
        if token and asset_url:
            request_url = asset_url
            headers["Authorization"] = f"token {token}"
            headers["Accept"] = "application/octet-stream"
        else:
            request_url = download_url

        try:
            req = urllib.request.Request(request_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 65536  # 64 KB

                with open(dest_file, "wb") as f_out:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            fraction = downloaded / total_size if total_size > 0 else 0.5
                            mb_down = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024) if total_size > 0 else 0
                            status = f"{mb_down:.1f} MB / {mb_total:.1f} MB" if total_size > 0 else f"{mb_down:.1f} MB"
                            progress_callback(fraction, status)

            if dest_file.exists() and dest_file.stat().st_size > 10000:
                return dest_file
            return None
        except Exception as e:
            if dest_file.exists():
                try:
                    dest_file.unlink()
                except Exception:
                    pass
            print(f"[!] Update download error: {e}")
            return None

    def apply_update_and_restart(self, new_exe_path: Path) -> bool:
        """
        Replace running executable and restart.
        On Windows, a running exe is locked. We spawn a detached batch script
        that waits for this process PID to terminate, overwrites the EXE, and restarts it.
        Clears PyInstaller internal environment variables to prevent 'Security validation failure'.
        """
        is_frozen = getattr(sys, "frozen", False)
        
        if not is_frozen:
            # Running as python script
            print(f"[*] Update heruntergeladen: {new_exe_path}")
            return False

        current_exe = Path(sys.executable).resolve()
        current_pid = os.getpid()

        # Batch script template to perform swap
        updater_bat = TEMP_DIR / "run_update.bat"
        bat_content = f"""@echo off
chcp 65001 >nul
echo [Gemini TTS Studio] Aktualisiere Anwendung auf neue Version...
set OLD_PID={current_pid}
set NEW_EXE="{new_exe_path.resolve()}"
set TARGET_EXE="{current_exe.resolve()}"

:wait_pid
timeout /t 1 /nobreak >nul
tasklist /fi "PID eq %OLD_PID%" | findstr /i "%OLD_PID%" >nul
if not errorlevel 1 goto wait_pid

:: Give PyInstaller bootloader parent process extra time to release file lock
timeout /t 2 /nobreak >nul

set RETRIES=0
:try_copy
echo [Gemini TTS Studio] Ersetze ausfuehrbare Datei...
copy /y %NEW_EXE% %TARGET_EXE% >nul 2>&1
if errorlevel 1 (
    set /a RETRIES+=1
    if %RETRIES% leq 10 (
        timeout /t 1 /nobreak >nul
        goto try_copy
    )
)

del /f /q %NEW_EXE% >nul 2>&1

:: Clear all PyInstaller bootloader environment variables!
:: Otherwise child process fails security validation check
for /f "tokens=1 delims==" %%v in ('set _PYI 2^>nul') do set %%v=
for /f "tokens=1 delims==" %%v in ('set _MEI 2^>nul') do set %%v=
for /f "tokens=1 delims==" %%v in ('set PYINSTALLER 2^>nul') do set %%v=
set _PYI_PARENT_PROCESS_LEVEL=
set _PYI_APPLICATION_HOME_DIR=
set _PYI_ARCHIVE_FILE=
set _PYI_SPLASH_IPC=
set _MEIPASS2=
set _MEIPASS=
set PYINSTALLER_STRICT_UNPACK_MODE=
set PYINSTALLER_RESET_ENVIRONMENT=

echo [Gemini TTS Studio] Starte neue Version...
cd /d "{current_exe.parent.resolve()}"
start "" %TARGET_EXE%

(goto) 2>nul & del "%~f0"
"""
        with open(updater_bat, "w", encoding="utf-8") as f:
            f.write(bat_content)

        # Launch detached updater script with sanitized environment
        clean_env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("_PYI") and not k.startswith("_MEI") and not k.startswith("PYINSTALLER")
        }

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # CREATE_NO_WINDOW

        subprocess.Popen(
            ["cmd.exe", "/c", str(updater_bat.resolve())],
            creationflags=creation_flags,
            env=clean_env,
            close_fds=True
        )

        # Exit current process immediately
        sys.exit(0)

