"""
Secure credential storage using macOS Keychain.

Stores API keys securely using the system keychain.
"""

import subprocess
from typing import Optional


SERVICE_NAME = "navi-voice"


def store_api_key(provider: str, api_key: str) -> bool:
    """
    Store an API key in the macOS Keychain.
    
    Args:
        provider: Provider name (e.g., "openai", "anthropic")
        api_key: The API key to store
        
    Returns:
        True if successful, False otherwise
    """
    account = f"{SERVICE_NAME}-{provider}"
    
    # Delete existing key if present
    delete_api_key(provider)
    
    try:
        # Add new key to keychain
        subprocess.run(
            [
                "security", "add-generic-password",
                "-a", account,
                "-s", SERVICE_NAME,
                "-w", api_key,
                "-U",  # Update if exists
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_api_key(provider: str) -> Optional[str]:
    """
    Retrieve an API key from the macOS Keychain.
    
    Args:
        provider: Provider name (e.g., "openai", "anthropic")
        
    Returns:
        The API key, or None if not found
    """
    account = f"{SERVICE_NAME}-{provider}"
    
    try:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-a", account,
                "-s", SERVICE_NAME,
                "-w",  # Output only the password
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def delete_api_key(provider: str) -> bool:
    """
    Delete an API key from the macOS Keychain.
    
    Args:
        provider: Provider name (e.g., "openai", "anthropic")
        
    Returns:
        True if deleted, False if not found or error
    """
    account = f"{SERVICE_NAME}-{provider}"
    
    try:
        subprocess.run(
            [
                "security", "delete-generic-password",
                "-a", account,
                "-s", SERVICE_NAME,
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def has_api_key(provider: str) -> bool:
    """
    Check if an API key exists in the Keychain.
    
    Args:
        provider: Provider name (e.g., "openai", "anthropic")
        
    Returns:
        True if key exists
    """
    return get_api_key(provider) is not None


def validate_openai_key(api_key: str) -> tuple[bool, str]:
    """
    Validate an OpenAI API key by making a test request.
    
    Args:
        api_key: The API key to validate
        
    Returns:
        Tuple of (is_valid, message)
    """
    try:
        import requests
        
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        
        if response.status_code == 200:
            return True, "API key is valid"
        elif response.status_code == 401:
            return False, "Invalid API key"
        else:
            return False, f"API error: {response.status_code}"
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {e}"


def validate_anthropic_key(api_key: str) -> tuple[bool, str]:
    """
    Validate an Anthropic API key by making a test request.
    
    Args:
        api_key: The API key to validate
        
    Returns:
        Tuple of (is_valid, message)
    """
    try:
        import requests
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "Hi"}],
            },
            timeout=10,
        )
        
        if response.status_code == 200:
            return True, "API key is valid"
        elif response.status_code == 401:
            return False, "Invalid API key"
        elif response.status_code == 400:
            # Bad request but key is valid (we sent minimal request)
            error = response.json().get("error", {})
            if "invalid_api_key" in str(error):
                return False, "Invalid API key"
            return True, "API key is valid"
        else:
            return False, f"API error: {response.status_code}"
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {e}"
