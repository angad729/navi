"""
Global hotkey listener for Navi.

Uses pynput to capture global keyboard shortcuts.
"""

import threading
from typing import Any, Callable, Optional, Set

from pynput import keyboard
from pynput.keyboard import Key, KeyCode


# Map config modifier names to pynput keys
MODIFIER_MAP = {
    "cmd": Key.cmd,
    "command": Key.cmd,
    "shift": Key.shift,
    "ctrl": Key.ctrl,
    "control": Key.ctrl,
    "alt": Key.alt,
    "option": Key.alt,
}


class HotkeyListener:
    """
    Listens for global hotkey combinations.
    
    When the configured hotkey is pressed, toggles recording on/off.
    """
    
    def __init__(self, config: dict[str, Any], recorder: Any):
        """
        Initialize the hotkey listener.
        
        Args:
            config: Navi configuration dictionary
            recorder: AudioRecorder instance to control
        """
        self.config = config
        self.recorder = recorder
        self.listener: Optional[keyboard.Listener] = None
        self._running = False
        
        # Parse hotkey from config
        self._parse_hotkey()
        
        # Track currently pressed modifiers
        self._pressed_modifiers: Set[Key] = set()
    
    def _parse_hotkey(self) -> None:
        """Parse hotkey configuration into pynput keys."""
        hotkey_config = self.config["hotkey"]
        
        # Get modifiers
        self.required_modifiers: Set[Key] = set()
        for mod in hotkey_config["modifiers"]:
            mod_lower = mod.lower()
            if mod_lower in MODIFIER_MAP:
                self.required_modifiers.add(MODIFIER_MAP[mod_lower])
        
        # Get key
        key_str = hotkey_config["key"].lower()
        if len(key_str) == 1:
            self.trigger_key = KeyCode.from_char(key_str)
        else:
            # Handle special keys if needed
            self.trigger_key = getattr(Key, key_str, KeyCode.from_char(key_str[0]))
    
    def _on_press(self, key: Key | KeyCode) -> None:
        """Handle key press events."""
        # Track modifiers
        if isinstance(key, Key) and key in MODIFIER_MAP.values():
            self._pressed_modifiers.add(key)
            return
        
        # Check if this is our trigger key with correct modifiers
        if self._is_hotkey_pressed(key):
            self._toggle_recording()
    
    def _on_release(self, key: Key | KeyCode) -> None:
        """Handle key release events."""
        # Remove released modifiers
        if isinstance(key, Key) and key in self._pressed_modifiers:
            self._pressed_modifiers.discard(key)
    
    def _is_hotkey_pressed(self, key: Key | KeyCode) -> bool:
        """Check if the current key press matches our hotkey."""
        # Check if all required modifiers are pressed
        if not self.required_modifiers.issubset(self._pressed_modifiers):
            return False
        
        # Check if the trigger key matches
        if isinstance(key, KeyCode) and isinstance(self.trigger_key, KeyCode):
            return key.char == self.trigger_key.char
        
        return key == self.trigger_key
    
    def _toggle_recording(self) -> None:
        """Toggle recording state."""
        if self.recorder.is_recording:
            self.recorder.stop_recording()
        else:
            self.recorder.start_recording()
    
    def start(self) -> None:
        """Start listening for hotkey."""
        if self._running:
            return
        
        self._running = True
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self.listener.start()
    
    def stop(self) -> None:
        """Stop listening for hotkey."""
        self._running = False
        if self.listener:
            self.listener.stop()
            self.listener = None
    
    @property
    def hotkey_string(self) -> str:
        """Get human-readable hotkey string."""
        parts = []
        for mod in self.config["hotkey"]["modifiers"]:
            if mod.lower() in ("cmd", "command"):
                parts.append("⌘")
            elif mod.lower() == "shift":
                parts.append("⇧")
            elif mod.lower() in ("ctrl", "control"):
                parts.append("⌃")
            elif mod.lower() in ("alt", "option"):
                parts.append("⌥")
        
        parts.append(self.config["hotkey"]["key"].upper())
        return "".join(parts)
