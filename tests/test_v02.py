#!/usr/bin/env python3
"""
Quick test script for Navi v0.2 features.

Run from the navi directory with:
    source .venv/bin/activate
    pytest tests/test_v02.py -v
"""

import sys
from pathlib import Path

import pytest


def test_imports():
    """Test that all new modules can be imported."""
    from navi.config import DEFAULT_CONFIG, load_config
    from navi.wakeword import WakeWordListener, check_vosk_available
    from navi.ask import NoteIndex, ask_navi, AskNaviError
    from navi.cli import main, ask_command, wake_group, index_command
    from navi.daemon import run_daemon


def test_wake_word_config_schema():
    """Test wake_word config exists with required fields."""
    from navi.config import DEFAULT_CONFIG
    
    assert "wake_word" in DEFAULT_CONFIG
    wake = DEFAULT_CONFIG["wake_word"]
    
    required_keys = ["enabled", "phrases", "sensitivity", "cooldown"]
    for key in required_keys:
        assert key in wake, f"wake_word.{key} missing"


def test_ask_navi_config_schema():
    """Test ask_navi config exists with required fields."""
    from navi.config import DEFAULT_CONFIG
    
    assert "ask_navi" in DEFAULT_CONFIG
    ask = DEFAULT_CONFIG["ask_navi"]
    
    required_keys = ["embedding_provider", "ollama_model", "st_model"]
    for key in required_keys:
        assert key in ask, f"ask_navi.{key} missing"


def test_vosk_availability_check():
    """Test Vosk availability check doesn't crash."""
    from navi.wakeword import check_vosk_available
    
    available, message = check_vosk_available()
    assert isinstance(available, bool)
    assert isinstance(message, str)


def test_note_index_init():
    """Test NoteIndex initialization."""
    from navi.ask import NoteIndex
    from navi.config import DEFAULT_CONFIG
    
    config = DEFAULT_CONFIG.copy()
    config["output"]["vault_path"] = "/tmp/test_vault"
    
    index = NoteIndex(config)
    stats = index.get_stats()
    
    assert isinstance(stats, dict)


def test_cli_version():
    """Test CLI version is 0.2.0."""
    from click.testing import CliRunner
    from navi.cli import main
    
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    
    assert "0.2.0" in result.output


def test_cli_has_new_commands():
    """Test CLI help shows new commands."""
    from click.testing import CliRunner
    from navi.cli import main
    
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    
    assert "ask" in result.output
    assert "index" in result.output
    assert "wake" in result.output


def test_wake_command_group():
    """Test 'navi wake' command group works."""
    from click.testing import CliRunner
    from navi.cli import main
    
    runner = CliRunner()
    result = runner.invoke(main, ["wake", "--help"])
    
    assert result.exit_code == 0
    assert "enable" in result.output
    assert "disable" in result.output
    assert "status" in result.output
