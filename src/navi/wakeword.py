"""
Wake word detection for Navi.

Listens for "Listen Navi" (or configurable phrase) to trigger recording.
Uses Vosk for offline, local, free speech recognition.

The wake word listener runs alongside the hotkey listener, providing
two ways to start recording:
1. Hotkey (⌘⇧N) - instant, always works
2. Wake word ("Listen Navi") - hands-free, natural

Architecture:
- Continuous low-power audio monitoring via sounddevice
- Vosk processes small chunks looking for wake phrase
- On detection: triggers the same recording flow as hotkey
- Configurable sensitivity and wake phrases
"""

import json
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import sounddevice as sd

# Vosk is imported lazily to allow graceful degradation
_vosk = None
_vosk_model = None


class WakeWordError(Exception):
    """Raised when wake word detection fails."""
    pass


def _ensure_vosk():
    """Lazy import and model loading for Vosk."""
    global _vosk, _vosk_model
    
    if _vosk is None:
        try:
            import vosk
            _vosk = vosk
            # Suppress Vosk's verbose logging
            vosk.SetLogLevel(-1)
        except ImportError:
            raise WakeWordError(
                "Vosk is not installed. Install with: pip install vosk"
            )
    
    if _vosk_model is None:
        model_path = _get_model_path()
        if not model_path.exists():
            raise WakeWordError(
                f"Vosk model not found at {model_path}. "
                "Download a model from https://alphacephei.com/vosk/models"
            )
        _vosk_model = _vosk.Model(str(model_path))
    
    return _vosk, _vosk_model


def _get_model_path() -> Path:
    """Get the path to the Vosk model."""
    # Check config dir first
    config_model = Path.home() / ".config" / "navi" / "vosk-model"
    if config_model.exists():
        return config_model
    
    # Check common locations
    common_paths = [
        Path.home() / ".vosk" / "vosk-model-small-en-us-0.15",
        Path.home() / ".vosk" / "vosk-model-en-us-0.22",
        Path("/usr/local/share/vosk/model"),
    ]
    
    for path in common_paths:
        if path.exists():
            return path
    
    # Default location (will fail if not present)
    return config_model


def download_vosk_model(model_name: str = "vosk-model-small-en-us-0.15") -> Path:
    """
    Download a Vosk model if not present.
    
    Args:
        model_name: Name of the model to download
        
    Returns:
        Path to the downloaded model
    """
    import urllib.request
    import zipfile
    import tempfile
    
    model_dir = Path.home() / ".config" / "navi"
    model_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = model_dir / "vosk-model"
    
    if model_path.exists():
        return model_path
    
    url = f"https://alphacephei.com/vosk/models/{model_name}.zip"
    
    print(f"Downloading Vosk model from {url}...")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = Path(tmp_dir) / "model.zip"
        urllib.request.urlretrieve(url, zip_path)
        
        print("Extracting model...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(tmp_dir)
        
        # Find the extracted model directory
        extracted = list(Path(tmp_dir).glob("vosk-model-*"))
        if extracted:
            import shutil
            shutil.move(str(extracted[0]), str(model_path))
    
    print(f"Model installed to {model_path}")
    return model_path


class WakeWordListener:
    """
    Listens for wake word to trigger recording.
    
    Uses Vosk for continuous speech recognition, looking for
    the configured wake phrase (default: "listen navi").
    
    The listener runs in a background thread and calls the
    provided callback when the wake word is detected.
    """
    
    # Default wake phrases (any of these will trigger)
    DEFAULT_PHRASES = [
        "listen navi",
        "hey navi", 
        "okay navi",
        "navi",
    ]
    
    # Audio settings for wake word detection
    SAMPLE_RATE = 16000  # Vosk expects 16kHz
    CHANNELS = 1
    BLOCKSIZE = 8000  # 0.5 seconds of audio per block
    
    def __init__(
        self,
        config: dict[str, Any],
        on_wake: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize the wake word listener.
        
        Args:
            config: Navi configuration dictionary
            on_wake: Callback function when wake word is detected
        """
        self.config = config
        self._on_wake = on_wake
        
        # Get wake word settings from config
        wake_config = config.get("wake_word", {})
        self.enabled = wake_config.get("enabled", False)
        self.phrases = wake_config.get("phrases", self.DEFAULT_PHRASES)
        self.sensitivity = wake_config.get("sensitivity", 0.5)
        self.cooldown = wake_config.get("cooldown", 2.0)  # seconds
        
        # State
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._last_detection = 0.0
        self._paused = False
    
    def start(self) -> None:
        """Start listening for wake word."""
        if not self.enabled:
            return
        
        if self._running:
            return
        
        try:
            _ensure_vosk()
        except WakeWordError as e:
            print(f"Wake word disabled: {e}")
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="WakeWordListener",
        )
        self._thread.start()
    
    def stop(self) -> None:
        """Stop listening for wake word."""
        self._running = False
        
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
    
    def pause(self) -> None:
        """Temporarily pause wake word detection (e.g., while recording)."""
        self._paused = True
    
    def resume(self) -> None:
        """Resume wake word detection."""
        self._paused = False
    
    def on_wake(self, callback: Callable[[], None]) -> None:
        """Set the callback for wake word detection."""
        self._on_wake = callback
    
    @property
    def is_listening(self) -> bool:
        """Check if currently listening for wake word."""
        return self._running and not self._paused
    
    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback for audio input stream."""
        if status:
            print(f"Wake word audio status: {status}")
        
        if not self._paused:
            # Convert to int16 for Vosk
            audio_data = (indata * 32767).astype(np.int16).tobytes()
            self._audio_queue.put(audio_data)
    
    def _listen_loop(self) -> None:
        """Main loop for wake word detection."""
        import time
        
        vosk, model = _ensure_vosk()
        recognizer = vosk.KaldiRecognizer(model, self.SAMPLE_RATE)
        recognizer.SetWords(True)
        
        # Start audio stream
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            blocksize=self.BLOCKSIZE,
            dtype=np.float32,
            callback=self._audio_callback,
        )
        self._stream.start()
        
        while self._running:
            try:
                # Get audio data with timeout
                try:
                    data = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                if self._paused:
                    continue
                
                # Process with Vosk
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").lower()
                    
                    if text and self._check_wake_phrase(text):
                        # Check cooldown
                        now = time.time()
                        if now - self._last_detection >= self.cooldown:
                            self._last_detection = now
                            self._trigger_wake()
                else:
                    # Check partial results for faster response
                    partial = json.loads(recognizer.PartialResult())
                    text = partial.get("partial", "").lower()
                    
                    if text and self._check_wake_phrase(text):
                        now = time.time()
                        if now - self._last_detection >= self.cooldown:
                            self._last_detection = now
                            # Reset recognizer to clear the partial
                            recognizer.Reset()
                            self._trigger_wake()
            
            except Exception as e:
                print(f"Wake word error: {e}")
                continue
        
        # Cleanup
        if self._stream:
            self._stream.stop()
            self._stream.close()
    
    def _check_wake_phrase(self, text: str) -> bool:
        """Check if text contains a wake phrase."""
        text = text.strip().lower()
        
        for phrase in self.phrases:
            phrase = phrase.lower()
            
            # Exact match
            if text == phrase:
                return True
            
            # Phrase at end of text (e.g., "okay listen navi")
            if text.endswith(phrase):
                return True
            
            # Phrase anywhere in text (with word boundaries)
            words = text.split()
            phrase_words = phrase.split()
            
            for i in range(len(words) - len(phrase_words) + 1):
                if words[i:i + len(phrase_words)] == phrase_words:
                    return True
        
        return False
    
    def _trigger_wake(self) -> None:
        """Trigger the wake callback."""
        if self._on_wake:
            # Run callback in separate thread to not block audio processing
            threading.Thread(
                target=self._on_wake,
                daemon=True,
            ).start()


def check_vosk_available() -> tuple[bool, str]:
    """
    Check if Vosk is available and model is installed.
    
    Returns:
        Tuple of (available, message)
    """
    try:
        import vosk
    except ImportError:
        return False, "Vosk not installed. Run: pip install vosk"
    
    model_path = _get_model_path()
    if not model_path.exists():
        return False, (
            f"Vosk model not found. Run: navi wake setup\n"
            f"Or download manually to {model_path}"
        )
    
    return True, f"Vosk ready with model at {model_path}"
