"""
Whisper transcription for Navi.

Uses mlx-whisper for fast, local transcription on Apple Silicon.
"""

import time
from pathlib import Path
from typing import Any, Optional

# mlx-whisper import is done lazily to avoid slow startup
_model_cache: dict[str, Any] = {}


def load_whisper_model(model_name: str = "large-v3") -> Any:
    """
    Load a Whisper model.
    
    Models are cached to avoid reloading.
    
    Args:
        model_name: Name of the model to load (large-v3, medium, small, base)
        
    Returns:
        Loaded model object
    """
    if model_name in _model_cache:
        return _model_cache[model_name]
    
    try:
        import mlx_whisper
        
        # mlx-whisper uses huggingface model names
        model_map = {
            "large-v3": "mlx-community/whisper-large-v3-mlx",
            "large": "mlx-community/whisper-large-v3-mlx",
            "medium": "mlx-community/whisper-medium-mlx",
            "small": "mlx-community/whisper-small-mlx",
            "base": "mlx-community/whisper-base-mlx",
        }
        
        hf_model = model_map.get(model_name, model_map["large-v3"])
        
        # The model will be downloaded on first use
        _model_cache[model_name] = hf_model
        return hf_model
        
    except ImportError:
        raise ImportError(
            "mlx-whisper is not installed. Install with: pip install mlx-whisper"
        )


def transcribe_audio(
    audio_path: Path,
    model_name: str = "large-v3",
    language: Optional[str] = "en",
) -> dict[str, Any]:
    """
    Transcribe audio file using Whisper.
    
    Args:
        audio_path: Path to audio file (WAV format, 16kHz)
        model_name: Whisper model to use
        language: Language code (e.g., "en") or None for auto-detect
        
    Returns:
        Dictionary with transcription results:
        - text: Full transcription text
        - segments: List of segments with timestamps
        - language: Detected language
        - duration: Audio duration in seconds
    """
    import mlx_whisper
    
    model = load_whisper_model(model_name)
    
    start_time = time.time()
    
    # Transcribe
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=model,
        language=language,
        word_timestamps=True,
    )
    
    elapsed = time.time() - start_time
    
    return {
        "text": result.get("text", "").strip(),
        "segments": result.get("segments", []),
        "language": result.get("language", language),
        "duration": elapsed,
    }


def format_transcript_with_timestamps(result: dict[str, Any]) -> str:
    """
    Format transcription with timestamps.
    
    Args:
        result: Transcription result from transcribe_audio
        
    Returns:
        Formatted transcript with timestamps
    """
    lines = []
    
    for segment in result.get("segments", []):
        start = segment.get("start", 0)
        end = segment.get("end", 0)
        text = segment.get("text", "").strip()
        
        # Format timestamp as MM:SS
        start_str = f"{int(start // 60):02d}:{int(start % 60):02d}"
        end_str = f"{int(end // 60):02d}:{int(end % 60):02d}"
        
        lines.append(f"[{start_str} - {end_str}] {text}")
    
    return "\n".join(lines)
