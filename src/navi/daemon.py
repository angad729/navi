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
    
    # Open log file for stdout/stderr
    log = open(log_file, "a")
    
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
    
    config = load_config()
    
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
    
    # Initialize wake word listener if enabled
    wake_listener = None
    wake_config = config.get("wake_word", {})
    
    if wake_config.get("enabled", False):
        try:
            from navi.wakeword import WakeWordListener
            
            wake_listener = WakeWordListener(config)
            components["wake_listener"] = wake_listener
            
            # Set up wake word callback to trigger recording
            def on_wake_detected():
                """Called when wake word is detected."""
                print("[Navi] Wake word detected!")
                
                # Don't trigger if already recording
                if recorder.is_recording:
                    return
                
                # Start recording (same as hotkey press)
                recorder.start_recording()
            
            wake_listener.on_wake(on_wake_detected)
            
            # Pause wake word detection while recording
            def on_recording_start():
                if wake_listener:
                    wake_listener.pause()
            
            def on_recording_stop(audio_path):
                if wake_listener:
                    wake_listener.resume()
            
            # Register callbacks with recorder using the public API
            recorder.on_recording_start(on_recording_start)
            recorder.on_recording_stop(on_recording_stop)
            
            print("[Navi] Wake word detection enabled")
        
        except ImportError as e:
            print(f"[Navi] Wake word not available: {e}")
        except Exception as e:
            print(f"[Navi] Failed to initialize wake word: {e}")
    
    def cleanup():
        """Clean up all components."""
        if recorder.is_recording:
            recorder.stop_recording()
        hotkey_listener.stop()
        if wake_listener:
            wake_listener.stop()
    
    # Start hotkey listener in a thread
    hotkey_listener.start()
    
    # Start wake word listener if enabled
    if wake_listener:
        wake_listener.start()
    
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
