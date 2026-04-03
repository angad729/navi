"""
Output handling for Navi.

Saves processed transcripts to the configured destination (Obsidian vault).
"""

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def save_note(
    processed: dict[str, Any],
    config: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> Path:
    """
    Save a processed note to the configured destination.
    
    Args:
        processed: Processed transcript dict with title, tags, entities, summary, transcript
        config: Navi configuration dictionary
        metadata: Optional metadata to include in frontmatter
        
    Returns:
        Path to saved file
    """
    output_config = config.get("output", {})
    destination = output_config.get("destination", "obsidian")
    
    if destination == "obsidian":
        return _save_to_obsidian(processed, output_config, metadata)
    else:
        # Default to generic markdown folder
        return _save_to_folder(processed, output_config, metadata)


def _save_to_obsidian(
    processed: dict[str, Any],
    output_config: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Save note to Obsidian vault."""
    vault_path = Path(output_config.get("vault_path", ""))
    subfolder = output_config.get("subfolder", "")
    
    if not vault_path.exists():
        raise ValueError(f"Obsidian vault not found: {vault_path}")
    
    # Build target directory (guard against path traversal in subfolder)
    if subfolder:
        target_dir = (vault_path / subfolder).resolve()
        if not str(target_dir).startswith(str(vault_path.resolve())):
            raise ValueError(f"Subfolder escapes vault: {subfolder}")
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = vault_path
    
    # Generate filename
    title = processed.get("title", "Untitled Note")
    filename = _generate_filename(title, output_config)
    filepath = target_dir / filename
    
    # Ensure unique filename
    filepath = _ensure_unique_path(filepath)
    
    # Build note content with frontmatter
    note_content = _build_note_content(processed, metadata)

    # Write atomically to avoid partial files on crash
    tmp_fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix=".md.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(note_content)
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return filepath


def _save_to_folder(
    processed: dict[str, Any],
    output_config: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Save note to a generic folder."""
    folder_path = Path(output_config.get("vault_path", ""))
    
    if not folder_path.exists():
        folder_path.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    title = processed.get("title", "Untitled Note")
    filename = _generate_filename(title, output_config)
    filepath = folder_path / filename
    
    # Ensure unique filename
    filepath = _ensure_unique_path(filepath)
    
    # Build note content
    note_content = _build_note_content(processed, metadata)

    # Write atomically
    tmp_fd, tmp_path = tempfile.mkstemp(dir=folder_path, suffix=".md.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(note_content)
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return filepath


def _generate_filename(title: str, output_config: dict[str, Any]) -> str:
    """
    Generate filename from template.
    
    Args:
        title: Note title
        output_config: Output configuration
        
    Returns:
        Filename with .md extension
    """
    template = output_config.get("filename_template", "{title} - {timestamp}")
    timestamp_format = output_config.get("timestamp_format", "%Y-%m-%d-%H%M%S")
    
    # Clean title for filename
    clean_title = _sanitize_filename(title)
    
    # Generate timestamp
    timestamp = datetime.now().strftime(timestamp_format)
    
    # Apply template
    filename = template.format(
        title=clean_title,
        timestamp=timestamp,
        date=datetime.now().strftime("%Y-%m-%d"),
        time=datetime.now().strftime("%H%M%S"),
    )
    
    # Ensure .md extension
    if not filename.endswith(".md"):
        filename += ".md"
    
    return filename


def _sanitize_filename(name: str) -> str:
    """
    Sanitize a string for use in filename.
    
    Args:
        name: Original name
        
    Returns:
        Sanitized name safe for filesystem
    """
    # Remove or replace problematic characters (including path separators and null bytes)
    name = re.sub(r'[<>:"/\\|?*/\x00]', "", name)
    
    # Replace multiple spaces/underscores with single space
    name = re.sub(r"[\s_]+", " ", name)
    
    # Remove leading/trailing whitespace and dots
    name = name.strip(". ")
    
    # Limit length (leaving room for timestamp and extension)
    if len(name) > 100:
        name = name[:97] + "..."
    
    return name


def _ensure_unique_path(filepath: Path) -> Path:
    """
    Ensure filepath is unique by adding number suffix if needed.
    
    Args:
        filepath: Desired filepath
        
    Returns:
        Unique filepath (may have number suffix)
    """
    if not filepath.exists():
        return filepath
    
    stem = filepath.stem
    suffix = filepath.suffix
    parent = filepath.parent
    
    import secrets
    counter = 1
    while True:
        new_path = parent / f"{stem} ({counter}){suffix}"
        if not new_path.exists():
            return new_path
        counter += 1

        if counter > 5:
            # Fall back to random suffix to avoid enumeration/timing issues
            rand = secrets.token_hex(4)
            new_path = parent / f"{stem}-{rand}{suffix}"
            if not new_path.exists():
                return new_path

        if counter > 1000:
            raise ValueError("Too many files with same name")


def _build_note_content(
    processed: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Build complete note content with frontmatter.
    
    Args:
        processed: Processed transcript dict
        metadata: Optional metadata for frontmatter
        
    Returns:
        Complete note content with YAML frontmatter
    """
    title = processed.get("title", "Untitled Note")
    tags = processed.get("tags", [])
    entities = processed.get("entities", [])
    related = processed.get("related", [])
    summary = processed.get("summary", "")
    transcript = processed.get("transcript", "")
    
    # Build frontmatter
    frontmatter_lines = [
        f'title: "{title}"',
        f"created: {datetime.now().isoformat()}",
        "source: navi",
        "type: note",
    ]
    
    # Add tags if present
    if tags:
        tags_str = ", ".join(tags)
        frontmatter_lines.append(f"tags: [{tags_str}]")
    
    # Add related links if present
    if related:
        related_str = ", ".join(related)
        frontmatter_lines.append(f"related: [{related_str}]")
    
    # Add metadata
    if metadata:
        if "duration" in metadata:
            frontmatter_lines.append(f"duration: {metadata['duration']:.1f}s")
        if "language" in metadata:
            frontmatter_lines.append(f"language: {metadata['language']}")
        if "model" in metadata:
            frontmatter_lines.append(f"whisper_model: {metadata['model']}")
    
    frontmatter = "\n".join(frontmatter_lines)
    
    # Build entity mentions for inline linking
    entity_links = []
    for entity in entities:
        if entity.get("link"):
            entity_links.append(entity["link"])
    
    # Insert wikilinks into transcript where entities are mentioned
    linked_transcript = _insert_entity_links(transcript, entities)
    linked_summary = _insert_entity_links(summary, entities)
    
    # Build the note body
    body_parts = [f"# {title}"]
    
    # Add Summary section if present
    if summary or linked_summary:
        body_parts.append("\n## Summary")
        body_parts.append(linked_summary or summary)
    
    # Add Transcript section
    body_parts.append("\n## Transcript")
    body_parts.append(linked_transcript or transcript)
    
    # Add tags at the bottom for Obsidian tag display
    if tags:
        tag_line = " ".join([f"#{tag}" for tag in tags])
        body_parts.append(f"\n---\n{tag_line}")
    
    body = "\n".join(body_parts)
    
    # Combine frontmatter and body
    note = f"""---
{frontmatter}
---

{body}
"""
    
    return note


def _insert_entity_links(text: str, entities: list[dict[str, Any]]) -> str:
    """
    Insert wikilinks for entities into text.
    
    Only inserts links for entities that have confirmed links
    and only on the first occurrence.
    
    Args:
        text: Original text
        entities: List of entity dicts with optional 'link' field
        
    Returns:
        Text with wikilinks inserted
    """
    if not text or not entities:
        return text
    
    result = text
    
    for entity in entities:
        name = entity.get("name", "")
        link = entity.get("link")
        
        if not name or not link:
            continue
        
        # Only replace the first occurrence
        # Use word boundaries to avoid partial matches
        pattern = rf'\b{re.escape(name)}\b'
        
        # Check if already linked (inside [[ ]])
        if f"[[{name}]]" in result:
            continue
        
        # Replace first occurrence only (use lambda to prevent backreference injection)
        result = re.sub(pattern, lambda m: link, result, count=1, flags=re.IGNORECASE)
    
    return result


def get_recent_notes(
    config: dict[str, Any],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get list of recent notes.
    
    Args:
        config: Navi configuration
        limit: Maximum number of notes to return
        
    Returns:
        List of note info dictionaries
    """
    output_config = config.get("output", {})
    vault_path = Path(output_config.get("vault_path", ""))
    subfolder = output_config.get("subfolder", "")
    
    if subfolder:
        target_dir = vault_path / subfolder
    else:
        target_dir = vault_path
    
    if not target_dir.exists():
        return []
    
    # Find markdown files
    notes = []
    for filepath in target_dir.glob("*.md"):
        try:
            stat = filepath.stat()
            content = filepath.read_text(encoding="utf-8")
            
            # Check if it's a Navi note (has source: navi in frontmatter)
            if "source: navi" not in content[:500]:
                continue
            
            notes.append({
                "path": filepath,
                "name": filepath.stem,
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "size": stat.st_size,
            })
        except Exception:
            continue
    
    # Sort by modification time (newest first)
    notes.sort(key=lambda x: x["modified"], reverse=True)
    
    return notes[:limit]
