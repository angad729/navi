"""
Notification and feedback for Navi.

Handles macOS notifications and sound effects.
"""

import subprocess
from pathlib import Path
from typing import Any


def play_sound(sound_name: str) -> None:
    """
    Play a system sound.
    
    Args:
        sound_name: Name of sound to play:
            - "start": Recording started
            - "stop": Recording stopped
            - "success": Note saved successfully
            - "error": An error occurred
    """
    # Map sound names to system sounds
    sound_map = {
        "start": "/System/Library/Sounds/Blow.aiff",
        "stop": "/System/Library/Sounds/Bottle.aiff",
        "success": "/System/Library/Sounds/Glass.aiff",
        "error": "/System/Library/Sounds/Basso.aiff",
    }
    
    sound_path = sound_map.get(sound_name)
    
    if sound_path and Path(sound_path).exists():
        try:
            subprocess.run(
                ["afplay", sound_path],
                capture_output=True,
                timeout=2,
            )
        except Exception:
            pass  # Silently fail if sound can't play


def send_notification(
    title: str,
    message: str,
    subtitle: str | None = None,
    sound: bool = False,
) -> None:
    """
    Send a macOS notification.
    
    Args:
        title: Notification title
        message: Notification body text
        subtitle: Optional subtitle
        sound: Whether to play default notification sound
    """
    # Build AppleScript
    script_parts = [
        f'display notification "{_escape_applescript(message)}"',
        f'with title "{_escape_applescript(title)}"',
    ]
    
    if subtitle:
        script_parts.append(f'subtitle "{_escape_applescript(subtitle)}"')
    
    if sound:
        script_parts.append('sound name "default"')
    
    script = " ".join(script_parts)
    
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass  # Silently fail if notification can't be sent


def _escape_applescript(text: str) -> str:
    """Escape text for use in AppleScript strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


class FeedbackManager:
    """
    Manages all user feedback (sounds, notifications, etc.).
    
    Respects user preferences from config.
    """
    
    def __init__(self, config: dict[str, Any]):
        """
        Initialize feedback manager.
        
        Args:
            config: Navi configuration dictionary
        """
        self.config = config
        feedback_config = config.get("feedback", {})
        self.sounds_enabled = feedback_config.get("sounds", True)
        self.notifications_enabled = feedback_config.get("notifications", True)
    
    def recording_started(self) -> None:
        """Notify that recording has started."""
        if self.sounds_enabled:
            play_sound("start")
        
        if self.notifications_enabled:
            send_notification(
                title="🧚 Navi",
                message="Recording started...",
                subtitle="Press hotkey again to stop",
            )
    
    def recording_stopped(self, duration: float) -> None:
        """
        Notify that recording has stopped.
        
        Args:
            duration: Recording duration in seconds
        """
        if self.sounds_enabled:
            play_sound("stop")
        
        if self.notifications_enabled:
            duration_str = f"{int(duration)}s" if duration < 60 else f"{int(duration // 60)}m {int(duration % 60)}s"
            send_notification(
                title="🧚 Navi",
                message="Transcribing...",
                subtitle=f"Processing {duration_str} of audio",
            )
    
    def note_saved(self, filepath: Path, title: str) -> None:
        """
        Notify that note has been saved.
        
        Args:
            filepath: Path to saved note
            title: Note title
        """
        if self.sounds_enabled:
            play_sound("success")
        
        if self.notifications_enabled:
            send_notification(
                title="🧚 Navi",
                message=f"Saved: {title}",
                subtitle=str(filepath.parent.name),
            )
    
    def error(self, message: str) -> None:
        """
        Notify of an error.
        
        Args:
            message: Error message
        """
        if self.sounds_enabled:
            play_sound("error")
        
        if self.notifications_enabled:
            send_notification(
                title="🧚 Navi - Error",
                message=message,
            )
    
    def transcribing(self) -> None:
        """Notify that transcription is in progress."""
        # No sound for this, just notification
        if self.notifications_enabled:
            send_notification(
                title="🧚 Navi",
                message="Transcribing...",
            )
    
    def processing(self) -> None:
        """Notify that LLM processing is in progress."""
        # No sound for this, just notification
        if self.notifications_enabled:
            send_notification(
                title="🧚 Navi",
                message="Cleaning up transcript...",
            )
