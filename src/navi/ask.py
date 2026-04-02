"""
Ask Navi - RAG-based querying over voice notes.

Enables natural language queries across your voice notes vault:
- "What did I say about the Q3 launch?"
- "Summarize my thoughts on Project Atlas"
- "Find all notes mentioning John"

Architecture:
1. Indexing: Embed all voice notes using local embeddings (Ollama or sentence-transformers)
2. Storage: ChromaDB for vector storage (or simple numpy + sqlite fallback)
3. Query: Embed query → vector search → retrieve top-k notes → LLM synthesis

All processing is local and private.
"""

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np

from navi.config import DEFAULT_CONFIG_DIR


# Index storage location
INDEX_DIR = DEFAULT_CONFIG_DIR / "index"
INDEX_DB = INDEX_DIR / "embeddings.db"
INDEX_META = INDEX_DIR / "meta.json"


class AskNaviError(Exception):
    """Raised when Ask Navi operations fail."""
    pass


def _get_embedding_provider(config: dict[str, Any]) -> str:
    """Determine which embedding provider to use based on config."""
    ask_config = config.get("ask_navi", {})
    provider = ask_config.get("embedding_provider", "auto")
    
    if provider == "auto":
        # Try Ollama first (if LLM is configured for Ollama)
        llm_provider = config.get("llm", {}).get("provider", "")
        if llm_provider == "ollama":
            return "ollama"
        
        # Fall back to sentence-transformers
        return "sentence-transformers"
    
    return provider


def _embed_with_ollama(
    texts: list[str],
    model: str = "nomic-embed-text",
    host: str = "http://localhost:11434",
) -> np.ndarray:
    """Generate embeddings using Ollama."""
    import requests
    
    embeddings = []
    
    for text in texts:
        try:
            response = requests.post(
                f"{host}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30,
            )
            
            if response.status_code != 200:
                raise AskNaviError(f"Ollama embedding failed: {response.status_code}")
            
            data = response.json()
            embeddings.append(data["embedding"])
        
        except requests.exceptions.ConnectionError:
            raise AskNaviError(
                "Cannot connect to Ollama. Is it running? Start with: ollama serve"
            )
    
    return np.array(embeddings, dtype=np.float32)


def _embed_with_sentence_transformers(
    texts: list[str],
    model_name: str = "all-MiniLM-L6-v2",
) -> np.ndarray:
    """Generate embeddings using sentence-transformers."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise AskNaviError(
            "sentence-transformers not installed. Run: pip install sentence-transformers"
        )
    
    # Load model (cached after first load)
    model = SentenceTransformer(model_name)
    embeddings = model.encode(texts, show_progress_bar=False)
    
    return embeddings.astype(np.float32)


def _generate_embeddings(
    texts: list[str],
    config: dict[str, Any],
) -> np.ndarray:
    """Generate embeddings using configured provider."""
    provider = _get_embedding_provider(config)
    
    if provider == "ollama":
        ollama_config = config.get("llm", {}).get("ollama", {})
        host = ollama_config.get("host", "http://localhost:11434")
        model = config.get("ask_navi", {}).get("ollama_model", "nomic-embed-text")
        return _embed_with_ollama(texts, model=model, host=host)
    
    elif provider == "sentence-transformers":
        model = config.get("ask_navi", {}).get("st_model", "all-MiniLM-L6-v2")
        return _embed_with_sentence_transformers(texts, model_name=model)
    
    else:
        raise AskNaviError(f"Unknown embedding provider: {provider}")


def _parse_voice_note(filepath: Path) -> dict[str, Any]:
    """
    Parse a voice note markdown file.
    
    Extracts frontmatter, title, summary, and transcript.
    """
    content = filepath.read_text(encoding="utf-8")
    
    # Check if it's a Navi note
    if "source: navi" not in content[:500]:
        return None
    
    result = {
        "path": str(filepath),
        "filename": filepath.stem,
        "modified": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
    }
    
    # Extract frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            body = parts[2].strip()
            
            # Parse frontmatter
            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip().strip('"')
                    
                    if key == "title":
                        result["title"] = value
                    elif key == "created":
                        result["created"] = value
                    elif key == "tags":
                        # Parse [tag1, tag2] format
                        tags = re.findall(r'\w+', value)
                        result["tags"] = tags
                    elif key == "duration":
                        result["duration"] = value
        else:
            body = content
    else:
        body = content
    
    # Extract title from body if not in frontmatter
    if "title" not in result:
        title_match = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
        if title_match:
            result["title"] = title_match.group(1).strip()
        else:
            result["title"] = filepath.stem
    
    # Extract summary section
    summary_match = re.search(
        r'##\s+Summary\s*\n(.*?)(?=\n##|\n---|\Z)',
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if summary_match:
        result["summary"] = summary_match.group(1).strip()
    
    # Extract transcript section
    transcript_match = re.search(
        r'##\s+Transcript\s*\n(.*?)(?=\n##|\n---|\Z)',
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if transcript_match:
        result["transcript"] = transcript_match.group(1).strip()
    else:
        # Use full body if no transcript section
        result["transcript"] = body
    
    # Create searchable text (combine all text for embedding)
    text_parts = [result.get("title", "")]
    if result.get("summary"):
        text_parts.append(result["summary"])
    if result.get("transcript"):
        text_parts.append(result["transcript"])
    if result.get("tags"):
        text_parts.append(" ".join(result["tags"]))
    
    result["searchable_text"] = "\n\n".join(text_parts)
    
    return result


def _get_content_hash(content: str) -> str:
    """Generate a hash of content for change detection."""
    return hashlib.md5(content.encode()).hexdigest()[:16]


class NoteIndex:
    """
    Index of voice notes for semantic search.
    
    Uses SQLite for metadata + numpy arrays for embeddings.
    Simple but effective for personal note collections.
    """
    
    def __init__(self, config: dict[str, Any]):
        """Initialize the index."""
        self.config = config
        self._ensure_index_dir()
        self._init_db()
    
    def _ensure_index_dir(self) -> None:
        """Create index directory if needed."""
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
    
    def _init_db(self) -> None:
        """Initialize SQLite database."""
        self.conn = sqlite3.connect(str(INDEX_DB), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                title TEXT,
                created TEXT,
                modified TEXT,
                summary TEXT,
                transcript TEXT,
                tags TEXT,
                content_hash TEXT,
                embedding BLOB
            )
        """)
        self.conn.commit()
    
    def _serialize_embedding(self, embedding: np.ndarray) -> bytes:
        """Serialize embedding to bytes for storage."""
        return embedding.tobytes()
    
    def _deserialize_embedding(self, data: bytes, dim: int = 384) -> np.ndarray:
        """Deserialize embedding from bytes."""
        return np.frombuffer(data, dtype=np.float32)
    
    def index_vault(
        self,
        vault_path: str,
        subfolder: str = "",
        force: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> dict[str, int]:
        """
        Index all voice notes in the vault.
        
        Args:
            vault_path: Path to Obsidian vault
            subfolder: Optional subfolder to limit indexing
            force: Re-index all notes even if unchanged
            progress_callback: Optional callback(current, total, message)
            
        Returns:
            Dict with counts: indexed, skipped, removed
        """
        vault = Path(vault_path)
        if subfolder:
            scan_path = vault / subfolder
        else:
            scan_path = vault
        
        if not scan_path.exists():
            raise AskNaviError(f"Vault path not found: {scan_path}")
        
        # Find all markdown files
        md_files = list(scan_path.rglob("*.md"))
        
        stats = {"indexed": 0, "skipped": 0, "removed": 0, "errors": 0}
        notes_to_embed = []
        
        # Track which paths we've seen
        seen_paths = set()
        
        for i, filepath in enumerate(md_files):
            if progress_callback:
                progress_callback(i + 1, len(md_files), f"Scanning {filepath.name}")
            
            try:
                note = _parse_voice_note(filepath)
                if note is None:
                    continue  # Not a Navi note
                
                path = str(filepath)
                seen_paths.add(path)
                
                # Check if note has changed
                content_hash = _get_content_hash(note["searchable_text"])
                
                existing = self.conn.execute(
                    "SELECT content_hash FROM notes WHERE path = ?",
                    (path,)
                ).fetchone()
                
                if existing and existing["content_hash"] == content_hash and not force:
                    stats["skipped"] += 1
                    continue
                
                notes_to_embed.append(note)
            
            except Exception as e:
                print(f"Error parsing {filepath}: {e}")
                stats["errors"] += 1
        
        # Generate embeddings in batch
        if notes_to_embed:
            if progress_callback:
                progress_callback(0, len(notes_to_embed), "Generating embeddings...")
            
            texts = [n["searchable_text"] for n in notes_to_embed]
            
            # Batch in chunks of 50 for memory efficiency
            batch_size = 50
            all_embeddings = []
            
            for j in range(0, len(texts), batch_size):
                batch_texts = texts[j:j + batch_size]
                if progress_callback:
                    progress_callback(
                        j + len(batch_texts),
                        len(texts),
                        f"Embedding {j + 1}-{j + len(batch_texts)} of {len(texts)}"
                    )
                
                batch_embeddings = _generate_embeddings(batch_texts, self.config)
                all_embeddings.append(batch_embeddings)
            
            embeddings = np.vstack(all_embeddings)
            
            # Store in database
            for note, embedding in zip(notes_to_embed, embeddings):
                content_hash = _get_content_hash(note["searchable_text"])
                
                self.conn.execute("""
                    INSERT OR REPLACE INTO notes 
                    (path, title, created, modified, summary, transcript, tags, content_hash, embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    note["path"],
                    note.get("title", ""),
                    note.get("created", ""),
                    note.get("modified", ""),
                    note.get("summary", ""),
                    note.get("transcript", ""),
                    json.dumps(note.get("tags", [])),
                    content_hash,
                    self._serialize_embedding(embedding),
                ))
                stats["indexed"] += 1
            
            self.conn.commit()
        
        # Remove notes that no longer exist
        existing_paths = [
            row["path"] for row in 
            self.conn.execute("SELECT path FROM notes").fetchall()
        ]
        
        for path in existing_paths:
            if path not in seen_paths:
                self.conn.execute("DELETE FROM notes WHERE path = ?", (path,))
                stats["removed"] += 1
        
        self.conn.commit()
        
        # Save metadata
        meta = {
            "last_indexed": datetime.now().isoformat(),
            "vault_path": vault_path,
            "subfolder": subfolder,
            "note_count": self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0],
            "embedding_provider": _get_embedding_provider(self.config),
        }
        INDEX_META.write_text(json.dumps(meta, indent=2))
        
        return stats
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        Search notes using semantic similarity.
        
        Args:
            query: Natural language query
            top_k: Maximum number of results
            threshold: Minimum similarity score (0-1)
            
        Returns:
            List of matching notes with scores
        """
        # Generate query embedding
        query_embedding = _generate_embeddings([query], self.config)[0]
        
        # Get all note embeddings
        rows = self.conn.execute("""
            SELECT path, title, summary, transcript, tags, embedding
            FROM notes
        """).fetchall()
        
        if not rows:
            return []
        
        # Calculate similarities
        results = []
        
        for row in rows:
            note_embedding = self._deserialize_embedding(row["embedding"])
            
            # Cosine similarity
            similarity = np.dot(query_embedding, note_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(note_embedding)
            )
            
            if similarity >= threshold:
                results.append({
                    "path": row["path"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "transcript": row["transcript"],
                    "tags": json.loads(row["tags"]) if row["tags"] else [],
                    "score": float(similarity),
                })
        
        # Sort by similarity and return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    
    def get_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        if not INDEX_META.exists():
            return {"indexed": False}
        
        meta = json.loads(INDEX_META.read_text())
        note_count = self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        
        return {
            "indexed": True,
            "note_count": note_count,
            "last_indexed": meta.get("last_indexed"),
            "embedding_provider": meta.get("embedding_provider"),
            "vault_path": meta.get("vault_path"),
        }


def ask_navi(
    query: str,
    config: dict[str, Any],
    top_k: int = 5,
    synthesize: bool = True,
) -> dict[str, Any]:
    """
    Query your voice notes using natural language.
    
    Args:
        query: Natural language question
        config: Navi configuration
        top_k: Number of notes to retrieve
        synthesize: Whether to synthesize an answer using LLM
        
    Returns:
        Dict with answer, sources, and raw results
    """
    index = NoteIndex(config)
    stats = index.get_stats()
    
    if not stats.get("indexed"):
        raise AskNaviError(
            "Notes not indexed yet. Run: navi index"
        )
    
    # Search for relevant notes
    results = index.search(query, top_k=top_k)
    
    if not results:
        return {
            "answer": "I couldn't find any relevant notes for your query.",
            "sources": [],
            "results": [],
        }
    
    # Build context from top results
    context_parts = []
    sources = []
    
    for i, result in enumerate(results):
        sources.append({
            "title": result["title"],
            "path": result["path"],
            "score": result["score"],
        })
        
        # Use summary if available, otherwise transcript excerpt
        content = result.get("summary") or result.get("transcript", "")[:500]
        context_parts.append(f"Note {i+1}: {result['title']}\n{content}")
    
    context = "\n\n---\n\n".join(context_parts)
    
    if not synthesize:
        return {
            "answer": None,
            "sources": sources,
            "results": results,
            "context": context,
        }
    
    # Synthesize answer using LLM
    answer = _synthesize_answer(query, context, results, config)
    
    return {
        "answer": answer,
        "sources": sources,
        "results": results,
    }


def _synthesize_answer(
    query: str,
    context: str,
    results: list[dict],
    config: dict[str, Any],
) -> str:
    """Use LLM to synthesize an answer from retrieved notes."""
    from navi.process import _process_with_ollama, _process_with_openai, _process_with_anthropic
    
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "none")
    
    if provider == "none":
        # No LLM - just return a summary of sources
        titles = [r["title"] for r in results[:3]]
        return f"Found {len(results)} relevant notes: {', '.join(titles)}"
    
    # Custom prompt for Ask Navi
    prompt = f"""You are Navi, a personal voice notes assistant. Answer the user's question based ONLY on the voice notes provided below.

Rules:
1. Answer concisely and directly
2. Reference specific notes using [[Note Title]] wikilinks
3. If the notes don't contain enough information, say so
4. Don't make up information not in the notes

Voice Notes Context:
{context}

Question: {query}

Answer:"""
    
    try:
        import requests
        
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
            from navi.keychain import get_api_key
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
            from navi.keychain import get_api_key
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
        print(f"LLM synthesis error: {e}")
    
    # Fallback to simple summary
    titles = [r["title"] for r in results[:3]]
    return f"Found {len(results)} relevant notes: {', '.join(titles)}"
