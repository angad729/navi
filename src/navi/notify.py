"""
Notification and feedback for Navi.

Handles macOS notifications and sound effects.
"""

import random
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


# Rotating recording-start subtitles — varied so repeated use stays fresh
_START_SUBTITLES = [
    "Press the hotkey again to stop",
    "Speak freely — I'm listening",
    "Taking notes so you don't have to",
    "Go ahead, I've got it",
    "All yours",
]

# Error messages mapped from technical strings to human copy
_ERROR_HINTS = {
    "No speech detected": "Nothing came through — was your mic muted?",
    "Ollama": "Ollama isn't responding. Is it running? Try: ollama serve",
    "timed out": "That took too long. Ollama might be overloaded — try again.",
    "Cannot connect": "Can't reach the LLM. Check that Ollama is running.",
    "API key": "API key missing or invalid. Run 'navi setup' to reconfigure.",
}


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
                title="🧚 Navi is listening",
                message=random.choice(_START_SUBTITLES),
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
            duration_str = (
                f"{int(duration)}s" if duration < 60
                else f"{int(duration // 60)}m {int(duration % 60)}s"
            )
            if duration < 15:
                flavour = "Quick thought incoming"
            elif duration > 180:
                flavour = "That was a lot — working through it"
            else:
                flavour = "On it"

            send_notification(
                title="🧚 Transcribing...",
                message=f"{flavour} · {duration_str} of audio",
            )
    
    def note_saved(self, filepath: Path, title: str, word_count: int = 0) -> None:
        """
        Notify that note has been saved.

        Args:
            filepath: Path to saved note
            title: Note title
            word_count: Approximate word count of the transcript
        """
        if self.sounds_enabled:
            play_sound("success")

        if self.notifications_enabled:
            count_str = f" · {word_count} words" if word_count > 0 else ""
            send_notification(
                title=f"✨ {title}",
                message=f"Saved to {filepath.parent.name}{count_str}",
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
            # Map technical errors to friendlier copy where possible
            friendly = next(
                (hint for key, hint in _ERROR_HINTS.items() if key in message),
                message,
            )
            send_notification(
                title="🧚 Something went wrong",
                message=friendly,
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
