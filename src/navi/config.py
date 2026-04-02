"""
Configuration management for Navi.

Handles loading, saving, and validating user configuration.
Config is stored at ~/.config/navi/config.yaml
"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "navi"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
DEFAULT_LOG_DIR = DEFAULT_CONFIG_DIR / "logs"
DEFAULT_TEMP_DIR = DEFAULT_CONFIG_DIR / "temp"

# Whisper model recommendations based on hardware
WHISPER_MODELS = {
    "large-v3": {
        "name": "large-v3",
        "description": "Highest accuracy, requires M1 Pro/Max or better, 16GB+ RAM",
        "min_ram_gb": 16,
        "recommended_for": "M1 Pro/Max, M2 Pro/Max, M3 Pro/Max, M4 Pro/Max",
    },
    "medium": {
        "name": "medium",
        "description": "Good balance of speed and accuracy, 8GB+ RAM",
        "min_ram_gb": 8,
        "recommended_for": "M1/M2/M3/M4 base models",
    },
    "small": {
        "name": "small",
        "description": "Faster, lower accuracy, works on most Macs",
        "min_ram_gb": 4,
        "recommended_for": "Older Macs or low RAM systems",
    },
    "base": {
        "name": "base",
        "description": "Fastest, lowest accuracy",
        "min_ram_gb": 2,
        "recommended_for": "When speed matters more than accuracy",
    },
}

# LLM provider options
LLM_PROVIDERS = {
    "ollama": {
        "name": "Ollama",
        "description": "Local, free, private - runs entirely on your Mac",
        "requires_api_key": False,
        "cost": "Free",
    },
    "openai": {
        "name": "OpenAI",
        "description": "Cloud-based, uses GPT-4o-mini",
        "requires_api_key": True,
        "cost": "~$0.001/note",
        "default_model": "gpt-4o-mini",
    },
    "anthropic": {
        "name": "Anthropic",
        "description": "Cloud-based, uses Claude",
        "requires_api_key": True,
        "cost": "~$0.002/note",
        "default_model": "claude-3-haiku-20240307",
    },
    "none": {
        "name": "None",
        "description": "Skip cleanup - save raw transcription only",
        "requires_api_key": False,
        "cost": "Free",
    },
}

CLEANUP_PROMPT = """You are a smart note-taking assistant. Process this voice transcription and output a well-structured note.

Your tasks:
1. Extract a concise title (max 6 words)
2. Extract entities: people names, project names, companies, topics, concepts
3. Generate relevant tags for categorization
4. Create a structured Summary with bullet points including:
   - Key decisions
   - Action items (with owners if mentioned)
   - Blockers or concerns
   - Important facts or dates
5. Create a cleaned Transcript that:
   - Removes filler words (um, uh, like, you know)
   - Fixes false starts and incomplete sentences
   - Preserves the conversational tone
   - Keeps ALL important context and sentences

Respond in this EXACT JSON format:
{
  "title": "Meeting About Q3 Launch",
  "tags": ["product", "Q3", "planning"],
  "entities": [
    {"name": "John Smith", "type": "person"},
    {"name": "Project Atlas", "type": "project"},
    {"name": "Acme Corp", "type": "company"}
  ],
  "summary": "- Key decision: Launch date set for June 15\\n- Action: John to finalize pricing by Monday\\n- Action: Review competitor analysis by Friday\\n- Blocker: Waiting on legal sign-off",
  "transcript": "We talked about the Q3 launch timeline. John thinks June 15 is doable if we lock down pricing this week. I mentioned we still need to look at what competitors are doing before we commit to the final feature set."
}

IMPORTANT:
- Only include entities you are HIGHLY confident about
- Tags should be lowercase, single words or hyphenated
- Summary should be bullet points starting with "- "
- Transcript should preserve ALL key information from the original
- Use \\n for newlines in the JSON strings"""

DEFAULT_CONFIG = {
    "version": 2,
    "hotkey": {
        "modifiers": ["cmd", "shift"],
        "key": "n",
    },
    "whisper": {
        "model": "large-v3",
        "language": "en",  # None for auto-detect
    },
    "llm": {
        "provider": "ollama",  # ollama, openai, anthropic, none
        "cleanup_prompt": CLEANUP_PROMPT,
        "ollama": {
            "model": "llama3.2",
            "host": "http://localhost:11434",
        },
        "openai": {
            "model": "gpt-4o-mini",
            # API key stored in macOS Keychain
        },
        "anthropic": {
            "model": "claude-3-haiku-20240307",
            # API key stored in macOS Keychain
        },
    },
    "output": {
        "destination": "obsidian",
        "vault_path": "",  # Set during setup
        "subfolder": "",  # Optional subfolder within vault
        "filename_template": "{title} - {timestamp}",
        "timestamp_format": "%Y-%m-%d-%H%M%S",
    },
    "feedback": {
        "sounds": True,
        "notifications": True,
        "menubar_icon": True,
    },
    "daemon": {
        "auto_start": False,
    },
}


class ConfigError(Exception):
    """Raised when there's a configuration error."""

    pass


def ensure_config_dirs() -> None:
    """Create config directories if they don't exist."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_TEMP_DIR.mkdir(parents=True, exist_ok=True)


def load_config(config_path: Optional[Path] = None) -> dict[str, Any]:
    """
    Load configuration from file.
    
    Args:
        config_path: Optional path to config file. Defaults to ~/.config/navi/config.yaml
        
    Returns:
        Configuration dictionary
        
    Raises:
        ConfigError: If config file is invalid
    """
    path = config_path or DEFAULT_CONFIG_FILE
    
    if not path.exists():
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(path, "r") as f:
            user_config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid config file: {e}")
    
    # Migrate old config format if needed
    user_config = _migrate_config(user_config)
    
    # Merge with defaults (user config takes precedence)
    config = _deep_merge(DEFAULT_CONFIG.copy(), user_config)
    return config


def _migrate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Migrate old config format to new format."""
    version = config.get("version", 1)
    
    # Migrate from v1 (ollama at top level) to v2 (llm.provider structure)
    if version < 2 and "ollama" in config:
        old_ollama = config.pop("ollama", {})
        config["llm"] = {
            "provider": "ollama",
            "ollama": old_ollama,
            "cleanup_prompt": old_ollama.get("cleanup_prompt", CLEANUP_PROMPT),
        }
        config["version"] = 2
    
    return config


def save_config(config: dict[str, Any], config_path: Optional[Path] = None) -> None:
    """
    Save configuration to file.
    
    Args:
        config: Configuration dictionary to save
        config_path: Optional path to config file. Defaults to ~/.config/navi/config.yaml
    """
    ensure_config_dirs()
    path = config_path or DEFAULT_CONFIG_FILE
    
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def validate_config(config: dict[str, Any]) -> list[str]:
    """
    Validate configuration and return list of errors.
    
    Args:
        config: Configuration dictionary to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Check vault path
    vault_path = config.get("output", {}).get("vault_path", "")
    if not vault_path:
        errors.append("Obsidian vault path is not set. Run 'navi setup' to configure.")
    elif not Path(vault_path).exists():
        errors.append(f"Obsidian vault path does not exist: {vault_path}")
    
    # Check Whisper model
    whisper_model = config.get("whisper", {}).get("model", "")
    if whisper_model not in WHISPER_MODELS:
        errors.append(f"Invalid Whisper model: {whisper_model}. Valid options: {list(WHISPER_MODELS.keys())}")
    
    # Check hotkey
    hotkey = config.get("hotkey", {})
    if not hotkey.get("key"):
        errors.append("Hotkey key is not set")
    
    # Check LLM provider
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "")
    if provider and provider not in LLM_PROVIDERS:
        errors.append(f"Invalid LLM provider: {provider}. Valid options: {list(LLM_PROVIDERS.keys())}")
    
    return errors


def get_config_value(config: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    Get a nested config value using dot notation.
    
    Args:
        config: Configuration dictionary
        key_path: Dot-separated path to value (e.g., "whisper.model")
        default: Default value if not found
        
    Returns:
        Config value or default
    """
    keys = key_path.split(".")
    value = config
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


def set_config_value(config: dict[str, Any], key_path: str, value: Any) -> dict[str, Any]:
    """
    Set a nested config value using dot notation.
    
    Args:
        config: Configuration dictionary
        key_path: Dot-separated path to value (e.g., "whisper.model")
        value: Value to set
        
    Returns:
        Updated config dictionary
    """
    keys = key_path.split(".")
    current = config
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value
    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries.
    
    Args:
        base: Base dictionary
        override: Dictionary with override values
        
    Returns:
        Merged dictionary
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def config_exists() -> bool:
    """Check if config file exists."""
    return DEFAULT_CONFIG_FILE.exists()


def get_temp_audio_path() -> Path:
    """Get path for temporary audio file."""
    ensure_config_dirs()
    return DEFAULT_TEMP_DIR / "recording.wav"
