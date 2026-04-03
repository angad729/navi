"""
Navi - Voice notes that just work.

A hotkey-triggered voice capture tool with local Whisper transcription
and LLM-powered cleanup, saving directly to your Obsidian vault.
"""

import sys

__version__ = "0.2.0"
__author__ = "angad729"

# Check Python version at import time
_py_version = sys.version_info
if _py_version < (3, 11):
    raise RuntimeError(
        f"Navi requires Python 3.11 or later, but you're using Python {_py_version.major}.{_py_version.minor}.\n"
        f"Please create a virtual environment with Python 3.12:\n"
        f"  python3.12 -m venv .venv && source .venv/bin/activate"
    )
