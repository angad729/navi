"""
LLM processing for Navi.

Supports multiple providers: Ollama (local), OpenAI, Anthropic, or none.
Includes smart entity extraction and vault linking.
"""

import json
import re
from pathlib import Path
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


def get_existing_notes(vault_path: str, subfolder: str = "") -> set[str]:
    """
    Scan vault for existing note titles to enable smart linking.
    
    Args:
        vault_path: Path to Obsidian vault
        subfolder: Optional subfolder to limit scan
        
    Returns:
        Set of note names (without .md extension)
    """
    vault = Path(vault_path)
    if not vault.exists():
        return set()
    
    notes = set()
    
    # Scan the vault (or subfolder)
    scan_path = vault / subfolder if subfolder else vault
    
    if scan_path.exists():
        for md_file in scan_path.rglob("*.md"):
            # Get the note name without extension
            note_name = md_file.stem
            notes.add(note_name.lower())
    
    return notes


def resolve_entity_links(
    entities: list[dict[str, str]],
    existing_notes: set[str],
) -> list[dict[str, Any]]:
    """
    Resolve entities to wikilinks, checking if notes exist.
    
    Args:
        entities: List of entity dicts with 'name' and 'type'
        existing_notes: Set of existing note names (lowercase)
        
    Returns:
        List of entities with 'link' field added (None if no match)
    """
    resolved = []
    
    for entity in entities:
        name = entity.get("name", "")
        entity_type = entity.get("type", "unknown")
        
        # Check if a note with this name exists
        name_lower = name.lower()
        
        # Try exact match first
        if name_lower in existing_notes:
            entity["link"] = f"[[{name}]]"
        else:
            # Try partial matches (e.g., "John" matches "John Smith")
            matches = [n for n in existing_notes if name_lower in n or n in name_lower]
            if len(matches) == 1:
                # Only link if there's exactly one match (high confidence)
                # Reconstruct the original case from the filename
                entity["link"] = f"[[{name}]]"
            else:
                entity["link"] = None
        
        resolved.append(entity)
    
    return resolved


def process_transcript(
    transcript: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    Process a raw transcript through the configured LLM provider.
    
    Args:
        transcript: Raw transcript text
        config: Navi configuration dictionary
        
    Returns:
        Dictionary with:
        - title: Extracted title
        - content: Full formatted note content
        - tags: List of tags
        - entities: List of extracted entities
        - related: List of wikilinks to related notes
        
    Raises:
        LLMError: If processing fails
    """
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "ollama")
    
    if provider == "none":
        return process_transcript_simple(transcript)
    elif provider == "ollama":
        result = _process_with_ollama(transcript, llm_config)
    elif provider == "openai":
        result = _process_with_openai(transcript, llm_config)
    elif provider == "anthropic":
        result = _process_with_anthropic(transcript, llm_config)
    else:
        raise LLMError(f"Unknown LLM provider: {provider}")
    
    # Resolve entity links against existing vault notes
    output_config = config.get("output", {})
    vault_path = output_config.get("vault_path", "")
    subfolder = output_config.get("subfolder", "")
    
    if vault_path:
        existing_notes = get_existing_notes(vault_path, subfolder)
        result["entities"] = resolve_entity_links(
            result.get("entities", []),
            existing_notes,
        )
    
    # Build the related links list (only entities with confirmed links)
    result["related"] = [
        e["link"] for e in result.get("entities", [])
        if e.get("link")
    ]
    
    return result


def _process_with_ollama(
    transcript: str,
    llm_config: dict[str, Any],
) -> dict[str, Any]:
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
                "format": "json",
                "options": {
                    "temperature": 0.3,
                    "num_predict": 4096,
                },
            },
            timeout=120,
        )
        
        if response.status_code != 200:
            raise LLMError(f"Ollama returned status {response.status_code}")
        
        data = response.json()
        result_text = data.get("response", "").strip()[:100_000]

        return _parse_json_response(result_text, transcript)

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
) -> dict[str, Any]:
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
                "max_tokens": 4096,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        
        if response.status_code == 401:
            raise LLMError("Invalid OpenAI API key")
        elif response.status_code != 200:
            raise LLMError(f"OpenAI API error: {response.status_code}")
        
        data = response.json()
        result_text = data["choices"][0]["message"]["content"].strip()[:100_000]

        return _parse_json_response(result_text, transcript)

    except requests.exceptions.Timeout:
        raise LLMError("OpenAI request timed out")
    except requests.exceptions.ConnectionError:
        raise LLMError("Cannot connect to OpenAI API")
    except (KeyError, IndexError) as e:
        raise LLMError(f"Invalid response from OpenAI: {e}")


def _process_with_anthropic(
    transcript: str,
    llm_config: dict[str, Any],
) -> dict[str, Any]:
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
                "max_tokens": 4096,
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
        result_text = data["content"][0]["text"].strip()[:100_000]

        return _parse_json_response(result_text, transcript)

    except requests.exceptions.Timeout:
        raise LLMError("Anthropic request timed out")
    except requests.exceptions.ConnectionError:
        raise LLMError("Cannot connect to Anthropic API")
    except (KeyError, IndexError) as e:
        raise LLMError(f"Invalid response from Anthropic: {e}")


def _parse_json_response(response: str, original: str) -> dict[str, Any]:
    """
    Parse the JSON response from LLM.
    
    Args:
        response: Raw response from LLM (should be JSON)
        original: Original transcript (fallback)
        
    Returns:
        Dictionary with title, tags, entities, summary, transcript
    """
    # Try to extract JSON from the response
    try:
        # Clean up response - remove markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        data = json.loads(cleaned)
        
        return {
            "title": _clean_title(data.get("title", "Untitled Note")),
            "tags": data.get("tags", []),
            "entities": data.get("entities", []),
            "summary": data.get("summary", ""),
            "transcript": data.get("transcript", original),
        }
    
    except json.JSONDecodeError:
        # Fallback to simple parsing if JSON fails
        return _parse_legacy_response(response, original)


def _parse_legacy_response(response: str, original: str) -> dict[str, Any]:
    """
    Fallback parser for non-JSON responses.
    
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
    
    return {
        "title": _clean_title(title),
        "tags": [],
        "entities": [],
        "summary": "",
        "transcript": content,
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

    # Remove characters that are problematic in filenames or YAML (including newlines)
    title = title.replace("\n", " ").replace("\r", " ")
    title = re.sub(r'[<>:"/\\|?*/\x00]', "", title)

    # Collapse multiple spaces
    title = re.sub(r"\s+", " ", title)

    # Limit length
    if len(title) > 60:
        title = title[:57] + "..."

    return title.strip()


def call_llm(prompt: str, config: dict[str, Any]) -> str:
    """
    Call the configured LLM with a plain text prompt.

    Returns the response as a plain string, or an empty string if provider is "none"
    or if the call fails.
    """
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "none")

    try:
        if provider == "ollama":
            ollama_config = llm_config.get("ollama", {})
            host = ollama_config.get("host", "http://localhost:11434")
            model = ollama_config.get("model", "llama3.2")
            response = requests.post(
                f"{host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 500},
                },
                timeout=60,
            )
            if response.status_code == 200:
                return response.json().get("response", "").strip()

        elif provider == "openai":
            api_key = get_api_key("openai")
            model = llm_config.get("openai", {}).get("model", "gpt-4o-mini")
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
                timeout=60,
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()

        elif provider == "anthropic":
            api_key = get_api_key("anthropic")
            model = llm_config.get("anthropic", {}).get("model", "claude-3-haiku-20240307")
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            if response.status_code == 200:
                return response.json()["content"][0]["text"].strip()

    except Exception as e:
        # Log provider name only — avoid echoing prompt content which may contain PII
        print(f"call_llm error ({provider}): {type(e).__name__}")

    return ""


def process_transcript_simple(transcript: str) -> dict[str, Any]:
    """
    Simple transcript processing without LLM.
    
    Just extracts a title from the first sentence and returns
    the transcript as-is. Use as fallback when no LLM is configured.
    
    Args:
        transcript: Raw transcript text
        
    Returns:
        Dictionary with title, tags, entities, summary, transcript
    """
    # Split into sentences
    sentences = re.split(r"[.!?]+", transcript)
    
    if sentences:
        title = _clean_title(sentences[0].strip())
    else:
        title = "Note"
    
    return {
        "title": title,
        "tags": [],
        "entities": [],
        "summary": "",
        "transcript": transcript,
    }


# Keep old name for backward compatibility
OllamaError = LLMError
