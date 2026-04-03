"""
Audio recording for Navi.

Handles microphone capture and saving audio to temporary files.
"""

import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

from navi.config import get_temp_audio_path


class AudioRecorder:
    """
    Records audio from the microphone.
    
    Uses sounddevice for cross-platform audio capture with low latency.
    """
    
    # Audio settings
    SAMPLE_RATE = 16000  # Whisper expects 16kHz
    CHANNELS = 1  # Mono
    DTYPE = 'float32'  # Use string instead of numpy dtype for compatibility
    BLOCKSIZE = 1024
    
    def __init__(self, config: dict[str, Any]):
        """
        Initialize the audio recorder.
        
        Args:
            config: Navi configuration dictionary
        """
        self.config = config
        self._is_recording = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._audio_data: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._recording_thread: Optional[threading.Thread] = None
        self._start_time: Optional[datetime] = None
        self._last_duration: float = 0.0  # Store duration when recording stops

        # Silence detection config
        recording_config = config.get("recording", {})
        self._silence_detection = recording_config.get("silence_detection", True)
        self._silence_threshold = recording_config.get("silence_threshold", 0.02)
        self._silence_duration = recording_config.get("silence_duration", 3.0)
        self._min_duration = recording_config.get("min_duration", 2.0)

        # Callbacks
        self._on_recording_start: list[Callable] = []
        self._on_recording_stop: list[Callable[[Path], None]] = []
        self._on_error: list[Callable[[Exception], None]] = []
    
    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._is_recording
    
    @property
    def recording_duration(self) -> float:
        """Get current or last recording duration in seconds."""
        if self._is_recording and self._start_time:
            return (datetime.now() - self._start_time).total_seconds()
        return self._last_duration
    
    def on_recording_start(self, callback: Callable) -> None:
        """Register callback for when recording starts."""
        self._on_recording_start.append(callback)
    
    def on_recording_stop(self, callback: Callable[[Path], None]) -> None:
        """Register callback for when recording stops. Receives audio file path."""
        self._on_recording_stop.append(callback)
    
    def on_error(self, callback: Callable[[Exception], None]) -> None:
        """Register callback for errors."""
        self._on_error.append(callback)
    
    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback for audio stream."""
        if status:
            print(f"Audio status: {status}")
        
        # Copy data to queue for processing
        self._audio_queue.put(indata.copy())
    
    def _process_audio_thread(self) -> None:
        """Thread to process audio from queue."""
        # Silence detection state
        silence_frames = 0
        # How many audio blocks of silence = silence_duration seconds
        frames_per_second = self.SAMPLE_RATE / self.BLOCKSIZE
        silence_frames_needed = int(self._silence_duration * frames_per_second)

        while self._is_recording:
            try:
                data = self._audio_queue.get(timeout=0.1)
                self._audio_data.append(data)

                if self._silence_detection:
                    # Only start checking after min_duration has elapsed
                    elapsed = (datetime.now() - self._start_time).total_seconds()
                    if elapsed >= self._min_duration:
                        rms = float(np.sqrt(np.mean(data ** 2)))
                        if rms < self._silence_threshold:
                            silence_frames += 1
                        else:
                            silence_frames = 0

                        if silence_frames >= silence_frames_needed:
                            # Auto-stop in a separate thread to avoid deadlock
                            threading.Thread(
                                target=self.stop_recording, daemon=True
                            ).start()
                            break

            except queue.Empty:
                continue
    
    def start_recording(self) -> None:
        """Start recording audio from microphone."""
        if self._is_recording:
            return
        
        try:
            # Clear previous data
            self._audio_data = []
            self._last_duration = 0.0
            while not self._audio_queue.empty():
                self._audio_queue.get_nowait()
            
            # Start stream
            self._stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=self.BLOCKSIZE,
                callback=self._audio_callback,
            )
            
            self._is_recording = True
            self._start_time = datetime.now()
            
            # Start processing thread
            self._recording_thread = threading.Thread(
                target=self._process_audio_thread,
                daemon=True,
            )
            self._recording_thread.start()
            
            # Start stream
            self._stream.start()
            
            # Notify callbacks
            for callback in self._on_recording_start:
                try:
                    callback()
                except Exception as e:
                    print(f"Callback error: {e}")
        
        except Exception as e:
            self._is_recording = False
            for callback in self._on_error:
                callback(e)
            raise
    
    def stop_recording(self) -> Optional[Path]:
        """
        Stop recording and save audio to file.
        
        Returns:
            Path to saved audio file, or None if no audio was recorded
        """
        if not self._is_recording:
            return None
        
        # Capture duration before stopping
        if self._start_time:
            self._last_duration = (datetime.now() - self._start_time).total_seconds()
        
        try:
            # Stop stream
            self._is_recording = False
            
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            
            # Wait for processing thread
            if self._recording_thread:
                self._recording_thread.join(timeout=1.0)
                self._recording_thread = None
            
            # Process any remaining audio in queue
            while not self._audio_queue.empty():
                try:
                    data = self._audio_queue.get_nowait()
                    self._audio_data.append(data)
                except queue.Empty:
                    break
            
            # Check if we have any audio
            if not self._audio_data:
                return None
            
            # Concatenate audio data
            audio = np.concatenate(self._audio_data, axis=0)
            
            # Skip if too short (less than 0.5 seconds)
            if len(audio) < self.SAMPLE_RATE * 0.5:
                return None
            
            # Save to file
            audio_path = get_temp_audio_path()
            sf.write(audio_path, audio, self.SAMPLE_RATE)
            
            # Notify callbacks
            for callback in self._on_recording_stop:
                try:
                    callback(audio_path)
                except Exception as e:
                    print(f"Callback error: {e}")
            
            return audio_path
        
        except Exception as e:
            for callback in self._on_error:
                callback(e)
            raise
        finally:
            self._start_time = None
    
    def get_input_devices(self) -> list[dict]:
        """Get available input devices."""
        devices = sd.query_devices()
        input_devices = []
        
        for i, device in enumerate(devices):
            if device["max_input_channels"] > 0:
                input_devices.append({
                    "index": i,
                    "name": device["name"],
                    "channels": device["max_input_channels"],
                    "default": i == sd.default.device[0],
                })
        
        return input_devices
