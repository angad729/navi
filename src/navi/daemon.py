"""
Daemon management for Navi.

Handles starting, stopping, and monitoring the background process.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from navi.config import DEFAULT_CONFIG_DIR, load_config


def get_pid_file() -> Path:
    """Get path to PID file."""
    return DEFAULT_CONFIG_DIR / "navi.pid"


def get_log_file() -> Path:
    """Get path to log file."""
    return DEFAULT_CONFIG_DIR / "logs" / "navi.log"


def is_daemon_running() -> bool:
    """Check if the daemon is currently running."""
    pid_file = get_pid_file()
    
    if not pid_file.exists():
        return False
    
    try:
        pid = int(pid_file.read_text().strip())
        # Check if process exists
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        # PID file exists but process doesn't - clean up
        pid_file.unlink(missing_ok=True)
        return False


def start_daemon() -> None:
    """Start the Navi daemon as a background process."""
    if is_daemon_running():
        return
    
    # Ensure log directory exists
    log_file = get_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Start the daemon process
    # We use the entry point to run the actual daemon
    python_path = sys.executable
    
    # Open log file for stdout/stderr (owner-only — may contain note content)
    log = open(log_file, "a")
    try:
        os.chmod(log_file, 0o600)
    except OSError:
        pass

    # Set environment variable to hide Dock icon
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    process = subprocess.Popen(
        [python_path, "-m", "navi.daemon", "run"],
        stdout=log,
        stderr=log,
        start_new_session=True,  # Detach from terminal
        env=env,
    )
    log.close()  # Parent doesn't need the fd; child has its own copy

    # Write PID file
    pid_file = get_pid_file()
    pid_file.write_text(str(process.pid))
    
    # Give it a moment to start
    time.sleep(0.5)


def stop_daemon() -> None:
    """Stop the Navi daemon."""
    pid_file = get_pid_file()
    
    if not pid_file.exists():
        return
    
    try:
        pid = int(pid_file.read_text().strip())
        
        # Send SIGTERM for graceful shutdown
        os.kill(pid, signal.SIGTERM)
        
        # Wait for process to terminate
        for _ in range(50):  # Wait up to 5 seconds
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break
        else:
            # Force kill if still running
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except (ValueError, ProcessLookupError, PermissionError):
        pass
    finally:
        pid_file.unlink(missing_ok=True)


def _hide_dock_icon():
    """Hide the Dock icon for this process using PyObjC."""
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except ImportError:
        pass  # PyObjC not available, skip
    except Exception:
        pass  # Any other error, skip


def run_daemon() -> None:
    """
    Run the daemon (called by the subprocess).
    
    This is the main entry point for the background process.
    """
    import signal
    
    # Hide Dock icon BEFORE any other AppKit/GUI imports
    _hide_dock_icon()
    
    from navi.config import load_config
    from navi.hotkey import HotkeyListener
    from navi.recorder import AudioRecorder
    from navi.menubar import MenubarApp
    
    # Write PID file so is_daemon_running() works regardless of how we were launched
    pid_file = get_pid_file()
    pid_file.write_text(str(os.getpid()))

    config = load_config()

    # Clean up any stale temp audio files from a previous crashed session
    from navi.config import DEFAULT_TEMP_DIR
    for stale in DEFAULT_TEMP_DIR.glob("recording-*.wav"):
        try:
            stale.unlink()
        except OSError:
            pass

    # Set up signal handlers for graceful shutdown
    def handle_shutdown(signum, frame):
        cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    
    # Initialize components
    recorder = AudioRecorder(config)
    hotkey_listener = HotkeyListener(config, recorder)
    
    # Track components for cleanup
    components = {
        "recorder": recorder,
        "hotkey_listener": hotkey_listener,
    }
    
    def cleanup():
        """Clean up all components."""
        if recorder.is_recording:
            recorder.stop_recording()
        hotkey_listener.stop()
        get_pid_file().unlink(missing_ok=True)
    
    # Start hotkey listener in a thread
    hotkey_listener.start()
    
    # Check if menubar is enabled
    if config["feedback"]["menubar_icon"]:
        # Run menubar app (this blocks)
        app = MenubarApp(config, recorder, hotkey_listener)
        components["menubar"] = app
        app.run()
    else:
        # No menubar - just run hotkey listener
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            cleanup()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        run_daemon()
