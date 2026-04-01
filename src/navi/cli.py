"""
CLI interface for Navi.

Commands:
    navi setup      - Interactive first-time configuration
    navi start      - Start the background daemon
    navi stop       - Stop the daemon
    navi status     - Check if daemon is running
    navi install    - Enable auto-start on login
    navi uninstall  - Disable auto-start
    navi config     - Show current configuration
    navi test       - Test microphone and transcription
"""

import subprocess
import sys
from pathlib import Path

import click

from navi.config import (
    DEFAULT_CONFIG,
    WHISPER_MODELS,
    LLM_PROVIDERS,
    config_exists,
    load_config,
    save_config,
    validate_config,
    ensure_config_dirs,
)
from navi.daemon import get_pid_file, is_daemon_running, start_daemon, stop_daemon
from navi.launchd import install_launchd, uninstall_launchd, is_launchd_installed


def _check_ffmpeg() -> bool:
    """Check if ffmpeg is installed."""
    try:
        result = subprocess.run(
            ["which", "ffmpeg"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def _install_ffmpeg() -> bool:
    """Install ffmpeg via Homebrew."""
    try:
        subprocess.run(
            ["brew", "install", "ffmpeg"],
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        return False


@click.group()
@click.version_option(version="0.1.0", prog_name="navi")
def main():
    """
    🧚 Navi - Voice notes that just work.
    
    Press ⌘⇧N to start/stop recording. Your voice is transcribed locally
    with Whisper, cleaned up with your chosen LLM, and saved to your Obsidian vault.
    
    Get started with: navi setup
    """
    pass


@main.command()
def setup():
    """Interactive first-time configuration wizard."""
    click.echo()
    click.echo(click.style("🧚 Welcome to Navi!", fg="cyan", bold=True))
    click.echo(click.style("   Let's set up your voice note capture.\n", fg="cyan"))
    
    # Step 0: Check dependencies (ffmpeg)
    click.echo(click.style("Checking dependencies...", fg="yellow", bold=True))
    
    if _check_ffmpeg():
        click.echo(click.style("✓ ffmpeg is installed", fg="green"))
    else:
        click.echo("ffmpeg is required for audio processing but is not installed.")
        if click.confirm("Would you like to install ffmpeg now?", default=True):
            click.echo("Installing ffmpeg via Homebrew...")
            if _install_ffmpeg():
                click.echo(click.style("✓ ffmpeg installed successfully", fg="green"))
            else:
                click.echo(click.style("✗ Failed to install ffmpeg", fg="red"))
                click.echo("  Please install manually: brew install ffmpeg")
                click.echo("  Then run 'navi setup' again.")
                return
        else:
            click.echo(click.style("✗ ffmpeg is required. Please install it:", fg="red"))
            click.echo("  brew install ffmpeg")
            return
    
    click.echo()
    
    config = DEFAULT_CONFIG.copy()
    
    # Step 1: Whisper model
    click.echo(click.style("Step 1: Whisper Model", fg="yellow", bold=True))
    click.echo("Choose a transcription model based on your hardware:\n")
    
    for key, model in WHISPER_MODELS.items():
        click.echo(f"  {click.style(key, fg='green', bold=True)}")
        click.echo(f"    {model['description']}")
        click.echo(f"    Best for: {model['recommended_for']}\n")
    
    model_choice = click.prompt(
        "Select model",
        type=click.Choice(list(WHISPER_MODELS.keys())),
        default="large-v3"
    )
    config["whisper"]["model"] = model_choice
    click.echo()
    
    # Step 2: Obsidian vault
    click.echo(click.style("Step 2: Obsidian Vault", fg="yellow", bold=True))
    
    # Try to find existing vaults
    common_paths = [
        Path.home() / "Documents" / "Obsidian",
        Path.home() / "Obsidian",
        Path.home() / "Documents",
    ]
    
    existing_vaults = []
    for path in common_paths:
        if path.exists():
            for item in path.iterdir():
                if item.is_dir() and (item / ".obsidian").exists():
                    existing_vaults.append(item)
    
    if existing_vaults:
        click.echo("Found existing Obsidian vaults:")
        for i, vault in enumerate(existing_vaults, 1):
            click.echo(f"  {i}. {vault}")
        click.echo(f"  {len(existing_vaults) + 1}. Enter custom path")
        
        choice = click.prompt(
            "Select vault",
            type=int,
            default=1
        )
        
        if choice <= len(existing_vaults):
            vault_path = str(existing_vaults[choice - 1])
        else:
            vault_path = click.prompt("Enter full path to your Obsidian vault")
    else:
        vault_path = click.prompt("Enter full path to your Obsidian vault")
    
    # Validate vault path
    vault_path = Path(vault_path).expanduser()
    if not vault_path.exists():
        click.echo(click.style(f"⚠️  Path does not exist: {vault_path}", fg="yellow"))
        if click.confirm("Create this directory?"):
            vault_path.mkdir(parents=True)
        else:
            click.echo("Please run setup again with a valid path.")
            return
    
    config["output"]["vault_path"] = str(vault_path)
    
    # Optional subfolder
    subfolder = click.prompt(
        "Subfolder for voice notes (leave empty for vault root)",
        default="",
        show_default=False
    )
    if subfolder:
        config["output"]["subfolder"] = subfolder
        subfolder_path = vault_path / subfolder
        if not subfolder_path.exists():
            subfolder_path.mkdir(parents=True)
            click.echo(click.style(f"✓ Created subfolder: {subfolder}", fg="green"))
    
    click.echo()
    
    # Step 3: Hotkey
    click.echo(click.style("Step 3: Hotkey", fg="yellow", bold=True))
    click.echo("Default hotkey is ⌘⇧N (Cmd+Shift+N)")
    
    if click.confirm("Use default hotkey?", default=True):
        pass  # Keep default
    else:
        click.echo("Enter key (single letter or number):")
        key = click.prompt("Key", default="n")
        config["hotkey"]["key"] = key.lower()
        
        click.echo("Modifiers (comma-separated: cmd,shift,ctrl,alt):")
        mods = click.prompt("Modifiers", default="cmd,shift")
        config["hotkey"]["modifiers"] = [m.strip() for m in mods.split(",")]
    
    click.echo()
    
    # Step 4: LLM Provider
    click.echo(click.style("Step 4: Transcript Cleanup", fg="yellow", bold=True))
    click.echo("Choose how to clean up your voice transcripts:\n")
    
    providers = list(LLM_PROVIDERS.keys())
    for i, key in enumerate(providers, 1):
        provider = LLM_PROVIDERS[key]
        cost_str = f" ({provider['cost']})" if provider.get('cost') else ""
        click.echo(f"  {click.style(str(i), fg='green', bold=True)}. {provider['name']}{cost_str}")
        click.echo(f"     {provider['description']}\n")
    
    # Force explicit choice - no default
    while True:
        choice_str = click.prompt(
            "Select provider (1-4)",
            type=str,
        )
        try:
            choice = int(choice_str)
            if 1 <= choice <= len(providers):
                break
            click.echo(click.style("Please enter a number between 1 and 4", fg="red"))
        except ValueError:
            click.echo(click.style("Please enter a number between 1 and 4", fg="red"))
    
    provider_key = providers[choice - 1]
    config["llm"]["provider"] = provider_key
    
    # Handle provider-specific setup
    if provider_key == "ollama":
        _setup_ollama(config)
    elif provider_key == "openai":
        _setup_openai_key()
    elif provider_key == "anthropic":
        _setup_anthropic_key()
    elif provider_key == "none":
        click.echo(click.style("✓ Skipping cleanup - raw transcriptions will be saved", fg="green"))
    
    click.echo()
    
    # Step 5: Feedback preferences
    click.echo(click.style("Step 5: Feedback Preferences", fg="yellow", bold=True))
    
    config["feedback"]["sounds"] = click.confirm("Enable sound feedback?", default=True)
    config["feedback"]["notifications"] = click.confirm("Enable macOS notifications?", default=True)
    config["feedback"]["menubar_icon"] = click.confirm("Show menubar icon?", default=True)
    
    click.echo()
    
    # Save config
    ensure_config_dirs()
    save_config(config)
    
    click.echo(click.style("✓ Configuration saved!", fg="green", bold=True))
    click.echo()
    
    # Offer to install auto-start
    if click.confirm("Enable auto-start on login?", default=True):
        install_launchd()
        config["daemon"]["auto_start"] = True
        save_config(config)
        click.echo(click.style("✓ Auto-start enabled", fg="green"))
    
    click.echo()
    click.echo(click.style("🎉 Setup complete!", fg="cyan", bold=True))
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Start Navi:  {click.style('navi start', fg='green')}")
    click.echo(f"  2. Press {click.style('⌘⇧N', fg='yellow')} to start recording")
    click.echo(f"  3. Press {click.style('⌘⇧N', fg='yellow')} again to stop and save")
    click.echo()


def _setup_ollama(config: dict) -> None:
    """Set up Ollama for local LLM processing."""
    click.echo()
    
    # Check if Ollama is installed
    try:
        result = subprocess.run(
            ["which", "ollama"],
            capture_output=True,
            text=True,
        )
        ollama_installed = result.returncode == 0
    except Exception:
        ollama_installed = False
    
    if ollama_installed:
        click.echo(click.style("✓ Ollama is already installed", fg="green"))
    else:
        click.echo("Ollama is not installed.")
        if click.confirm("Would you like to install Ollama now?", default=True):
            click.echo("Installing Ollama via Homebrew...")
            try:
                subprocess.run(
                    ["brew", "install", "ollama"],
                    check=True,
                )
                click.echo(click.style("✓ Ollama installed successfully", fg="green"))
                ollama_installed = True
            except subprocess.CalledProcessError:
                click.echo(click.style("✗ Failed to install Ollama", fg="red"))
                click.echo("  Please install manually: brew install ollama")
                return
            except FileNotFoundError:
                click.echo(click.style("✗ Homebrew not found", fg="red"))
                click.echo("  Please install Ollama manually: https://ollama.ai")
                return
        else:
            click.echo("Please install Ollama manually: brew install ollama")
            return
    
    # Check if Ollama is running
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ollama_running = result.returncode == 0
    except Exception:
        ollama_running = False
    
    if not ollama_running:
        click.echo("Starting Ollama service...")
        try:
            # Start Ollama in background
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            import time
            time.sleep(2)  # Give it time to start
            click.echo(click.style("✓ Ollama service started", fg="green"))
        except Exception as e:
            click.echo(click.style(f"⚠️  Could not start Ollama: {e}", fg="yellow"))
            click.echo("  Start it manually with: ollama serve")
    
    # Check if model is available
    model = config["llm"]["ollama"]["model"]
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        model_available = model in result.stdout
    except Exception:
        model_available = False
    
    if model_available:
        click.echo(click.style(f"✓ Model '{model}' is available", fg="green"))
    else:
        click.echo(f"Model '{model}' is not downloaded.")
        if click.confirm(f"Would you like to download '{model}' now? (~2GB)", default=True):
            click.echo(f"Downloading {model}... (this may take a few minutes)")
            try:
                subprocess.run(
                    ["ollama", "pull", model],
                    check=True,
                )
                click.echo(click.style(f"✓ Model '{model}' downloaded successfully", fg="green"))
            except subprocess.CalledProcessError:
                click.echo(click.style(f"✗ Failed to download model", fg="red"))
                click.echo(f"  Please download manually: ollama pull {model}")
        else:
            click.echo(f"Please download the model manually: ollama pull {model}")


def _setup_openai_key() -> None:
    """Set up OpenAI API key."""
    from navi.keychain import store_api_key, validate_openai_key, has_api_key
    
    click.echo()
    
    if has_api_key("openai"):
        if not click.confirm("OpenAI API key already stored. Replace it?", default=False):
            click.echo(click.style("✓ Using existing API key", fg="green"))
            return
    
    click.echo("Enter your OpenAI API key.")
    click.echo("Get one at: https://platform.openai.com/api-keys")
    click.echo()
    
    while True:
        api_key = click.prompt("API key", hide_input=True)
        
        if not api_key.startswith("sk-"):
            click.echo(click.style("Invalid format. OpenAI keys start with 'sk-'", fg="red"))
            continue
        
        click.echo("Validating API key...")
        is_valid, message = validate_openai_key(api_key)
        
        if is_valid:
            store_api_key("openai", api_key)
            click.echo(click.style("✓ API key validated and stored securely", fg="green"))
            break
        else:
            click.echo(click.style(f"✗ {message}", fg="red"))
            if not click.confirm("Try again?", default=True):
                click.echo("OpenAI setup skipped. You can add the key later with 'navi setup'")
                break


def _setup_anthropic_key() -> None:
    """Set up Anthropic API key."""
    from navi.keychain import store_api_key, validate_anthropic_key, has_api_key
    
    click.echo()
    
    if has_api_key("anthropic"):
        if not click.confirm("Anthropic API key already stored. Replace it?", default=False):
            click.echo(click.style("✓ Using existing API key", fg="green"))
            return
    
    click.echo("Enter your Anthropic API key.")
    click.echo("Get one at: https://console.anthropic.com/settings/keys")
    click.echo()
    
    while True:
        api_key = click.prompt("API key", hide_input=True)
        
        if not api_key.startswith("sk-ant-"):
            click.echo(click.style("Invalid format. Anthropic keys start with 'sk-ant-'", fg="red"))
            continue
        
        click.echo("Validating API key...")
        is_valid, message = validate_anthropic_key(api_key)
        
        if is_valid:
            store_api_key("anthropic", api_key)
            click.echo(click.style("✓ API key validated and stored securely", fg="green"))
            break
        else:
            click.echo(click.style(f"✗ {message}", fg="red"))
            if not click.confirm("Try again?", default=True):
                click.echo("Anthropic setup skipped. You can add the key later with 'navi setup'")
                break


@main.command()
def start():
    """Start the Navi background daemon."""
    if not config_exists():
        click.echo(click.style("⚠️  Navi is not configured yet.", fg="yellow"))
        click.echo("   Run: navi setup")
        return
    
    # Check ffmpeg before starting
    if not _check_ffmpeg():
        click.echo(click.style("⚠️  ffmpeg is not installed.", fg="yellow"))
        click.echo("   Install with: brew install ffmpeg")
        return
    
    config = load_config()
    errors = validate_config(config)
    
    if errors:
        click.echo(click.style("⚠️  Configuration errors:", fg="yellow"))
        for error in errors:
            click.echo(f"   - {error}")
        return
    
    if is_daemon_running():
        click.echo(click.style("✓ Navi is already running", fg="green"))
        return
    
    click.echo("Starting Navi...")
    start_daemon()
    click.echo(click.style("✓ Navi is now running", fg="green"))
    
    # Show hotkey reminder
    mods = config["hotkey"]["modifiers"]
    key = config["hotkey"]["key"].upper()
    hotkey_str = "+".join([m.title() for m in mods] + [key])
    click.echo(f"   Press {click.style(hotkey_str, fg='yellow')} to start/stop recording")


@main.command()
def stop():
    """Stop the Navi background daemon."""
    if not is_daemon_running():
        click.echo("Navi is not running")
        return
    
    click.echo("Stopping Navi...")
    stop_daemon()
    click.echo(click.style("✓ Navi stopped", fg="green"))


@main.command()
def status():
    """Check if the Navi daemon is running."""
    if is_daemon_running():
        click.echo(click.style("✓ Navi is running", fg="green"))
        
        pid_file = get_pid_file()
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            click.echo(f"   PID: {pid}")
        
        config = load_config()
        mods = config["hotkey"]["modifiers"]
        key = config["hotkey"]["key"].upper()
        hotkey_str = "+".join([m.title() for m in mods] + [key])
        click.echo(f"   Hotkey: {hotkey_str}")
        
        # Show LLM provider
        provider = config.get("llm", {}).get("provider", "unknown")
        provider_name = LLM_PROVIDERS.get(provider, {}).get("name", provider)
        click.echo(f"   LLM: {provider_name}")
    else:
        click.echo("Navi is not running")
        click.echo("   Start with: navi start")
    
    # Show LaunchAgent status
    if is_launchd_installed():
        click.echo(click.style("✓ Auto-start is enabled", fg="green"))
    else:
        click.echo("   Auto-start is disabled")


@main.command()
def install():
    """Enable auto-start on login."""
    if not config_exists():
        click.echo(click.style("⚠️  Navi is not configured yet.", fg="yellow"))
        click.echo("   Run: navi setup")
        return
    
    if is_launchd_installed():
        click.echo(click.style("✓ Auto-start is already enabled", fg="green"))
        return
    
    install_launchd()
    
    config = load_config()
    config["daemon"]["auto_start"] = True
    save_config(config)
    
    click.echo(click.style("✓ Auto-start enabled", fg="green"))
    click.echo("   Navi will start automatically when you log in")


@main.command()
def uninstall():
    """Disable auto-start on login."""
    if not is_launchd_installed():
        click.echo("Auto-start is not enabled")
        return
    
    uninstall_launchd()
    
    if config_exists():
        config = load_config()
        config["daemon"]["auto_start"] = False
        save_config(config)
    
    click.echo(click.style("✓ Auto-start disabled", fg="green"))


@main.command()
def config():
    """Show current configuration."""
    if not config_exists():
        click.echo(click.style("⚠️  Navi is not configured yet.", fg="yellow"))
        click.echo("   Run: navi setup")
        return
    
    cfg = load_config()
    
    click.echo(click.style("\n📋 Navi Configuration\n", fg="cyan", bold=True))
    
    # Hotkey
    mods = cfg["hotkey"]["modifiers"]
    key = cfg["hotkey"]["key"].upper()
    hotkey_str = "+".join([m.title() for m in mods] + [key])
    click.echo(f"Hotkey:         {click.style(hotkey_str, fg='yellow')}")
    
    # Whisper
    click.echo(f"Whisper model:  {cfg['whisper']['model']}")
    
    # LLM Provider
    llm_config = cfg.get("llm", {})
    provider = llm_config.get("provider", "ollama")
    provider_name = LLM_PROVIDERS.get(provider, {}).get("name", provider)
    click.echo(f"LLM provider:   {provider_name}")
    
    if provider == "ollama":
        ollama_config = llm_config.get("ollama", {})
        click.echo(f"  Model:        {ollama_config.get('model', 'llama3.2')}")
        click.echo(f"  Host:         {ollama_config.get('host', 'http://localhost:11434')}")
    elif provider == "openai":
        from navi.keychain import has_api_key
        has_key = "✓" if has_api_key("openai") else "✗"
        click.echo(f"  API key:      {has_key}")
        click.echo(f"  Model:        {llm_config.get('openai', {}).get('model', 'gpt-4o-mini')}")
    elif provider == "anthropic":
        from navi.keychain import has_api_key
        has_key = "✓" if has_api_key("anthropic") else "✗"
        click.echo(f"  API key:      {has_key}")
        click.echo(f"  Model:        {llm_config.get('anthropic', {}).get('model', 'claude-3-haiku-20240307')}")
    
    # Output
    click.echo(f"Vault path:     {cfg['output']['vault_path']}")
    if cfg['output']['subfolder']:
        click.echo(f"Subfolder:      {cfg['output']['subfolder']}")
    
    # Feedback
    click.echo(f"Sounds:         {'✓' if cfg['feedback']['sounds'] else '✗'}")
    click.echo(f"Notifications:  {'✓' if cfg['feedback']['notifications'] else '✗'}")
    click.echo(f"Menubar icon:   {'✓' if cfg['feedback']['menubar_icon'] else '✗'}")
    
    # Daemon
    click.echo(f"Auto-start:     {'✓' if cfg['daemon']['auto_start'] else '✗'}")
    
    click.echo()
    click.echo(f"Config file:    ~/.config/navi/config.yaml")
    click.echo()


@main.command()
def test():
    """Test microphone and transcription."""
    if not config_exists():
        click.echo(click.style("⚠️  Navi is not configured yet.", fg="yellow"))
        click.echo("   Run: navi setup")
        return
    
    click.echo(click.style("\n🎤 Testing Navi\n", fg="cyan", bold=True))
    
    # Test 0: ffmpeg
    click.echo("0. Checking ffmpeg...")
    if _check_ffmpeg():
        click.echo(click.style("   ✓ ffmpeg is installed", fg="green"))
    else:
        click.echo(click.style("   ✗ ffmpeg is not installed", fg="red"))
        click.echo("     Install with: brew install ffmpeg")
        return
    
    # Test 1: Microphone access
    click.echo("1. Testing microphone access...")
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_device = sd.query_devices(kind='input')
        click.echo(click.style(f"   ✓ Found input device: {input_device['name']}", fg="green"))
    except Exception as e:
        click.echo(click.style(f"   ✗ Microphone error: {e}", fg="red"))
        click.echo("     Grant microphone access in System Preferences > Privacy & Security")
        return
    
    # Test 2: LLM provider
    config = load_config()
    provider = config.get("llm", {}).get("provider", "ollama")
    provider_name = LLM_PROVIDERS.get(provider, {}).get("name", provider)
    
    click.echo(f"2. Testing {provider_name} connection...")
    
    if provider == "ollama":
        try:
            import requests
            response = requests.get(f"{config['llm']['ollama']['host']}/api/tags", timeout=5)
            if response.status_code == 200:
                click.echo(click.style("   ✓ Ollama is running", fg="green"))
            else:
                click.echo(click.style("   ✗ Ollama returned an error", fg="red"))
        except Exception:
            click.echo(click.style("   ✗ Cannot connect to Ollama", fg="yellow"))
            click.echo("     Start Ollama with: ollama serve")
    elif provider == "openai":
        from navi.keychain import has_api_key, get_api_key, validate_openai_key
        if has_api_key("openai"):
            api_key = get_api_key("openai")
            is_valid, message = validate_openai_key(api_key)
            if is_valid:
                click.echo(click.style("   ✓ OpenAI API key is valid", fg="green"))
            else:
                click.echo(click.style(f"   ✗ {message}", fg="red"))
        else:
            click.echo(click.style("   ✗ OpenAI API key not found", fg="red"))
            click.echo("     Run 'navi setup' to add your API key")
    elif provider == "anthropic":
        from navi.keychain import has_api_key, get_api_key, validate_anthropic_key
        if has_api_key("anthropic"):
            api_key = get_api_key("anthropic")
            is_valid, message = validate_anthropic_key(api_key)
            if is_valid:
                click.echo(click.style("   ✓ Anthropic API key is valid", fg="green"))
            else:
                click.echo(click.style(f"   ✗ {message}", fg="red"))
        else:
            click.echo(click.style("   ✗ Anthropic API key not found", fg="red"))
            click.echo("     Run 'navi setup' to add your API key")
    elif provider == "none":
        click.echo(click.style("   ✓ No LLM configured (raw transcription)", fg="green"))
    
    # Test 3: Whisper model
    click.echo("3. Testing Whisper model...")
    click.echo("   (This may take a moment on first run as the model downloads)")
    try:
        from navi.transcribe import load_whisper_model
        model = load_whisper_model(config["whisper"]["model"])
        click.echo(click.style(f"   ✓ Whisper model '{config['whisper']['model']}' loaded", fg="green"))
    except Exception as e:
        click.echo(click.style(f"   ✗ Whisper error: {e}", fg="red"))
    
    # Test 4: Vault path
    click.echo("4. Testing vault access...")
    vault_path = Path(config["output"]["vault_path"])
    if vault_path.exists():
        click.echo(click.style(f"   ✓ Vault accessible: {vault_path}", fg="green"))
    else:
        click.echo(click.style(f"   ✗ Vault not found: {vault_path}", fg="red"))
    
    click.echo()
    click.echo(click.style("✓ All tests passed!", fg="green", bold=True))
    click.echo()


if __name__ == "__main__":
    main()
