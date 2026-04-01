"""
Output handling for Navi.

Saves processed transcripts to the configured destination (Obsidian vault).
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any


def save_note(
    title: str,
    content: str,
    config: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> Path:
    """
    Save a note to the configured destination.
    
    Args:
        title: Note title (used in filename)
        content: Note content (markdown)
        config: Navi configuration dictionary
        metadata: Optional metadata to include in frontmatter
        
    Returns:
        Path to saved file
    """
    output_config = config.get("output", {})
    destination = output_config.get("destination", "obsidian")
    
    if destination == "obsidian":
        return _save_to_obsidian(title, content, output_config, metadata)
    else:
        # Default to generic markdown folder
        return _save_to_folder(title, content, output_config, metadata)


def _save_to_obsidian(
    title: str,
    content: str,
    output_config: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Save note to Obsidian vault."""
    vault_path = Path(output_config.get("vault_path", ""))
    subfolder = output_config.get("subfolder", "")
    
    if not vault_path.exists():
        raise ValueError(f"Obsidian vault not found: {vault_path}")
    
    # Build target directory
    if subfolder:
        target_dir = vault_path / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = vault_path
    
    # Generate filename
    filename = _generate_filename(title, output_config)
    filepath = target_dir / filename
    
    # Ensure unique filename
    filepath = _ensure_unique_path(filepath)
    
    # Build note content with frontmatter
    note_content = _build_note_content(title, content, metadata)
    
    # Write file
    filepath.write_text(note_content, encoding="utf-8")
    
    return filepath


def _save_to_folder(
    title: str,
    content: str,
    output_config: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Save note to a generic folder."""
    folder_path = Path(output_config.get("vault_path", ""))
    
    if not folder_path.exists():
        folder_path.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    filename = _generate_filename(title, output_config)
    filepath = folder_path / filename
    
    # Ensure unique filename
    filepath = _ensure_unique_path(filepath)
    
    # Build note content
    note_content = _build_note_content(title, content, metadata)
    
    # Write file
    filepath.write_text(note_content, encoding="utf-8")
    
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
    # Remove or replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    
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
    
    counter = 1
    while True:
        new_path = parent / f"{stem} ({counter}){suffix}"
        if not new_path.exists():
            return new_path
        counter += 1
        
        if counter > 1000:  # Safety limit
            raise ValueError("Too many files with same name")


def _build_note_content(
    title: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Build complete note content with frontmatter.
    
    Args:
        title: Note title
        content: Note content
        metadata: Optional metadata for frontmatter
        
    Returns:
        Complete note content with YAML frontmatter
    """
    # Build frontmatter
    frontmatter_items = [
        f"title: \"{title}\"",
        f"created: {datetime.now().isoformat()}",
        "source: navi",
        "type: note",
    ]
    
    if metadata:
        if "duration" in metadata:
            frontmatter_items.append(f"duration: {metadata['duration']:.1f}s")
        if "language" in metadata:
            frontmatter_items.append(f"language: {metadata['language']}")
        if "model" in metadata:
            frontmatter_items.append(f"whisper_model: {metadata['model']}")
    
    frontmatter = "\n".join(frontmatter_items)
    
    # Combine frontmatter and content
    note = f"""---
{frontmatter}
---

# {title}

{content}
"""
    
    return note


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
