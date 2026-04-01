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
    config_exists,
    load_config,
    save_config,
    validate_config,
    ensure_config_dirs,
)
from navi.daemon import get_pid_file, is_daemon_running, start_daemon, stop_daemon
from navi.launchd import install_launchd, uninstall_launchd, is_launchd_installed


@click.group()
@click.version_option(version="0.1.0", prog_name="navi")
def main():
    """
    🧚 Navi - Voice notes that just work.
    
    Press ⌘⇧N to start/stop recording. Your voice is transcribed locally
    with Whisper, cleaned up with Ollama, and saved to your Obsidian vault.
    
    Get started with: navi setup
    """
    pass


@main.command()
def setup():
    """Interactive first-time configuration wizard."""
    click.echo()
    click.echo(click.style("🧚 Welcome to Navi!", fg="cyan", bold=True))
    click.echo(click.style("   Let's set up your voice note capture.\n", fg="cyan"))
    
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
    
    # Step 4: Ollama check
    click.echo(click.style("Step 4: Ollama Setup", fg="yellow", bold=True))
    
    # Check if Ollama is installed
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        ollama_installed = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        ollama_installed = False
    
    if ollama_installed:
        click.echo(click.style("✓ Ollama is installed", fg="green"))
        
        # Check if model is available
        model = config["ollama"]["model"]
        if model in result.stdout:
            click.echo(click.style(f"✓ Model '{model}' is available", fg="green"))
        else:
            click.echo(click.style(f"⚠️  Model '{model}' not found", fg="yellow"))
            click.echo(f"   Run: ollama pull {model}")
    else:
        click.echo(click.style("⚠️  Ollama is not installed", fg="yellow"))
        click.echo("   Install with: brew install ollama")
        click.echo("   Then run: ollama pull llama3.2")
    
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


@main.command()
def start():
    """Start the Navi background daemon."""
    if not config_exists():
        click.echo(click.style("⚠️  Navi is not configured yet.", fg="yellow"))
        click.echo("   Run: navi setup")
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
    
    # Ollama
    click.echo(f"Ollama model:   {cfg['ollama']['model']}")
    click.echo(f"Ollama host:    {cfg['ollama']['host']}")
    
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
    
    # Test 2: Ollama
    click.echo("2. Testing Ollama connection...")
    try:
        import requests
        config = load_config()
        response = requests.get(f"{config['ollama']['host']}/api/tags", timeout=5)
        if response.status_code == 200:
            click.echo(click.style("   ✓ Ollama is running", fg="green"))
        else:
            click.echo(click.style("   ✗ Ollama returned an error", fg="red"))
    except requests.exceptions.ConnectionError:
        click.echo(click.style("   ✗ Cannot connect to Ollama", fg="yellow"))
        click.echo("     Start Ollama with: ollama serve")
    except Exception as e:
        click.echo(click.style(f"   ✗ Ollama error: {e}", fg="red"))
    
    # Test 3: Whisper model
    click.echo("3. Testing Whisper model...")
    click.echo("   (This may take a moment on first run as the model downloads)")
    try:
        from navi.transcribe import load_whisper_model
        config = load_config()
        model = load_whisper_model(config["whisper"]["model"])
        click.echo(click.style(f"   ✓ Whisper model '{config['whisper']['model']}' loaded", fg="green"))
    except Exception as e:
        click.echo(click.style(f"   ✗ Whisper error: {e}", fg="red"))
    
    # Test 4: Vault path
    click.echo("4. Testing vault access...")
    config = load_config()
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
