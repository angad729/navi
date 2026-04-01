"""Tests for Navi."""

import pytest


def test_version():
    """Test version is defined."""
    from navi import __version__
    assert __version__ == "0.1.0"


def test_config_defaults():
    """Test config has required defaults."""
    from navi.config import DEFAULT_CONFIG
    
    assert "hotkey" in DEFAULT_CONFIG
    assert "whisper" in DEFAULT_CONFIG
    assert "ollama" in DEFAULT_CONFIG
    assert "output" in DEFAULT_CONFIG
    assert "feedback" in DEFAULT_CONFIG
