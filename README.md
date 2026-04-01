# 🧚 Navi

**Voice notes that just work.**

Press a hotkey, speak your thoughts, and Navi transcribes them locally with Whisper, cleans them up with a local LLM, and saves them to your Obsidian vault. No cloud services, no subscriptions, no fuss.

![macOS](https://img.shields.io/badge/macOS-000000?style=flat&logo=apple&logoColor=white)
![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue?style=flat&logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ Features

- **🎙️ Hotkey Triggered** — Press `⌘⇧N` to start/stop recording. No UI to navigate.
- **🔒 100% Local** — Whisper transcription and Ollama cleanup run entirely on your Mac.
- **🧹 Smart Cleanup** — Removes filler words, fixes incomplete sentences, adds punctuation.
- **📝 Obsidian Integration** — Notes saved directly to your vault with YAML frontmatter.
- **🔔 Full Feedback** — Menubar icon, sound effects, and macOS notifications.
- **🚀 Auto-Start** — Optionally starts on login so it's always ready.

## 📋 Requirements

- **macOS** (Apple Silicon recommended for best performance)
- **Python 3.11+**
- **Ollama** (for transcript cleanup)
- **16GB+ RAM** recommended for Whisper Large-v3

## 🚀 Installation

### Option 1: Homebrew (Recommended)

```bash
brew tap angad729/navi
brew install navi
```

### Option 2: pipx

```bash
pipx install navi-voice
```

### Option 3: pip

```bash
pip install navi-voice
```

### Post-Install Setup

1. **Install Ollama** (if not already installed):
   ```bash
   brew install ollama
   ollama pull llama3.2
   ```

2. **Run the setup wizard**:
   ```bash
   navi setup
   ```

3. **Start Navi**:
   ```bash
   navi start
   ```

4. **Press `⌘⇧N`** to start your first recording!

## 🎯 Usage

### Basic Workflow

1. Press `⌘⇧N` — Recording starts (you'll hear a chime)
2. Speak your thoughts naturally
3. Press `⌘⇧N` again — Recording stops
4. Wait a few seconds — Navi transcribes and cleans up your note
5. Check your Obsidian vault — Your note is there with a title and clean formatting

### CLI Commands

```bash
navi setup      # First-time configuration wizard
navi start      # Start the background daemon
navi stop       # Stop the daemon
navi status     # Check if Navi is running
navi install    # Enable auto-start on login
navi uninstall  # Disable auto-start
navi config     # Show current configuration
navi test       # Test microphone and transcription
```

### Menubar

When running, Navi shows a 🧚 icon in your menubar:
- **🧚** — Idle, ready to record
- **🔴** — Currently recording
- **⏳** — Processing your recording

Click the icon for quick access to:
- Recent notes
- Open Obsidian vault
- Settings
- Quit

## ⚙️ Configuration

Configuration is stored at `~/.config/navi/config.yaml`.

### Hotkey

Change the recording hotkey:

```yaml
hotkey:
  modifiers:
    - cmd
    - shift
  key: n  # Change this to any letter/number
```

### Whisper Model

Choose based on your hardware:

| Model | RAM | Quality | Speed | Best For |
|-------|-----|---------|-------|----------|
| `large-v3` | 16GB+ | ★★★★★ | ★★☆☆☆ | M1 Pro/Max or better |
| `medium` | 8GB+ | ★★★★☆ | ★★★☆☆ | M1/M2 base models |
| `small` | 4GB+ | ★★★☆☆ | ★★★★☆ | Older Macs |
| `base` | 2GB+ | ★★☆☆☆ | ★★★★★ | Speed over accuracy |

```yaml
whisper:
  model: large-v3  # or medium, small, base
  language: en     # or null for auto-detect
```

### Output

Configure where notes are saved:

```yaml
output:
  destination: obsidian
  vault_path: /path/to/your/vault
  subfolder: Voice Notes  # Optional
  filename_template: "{title} - {timestamp}"
```

### Feedback

Toggle notifications and sounds:

```yaml
feedback:
  sounds: true
  notifications: true
  menubar_icon: true
```

## 🔧 Troubleshooting

### "Ollama is not running"

Start Ollama:
```bash
ollama serve
```

Or if using Homebrew:
```bash
brew services start ollama
```

### "Cannot access microphone"

Grant microphone permission:
1. Open **System Preferences** → **Privacy & Security** → **Microphone**
2. Enable access for your terminal app

### "Model not found"

Download the required Ollama model:
```bash
ollama pull llama3.2
```

### Hotkey not working

1. Check if Navi is running: `navi status`
2. Grant accessibility permissions:
   - **System Preferences** → **Privacy & Security** → **Accessibility**
   - Add your terminal app or Python

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

- [Whisper](https://github.com/openai/whisper) by OpenAI for the transcription model
- [mlx-whisper](https://github.com/ml-explore/mlx-examples) for Apple Silicon optimization
- [Ollama](https://ollama.ai) for local LLM inference
- [rumps](https://github.com/jaredks/rumps) for the menubar app framework

---

*"Hey! Listen!" — Navi, probably*
