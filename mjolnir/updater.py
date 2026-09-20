"""
mjolnir/updater.py - Native GitHub Release Auto-Updater.
Checks GitHub Releases, downloads installer, and launches silent in-place upgrade.
"""

import sys
import os
import json
import urllib.request
import subprocess
from packaging import version
from PySide6.QtCore import Signal, QThread

CURRENT_VERSION = "2.2.0"
REPO_API_URL = "https://api.github.com/repos/Om12-0/plethora-mjolnir/releases/latest"

class UpdateCheckWorker(QThread):
    update_available = Signal(str, str, str)  # (version, download_url, release_notes)
    no_update = Signal()
    error_occurred = Signal(str)

    def run(self):
        try:
            req = urllib.request.Request(
                REPO_API_URL,
                headers={"User-Agent": "Plethora-Mjolnir-Updater"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())

            tag_name = data.get("tag_name", "").lstrip("v")
            if not tag_name:
                self.no_update.emit()
                return

            if version.parse(tag_name) > version.parse(CURRENT_VERSION):
                download_url = None
                for asset in data.get("assets", []):
                    if asset.get("name", "").endswith(".exe"):
                        download_url = asset.get("browser_download_url")
                        break

                body = data.get("body", "No release notes provided.")
                if download_url:
                    self.update_available.emit(tag_name, download_url, body)
                else:
                    self.no_update.emit()
            else:
                self.no_update.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))

def perform_silent_upgrade(download_url: str):
    """Downloads the installer to %TEMP% and runs it silently."""
    try:
        temp_installer = os.path.join(os.environ["TEMP"], "Plethora-Mjolnir-Update.exe")
        urllib.request.urlretrieve(download_url, temp_installer)

        # Silent Inno Setup install flags
        cmd = f'"{temp_installer}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART'
        subprocess.Popen(cmd, shell=True)
        sys.exit(0)
    except Exception as e:
        print(f"[ERR] Upgrade failed: {e}")
