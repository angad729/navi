"""
LLM processing for Navi.

Supports multiple providers: Ollama (local), OpenAI, Anthropic, or none.
"""

import json
import re
from typing import Any, Optional

import requests

from navi.keychain import get_api_key


class LLMError(Exception):
    """Raised when LLM processing fails."""
    pass


def check_ollama_available(host: str = "http://localhost:11434") -> bool:
    """
    Check if Ollama is running and accessible.
    
    Args:
        host: Ollama host URL
        
    Returns:
        True if Ollama is available
    """
    try:
        response = requests.get(f"{host}/api/tags", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def check_model_available(
    model: str,
    host: str = "http://localhost:11434"
) -> bool:
    """
    Check if a specific model is available in Ollama.
    
    Args:
        model: Model name (e.g., "llama3.2")
        host: Ollama host URL
        
    Returns:
        True if model is available
    """
    try:
        response = requests.get(f"{host}/api/tags", timeout=5)
        if response.status_code != 200:
            return False
        
        data = response.json()
        models = [m["name"].split(":")[0] for m in data.get("models", [])]
        return model in models or model.split(":")[0] in models
    except requests.exceptions.RequestException:
        return False


def process_transcript(
    transcript: str,
    config: dict[str, Any],
) -> dict[str, str]:
    """
    Process a raw transcript through the configured LLM provider.
    
    Args:
        transcript: Raw transcript text
        config: Navi configuration dictionary
        
    Returns:
        Dictionary with:
        - title: Extracted title
        - content: Cleaned transcript
        
    Raises:
        LLMError: If processing fails
    """
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "ollama")
    
    if provider == "none":
        return process_transcript_simple(transcript)
    elif provider == "ollama":
        return _process_with_ollama(transcript, llm_config)
    elif provider == "openai":
        return _process_with_openai(transcript, llm_config)
    elif provider == "anthropic":
        return _process_with_anthropic(transcript, llm_config)
    else:
        raise LLMError(f"Unknown LLM provider: {provider}")


def _process_with_ollama(
    transcript: str,
    llm_config: dict[str, Any],
) -> dict[str, str]:
    """Process transcript using Ollama."""
    ollama_config = llm_config.get("ollama", {})
    host = ollama_config.get("host", "http://localhost:11434")
    model = ollama_config.get("model", "llama3.2")
    prompt_template = llm_config.get("cleanup_prompt", "")
    
    prompt = f"{prompt_template}\n\nTranscript:\n{transcript}"
    
    try:
        response = requests.post(
            f"{host}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 2048,
                },
            },
            timeout=60,
        )
        
        if response.status_code != 200:
            raise LLMError(f"Ollama returned status {response.status_code}")
        
        data = response.json()
        result_text = data.get("response", "").strip()
        
        return _parse_llm_response(result_text, transcript)
    
    except requests.exceptions.Timeout:
        raise LLMError("Ollama request timed out")
    except requests.exceptions.ConnectionError:
        raise LLMError(
            "Cannot connect to Ollama. Is it running? Start with: ollama serve"
        )
    except json.JSONDecodeError:
        raise LLMError("Invalid response from Ollama")


def _process_with_openai(
    transcript: str,
    llm_config: dict[str, Any],
) -> dict[str, str]:
    """Process transcript using OpenAI API."""
    api_key = get_api_key("openai")
    if not api_key:
        raise LLMError("OpenAI API key not found. Run 'navi setup' to configure.")
    
    openai_config = llm_config.get("openai", {})
    model = openai_config.get("model", "gpt-4o-mini")
    prompt_template = llm_config.get("cleanup_prompt", "")
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": prompt_template},
                    {"role": "user", "content": f"Transcript:\n{transcript}"},
                ],
                "temperature": 0.3,
                "max_tokens": 2048,
            },
            timeout=60,
        )
        
        if response.status_code == 401:
            raise LLMError("Invalid OpenAI API key")
        elif response.status_code != 200:
            raise LLMError(f"OpenAI API error: {response.status_code}")
        
        data = response.json()
        result_text = data["choices"][0]["message"]["content"].strip()
        
        return _parse_llm_response(result_text, transcript)
    
    except requests.exceptions.Timeout:
        raise LLMError("OpenAI request timed out")
    except requests.exceptions.ConnectionError:
        raise LLMError("Cannot connect to OpenAI API")
    except (KeyError, IndexError) as e:
        raise LLMError(f"Invalid response from OpenAI: {e}")


def _process_with_anthropic(
    transcript: str,
    llm_config: dict[str, Any],
) -> dict[str, str]:
    """Process transcript using Anthropic API."""
    api_key = get_api_key("anthropic")
    if not api_key:
        raise LLMError("Anthropic API key not found. Run 'navi setup' to configure.")
    
    anthropic_config = llm_config.get("anthropic", {})
    model = anthropic_config.get("model", "claude-3-haiku-20240307")
    prompt_template = llm_config.get("cleanup_prompt", "")
    
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 2048,
                "system": prompt_template,
                "messages": [
                    {"role": "user", "content": f"Transcript:\n{transcript}"},
                ],
            },
            timeout=60,
        )
        
        if response.status_code == 401:
            raise LLMError("Invalid Anthropic API key")
        elif response.status_code != 200:
            raise LLMError(f"Anthropic API error: {response.status_code}")
        
        data = response.json()
        result_text = data["content"][0]["text"].strip()
        
        return _parse_llm_response(result_text, transcript)
    
    except requests.exceptions.Timeout:
        raise LLMError("Anthropic request timed out")
    except requests.exceptions.ConnectionError:
        raise LLMError("Cannot connect to Anthropic API")
    except (KeyError, IndexError) as e:
        raise LLMError(f"Invalid response from Anthropic: {e}")


def _parse_llm_response(response: str, original: str) -> dict[str, str]:
    """
    Parse the LLM response to extract title and content.
    
    Args:
        response: Raw response from LLM
        original: Original transcript (fallback)
        
    Returns:
        Dictionary with title and content
    """
    # Try to extract title and content from the expected format
    title_match = re.search(r"TITLE:\s*(.+?)(?:\n|---)", response, re.IGNORECASE)
    
    if title_match:
        title = title_match.group(1).strip()
        
        # Get content after the separator
        content_match = re.search(r"---\s*\n(.+)", response, re.DOTALL)
        if content_match:
            content = content_match.group(1).strip()
        else:
            # Try to get everything after the title line
            content = re.sub(r"^TITLE:\s*.+?\n", "", response, flags=re.IGNORECASE).strip()
            content = re.sub(r"^---\s*", "", content).strip()
    else:
        # Fallback: use first line as title, rest as content
        lines = response.strip().split("\n")
        if lines:
            title = _generate_fallback_title(lines[0])
            content = "\n".join(lines[1:]).strip() or response.strip()
        else:
            title = _generate_fallback_title(original)
            content = original
    
    # Clean up title
    title = _clean_title(title)
    
    return {
        "title": title,
        "content": content,
    }


def _generate_fallback_title(text: str) -> str:
    """Generate a title from the first part of text."""
    # Take first 50 characters and clean up
    title = text[:50].strip()
    
    # Remove any trailing incomplete words
    if len(text) > 50:
        last_space = title.rfind(" ")
        if last_space > 20:
            title = title[:last_space]
    
    return title


def _clean_title(title: str) -> str:
    """Clean up a title for use in filename."""
    # Remove quotes
    title = title.strip('"\'')
    
    # Remove markdown formatting
    title = re.sub(r"\*\*(.+?)\*\*", r"\1", title)
    title = re.sub(r"\*(.+?)\*", r"\1", title)
    
    # Remove characters that are problematic in filenames
    title = re.sub(r'[<>:"/\\|?*]', "", title)
    
    # Collapse multiple spaces
    title = re.sub(r"\s+", " ", title)
    
    # Limit length
    if len(title) > 60:
        title = title[:57] + "..."
    
    return title.strip()


def process_transcript_simple(transcript: str) -> dict[str, str]:
    """
    Simple transcript processing without LLM.
    
    Just extracts a title from the first sentence and returns
    the transcript as-is. Use as fallback when no LLM is configured.
    
    Args:
        transcript: Raw transcript text
        
    Returns:
        Dictionary with title and content
    """
    # Split into sentences
    sentences = re.split(r"[.!?]+", transcript)
    
    if sentences:
        title = _clean_title(sentences[0].strip())
    else:
        title = "Voice Note"
    
    return {
        "title": title,
        "content": transcript,
    }


# Keep old name for backward compatibility
OllamaError = LLMError
