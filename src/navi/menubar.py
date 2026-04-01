"""
Menubar application for Navi.

Shows recording status in the macOS menu bar using rumps.
"""

import threading
from pathlib import Path
from typing import Any, Optional

import rumps

from navi.config import load_config, save_config
from navi.notify import FeedbackManager
from navi.output import save_note
from navi.process import process_transcript, OllamaError, process_transcript_simple
from navi.transcribe import transcribe_audio


class MenubarApp(rumps.App):
    """
    Menubar application for Navi.
    
    Shows a fairy icon that changes color based on recording state.
    Provides quick access to settings and recent notes.
    """
    
    # Icon states (using emoji for simplicity - can be replaced with actual icons)
    ICON_IDLE = "🧚"
    ICON_RECORDING = "🔴"
    ICON_PROCESSING = "⏳"
    
    def __init__(
        self,
        config: dict[str, Any],
        recorder: Any,
        hotkey_listener: Any,
    ):
        """
        Initialize the menubar app.
        
        Args:
            config: Navi configuration dictionary
            recorder: AudioRecorder instance
            hotkey_listener: HotkeyListener instance
        """
        super().__init__(
            name="Navi",
            icon=None,
            title=self.ICON_IDLE,
            quit_button=None,  # We'll add our own
        )
        
        self.config = config
        self.recorder = recorder
        self.hotkey_listener = hotkey_listener
        self.feedback = FeedbackManager(config)
        
        # Set up recording callbacks
        self.recorder.on_recording_start(self._on_recording_start)
        self.recorder.on_recording_stop(self._on_recording_stop)
        self.recorder.on_error(self._on_error)
        
        # Build menu
        self._build_menu()
    
    def _build_menu(self) -> None:
        """Build the dropdown menu."""
        # Status item (non-clickable)
        self.status_item = rumps.MenuItem(
            title="Ready",
            callback=None,
        )
        
        # Hotkey info
        hotkey_str = self.hotkey_listener.hotkey_string
        self.hotkey_item = rumps.MenuItem(
            title=f"Hotkey: {hotkey_str}",
            callback=None,
        )
        
        # Recent notes submenu
        self.recent_menu = rumps.MenuItem(title="Recent Notes")
        self._update_recent_notes()
        
        # Settings
        self.settings_item = rumps.MenuItem(
            title="Open Settings...",
            callback=self._open_settings,
        )
        
        # Open vault
        self.vault_item = rumps.MenuItem(
            title="Open Vault",
            callback=self._open_vault,
        )
        
        # Quit
        self.quit_item = rumps.MenuItem(
            title="Quit Navi",
            callback=self._quit,
        )
        
        # Build menu
        self.menu = [
            self.status_item,
            self.hotkey_item,
            None,  # Separator
            self.recent_menu,
            self.vault_item,
            None,  # Separator
            self.settings_item,
            None,  # Separator
            self.quit_item,
        ]
    
    def _update_recent_notes(self) -> None:
        """Update the recent notes submenu."""
        self.recent_menu.clear()
        
        try:
            from navi.output import get_recent_notes
            notes = get_recent_notes(self.config, limit=5)
            
            if not notes:
                self.recent_menu.add(rumps.MenuItem(
                    title="No notes yet",
                    callback=None,
                ))
                return
            
            for note in notes:
                item = rumps.MenuItem(
                    title=note["name"][:40],
                    callback=lambda _, p=note["path"]: self._open_note(p),
                )
                self.recent_menu.add(item)
        except Exception as e:
            self.recent_menu.add(rumps.MenuItem(
                title=f"Error: {e}",
                callback=None,
            ))
    
    def _on_recording_start(self) -> None:
        """Called when recording starts."""
        self.title = self.ICON_RECORDING
        self.status_item.title = "Recording..."
        self.feedback.recording_started()
    
    def _on_recording_stop(self, audio_path: Path) -> None:
        """
        Called when recording stops.
        
        Processes the audio in a background thread.
        """
        duration = self.recorder.recording_duration
        self.title = self.ICON_PROCESSING
        self.status_item.title = "Processing..."
        self.feedback.recording_stopped(duration)
        
        # Process in background thread
        thread = threading.Thread(
            target=self._process_audio,
            args=(audio_path, duration),
            daemon=True,
        )
        thread.start()
    
    def _process_audio(self, audio_path: Path, duration: float) -> None:
        """
        Process recorded audio (runs in background thread).
        
        Args:
            audio_path: Path to audio file
            duration: Recording duration in seconds
        """
        try:
            # Step 1: Transcribe with Whisper
            self._update_status("Transcribing...")
            
            whisper_model = self.config["whisper"]["model"]
            language = self.config["whisper"].get("language", "en")
            
            result = transcribe_audio(
                audio_path,
                model_name=whisper_model,
                language=language,
            )
            
            transcript = result["text"]
            
            if not transcript.strip():
                self.feedback.error("No speech detected")
                self._reset_status()
                return
            
            # Step 2: Process with Ollama
            self._update_status("Cleaning up...")
            
            try:
                processed = process_transcript(transcript, self.config)
            except OllamaError as e:
                # Fall back to simple processing
                print(f"Ollama error: {e}, using simple processing")
                processed = process_transcript_simple(transcript)
            
            # Step 3: Save to vault
            self._update_status("Saving...")
            
            metadata = {
                "duration": duration,
                "language": result.get("language", language),
                "model": whisper_model,
            }
            
            filepath = save_note(
                title=processed["title"],
                content=processed["content"],
                config=self.config,
                metadata=metadata,
            )
            
            # Success!
            self.feedback.note_saved(filepath, processed["title"])
            self._update_recent_notes()
            self._reset_status()
            
        except Exception as e:
            print(f"Processing error: {e}")
            self.feedback.error(str(e))
            self._reset_status()
        finally:
            # Clean up temp audio file
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass
    
    def _on_error(self, error: Exception) -> None:
        """Called when a recording error occurs."""
        self.feedback.error(str(error))
        self._reset_status()
    
    def _update_status(self, status: str) -> None:
        """Update the status display (thread-safe)."""
        rumps.Timer(0, lambda _: setattr(self.status_item, "title", status)).start()
    
    def _reset_status(self) -> None:
        """Reset to idle state (thread-safe)."""
        def reset(_):
            self.title = self.ICON_IDLE
            self.status_item.title = "Ready"
        rumps.Timer(0, reset).start()
    
    def _open_note(self, filepath: Path) -> None:
        """Open a note in the default editor."""
        import subprocess
        subprocess.run(["open", str(filepath)])
    
    def _open_vault(self, _) -> None:
        """Open the Obsidian vault folder."""
        import subprocess
        vault_path = self.config["output"]["vault_path"]
        subprocess.run(["open", vault_path])
    
    def _open_settings(self, _) -> None:
        """Open the config file in default editor."""
        import subprocess
        from navi.config import DEFAULT_CONFIG_FILE
        subprocess.run(["open", str(DEFAULT_CONFIG_FILE)])
    
    def _quit(self, _) -> None:
        """Quit the application."""
        # Stop recording if in progress
        if self.recorder.is_recording:
            self.recorder.stop_recording()
        
        # Stop hotkey listener
        self.hotkey_listener.stop()
        
        # Quit the app
        rumps.quit_application()
