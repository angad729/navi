# 🧚 Navi

**Think out loud. Capture as notes.**

Press a hotkey, speak your thoughts, and Navi transcribes them locally with Whisper, cleans them up with an LLM of your choice, and saves them as Markdown to your Obsidian vault.

![macOS](https://img.shields.io/badge/macOS-Apple_Silicon-000000?style=flat&logo=apple&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11--3.13-blue?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎙️ **Hotkey Triggered** | Press `⌘⇧N` to start/stop recording. No UI to navigate. |
| 🔒 **Privacy First** | Whisper runs 100% locally on your Mac. Your voice never leaves your device. |
| 🧠 **Flexible LLM** | Choose Ollama (local/free), OpenAI, Anthropic, or skip cleanup entirely. |
| 🧹 **Smart Cleanup** | Removes filler words, fixes incomplete sentences, extracts titles automatically. |
| 📝 **Obsidian Ready** | Notes saved as Markdown with YAML frontmatter, ready for your knowledge graph. |
| 🔔 **Full Feedback** | Menubar icon, sound effects, and macOS notifications. |
| 🚀 **Auto-Start** | Optionally starts on login so it's always ready. |
| 🔐 **Secure** | API keys stored in macOS Keychain, never in plain text. |

## 📋 Requirements

- **macOS** with Apple Silicon (M1/M2/M3/M4)
- **Python 3.11, 3.12, or 3.13** (⚠️ Python 3.14 not yet supported)
- **16GB+ RAM** recommended for Whisper large-v3
- **Homebrew** for installing dependencies

## 🚀 Quick Start

### 1. Install

```bash
# Clone the repo
git clone https://github.com/angad729/navi.git
cd navi

# Create virtual environment with Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate

# Install Navi
pip install -e .
```

### 2. Setup

Run the interactive setup wizard:

```bash
navi setup
```

The wizard will guide you through:
1. ✅ Installing dependencies (ffmpeg)
2. 🎤 Choosing a Whisper model for your hardware
3. 📁 Configuring your Obsidian vault path
4. ⌨️ Setting your hotkey preference
5. 🧠 Selecting your LLM provider
6. 🔔 Configuring notifications & sounds

### 3. Start

```bash
navi start
```

### 4. Capture

Press **⌘⇧N** (or your custom hotkey) to start recording. Press again to stop. Your thoughts are transcribed and saved to Obsidian! ✨

## 🧠 LLM Providers

Choose how your transcripts get cleaned up:

| Provider | Cost | Privacy | Setup |
|----------|------|---------|-------|
| **Ollama** | Free | 100% Local | `brew install ollama && ollama pull llama3.2` |
| **OpenAI** | ~$0.001/note | Cloud | API key required |
| **Anthropic** | ~$0.002/note | Cloud | API key required |
| **None** | Free | N/A | Raw transcription only |

## 🎤 Whisper Models

Choose based on your hardware:

| Model | RAM | Quality | Speed | Best For |
|-------|-----|---------|-------|----------|
| `large-v3` | 16GB+ | ⭐⭐⭐⭐⭐ | ⭐⭐ | M1 Pro/Max or better |
| `medium` | 8GB+ | ⭐⭐⭐⭐ | ⭐⭐⭐ | M1/M2/M3/M4 base |
| `small` | 4GB+ | ⭐⭐⭐ | ⭐⭐⭐⭐ | Older Macs |
| `base` | 2GB+ | ⭐⭐ | ⭐⭐⭐⭐⭐ | Speed over accuracy |

## 📖 CLI Commands

```bash
navi setup      # Interactive configuration wizard
navi start      # Start the background daemon
navi stop       # Stop the daemon
navi status     # Check if Navi is running
navi config     # Show current configuration
navi test       # Test microphone, LLM, and Whisper
navi install    # Enable auto-start on login
navi uninstall  # Disable auto-start
```

## 🧚 Menubar

When running, Navi shows an icon in your menubar:

| Icon | Status |
|------|--------|
| 🧚 | Idle — ready to capture |
| 🔴 | Recording in progress |
| ⏳ | Processing your recording |

Click the icon for quick access to recent notes, settings, and more.

## 📝 Output Format

Notes are saved as Markdown with YAML frontmatter:

```markdown
---
title: "Meeting with Design Team"
created: 2026-04-02T10:30:00
source: navi
type: note
duration: 45.2s
language: en
whisper_model: large-v3
---

# Meeting with Design Team

We discussed the new dashboard layout and agreed on...
```

## ⚙️ Configuration

Configuration is stored at `~/.config/navi/config.yaml`:

```yaml
hotkey:
  modifiers: [cmd, shift]
  key: n

whisper:
  model: large-v3
  language: en

llm:
  provider: ollama  # or: openai, anthropic, none
  ollama:
    model: llama3.2
    host: http://localhost:11434

output:
  vault_path: /path/to/your/obsidian/vault
  subfolder: Notes
  filename_template: "{title} - {timestamp}"

feedback:
  sounds: true
  notifications: true
  menubar_icon: true
```

## 🔧 Troubleshooting

### Hotkey not working

Grant Accessibility permissions:
1. **System Settings** → **Privacy & Security** → **Accessibility**
2. Add Terminal.app or the Python executable

### "Cannot access microphone"

Grant Microphone permissions:
1. **System Settings** → **Privacy & Security** → **Microphone**
2. Enable access for Terminal.app

### "ffmpeg not found"

```bash
brew install ffmpeg
```

### "Ollama not running"

```bash
ollama serve
```

### Python 3.14 errors

Navi requires Python 3.11-3.13. Create a venv with the correct version:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 🛠️ Development

```bash
# Clone and setup
git clone https://github.com/angad729/navi.git
cd navi
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/
ruff check src/
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [Whisper](https://github.com/openai/whisper) by OpenAI for the incredible transcription model
- [mlx-whisper](https://github.com/ml-explore/mlx-examples) for Apple Silicon optimization
- [Ollama](https://ollama.ai) for making local LLMs accessible
- [rumps](https://github.com/jaredks/rumps) for the menubar framework

---

<p align="center">
  <i>"Hey! Listen!"</i> — Navi 🧚
</p>
