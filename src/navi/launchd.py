"""
LaunchAgent management for Navi.

Handles installing/uninstalling the macOS LaunchAgent for auto-start on login.
"""

import plistlib
import subprocess
import sys
from pathlib import Path


LAUNCHD_LABEL = "com.navi.voice"
LAUNCHD_DIR = Path.home() / "Library" / "LaunchAgents"
LAUNCHD_PLIST = LAUNCHD_DIR / f"{LAUNCHD_LABEL}.plist"


def get_plist_content() -> dict:
    """Generate the LaunchAgent plist content."""
    python_path = sys.executable
    
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [python_path, "-m", "navi.daemon", "run"],
        "RunAtLoad": True,
        "KeepAlive": {
            "SuccessfulExit": False,  # Restart if it crashes
        },
        "StandardOutPath": str(Path.home() / ".config" / "navi" / "logs" / "navi.log"),
        "StandardErrorPath": str(Path.home() / ".config" / "navi" / "logs" / "navi.log"),
        "EnvironmentVariables": {
            "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
        },
        "ProcessType": "Interactive",  # Higher priority for responsive hotkey
    }


def install_launchd() -> None:
    """Install the LaunchAgent for auto-start."""
    # Ensure directory exists
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Ensure log directory exists
    log_dir = Path.home() / ".config" / "navi" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Unload existing if present
    if LAUNCHD_PLIST.exists():
        try:
            subprocess.run(
                ["launchctl", "unload", str(LAUNCHD_PLIST)],
                capture_output=True,
            )
        except Exception:
            pass
    
    # Write plist file
    plist_content = get_plist_content()
    with open(LAUNCHD_PLIST, "wb") as f:
        plistlib.dump(plist_content, f)
    
    # Load the agent
    subprocess.run(
        ["launchctl", "load", str(LAUNCHD_PLIST)],
        check=True,
    )


def uninstall_launchd() -> None:
    """Uninstall the LaunchAgent."""
    if not LAUNCHD_PLIST.exists():
        return
    
    # Unload the agent
    try:
        subprocess.run(
            ["launchctl", "unload", str(LAUNCHD_PLIST)],
            capture_output=True,
        )
    except Exception:
        pass
    
    # Remove plist file
    LAUNCHD_PLIST.unlink(missing_ok=True)


def is_launchd_installed() -> bool:
    """Check if the LaunchAgent is installed."""
    return LAUNCHD_PLIST.exists()


def is_launchd_running() -> bool:
    """Check if the LaunchAgent is currently loaded and running."""
    try:
        result = subprocess.run(
            ["launchctl", "list", LAUNCHD_LABEL],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False
