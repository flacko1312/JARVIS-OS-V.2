"""Documentary RAG — local document retrieval for technical information.

Entirely separate from personal memory (LILITH). Only retrieves technical
documents: JARVIS docs, LILITH docs, manuals, READMEs, architecture notes,
technical reports, and source documentation.

RAG retrieval NEVER silently becomes personal memory.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.green.rag")

RAG_ENABLED = os.environ.get("JARVIS_RAG_ENABLED", "0") == "1"

# Paths that must NEVER be indexed
_EXCLUDED_PATTERNS = {
    ".env", ".env.", "credentials", "private_key", "id_rsa", "id_ed25519",
    "ssh_key", "cookie", "secret", ".git", "__pycache__", "node_modules",
    ".venv", "venv", "build", "dist", ".egg-info",
}

_EXCLUDED_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".dat",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".bz2", ".7z",
    ".db", ".sqlite", ".sqlite3",
})

_SUPPORTED_EXTENSIONS = frozenset({
    ".md", ".txt", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
    ".html", ".css", ".sh", ".bat", ".ps1",
})


def _is_excluded(path: Path) -> bool:
    """Check if a path should be excluded from indexing."""
    name_lower = path.name.lower()
    for pattern in _EXCLUDED_PATTERNS:
        if pattern in name_lower:
            return True
    for part in path.parts:
        part_lower = part.lower()
        for pattern in _EXCLUDED_PATTERNS:
            if pattern == part_lower:
                return True
    if path.suffix.lower() in _EXCLUDED_EXTENSIONS:
        return True
    return False


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in _SUPPORTED_EXTENSIONS


# ── Data models ─────────────────────────────────────────────────────

@dataclass
class Document:
    """A single indexed document."""

    doc_id: str
    source_path: str
    title: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """A chunk of a document for retrieval."""

    chunk_id: str
    doc_id: str
    content: str
    start_offset: int = 0
    end_offset: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Result of a retrieval query with provenance."""

    chunks: list[Chunk]
    query: str
    source_paths: list[str] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)


# ── Chunking ────────────────────────────────────────────────────────

def chunk_text(text: str, doc_id: str, chunk_size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Split text into overlapping chunks."""
    if not text.strip():
        return []

    chunks = []
    lines = text.split("\n")
    current_chunk = []
    current_size = 0
    start_offset = 0
    chunk_index = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current_size + line_len > chunk_size and current_chunk:
            chunk_text_str = "\n".join(current_chunk)
            chunk_id = f"{doc_id}_c{chunk_index}"
            chunks.append(Chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                content=chunk_text_str,
                start_offset=start_offset,
                end_offset=start_offset + len(chunk_text_str),
            ))
            chunk_index += 1

            # Overlap: keep last few lines
            overlap_lines = []
            overlap_size = 0
            for prev_line in reversed(current_chunk):
                if overlap_size + len(prev_line) > overlap:
                    break
                overlap_lines.insert(0, prev_line)
                overlap_size += len(prev_line) + 1

            start_offset = start_offset + len(chunk_text_str) - overlap_size
            current_chunk = overlap_lines
            current_size = overlap_size

        current_chunk.append(line)
        current_size += line_len

    if current_chunk:
        chunk_text_str = "\n".join(current_chunk)
        chunks.append(Chunk(
            chunk_id=f"{doc_id}_c{chunk_index}",
            doc_id=doc_id,
            content=chunk_text_str,
            start_offset=start_offset,
            end_offset=start_offset + len(chunk_text_str),
        ))

    return chunks


# ── Document Store ──────────────────────────────────────────────────

class DocumentStore:
    """In-memory document store with lexical search.

    v1 uses deterministic TF-based scoring. The interface supports
    future upgrades to embeddings, BM25, or hybrid retrieval without
    rewriting callers.
    """

    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}
        self._chunks: dict[str, list[Chunk]] = {}

    def ingest(self, path: Path, *, chunk_size: int = 500) -> Document | None:
        """Ingest a single file. Returns None if excluded or unsupported."""
        if _is_excluded(path):
            logger.debug("excluded from indexing: %s", path)
            return None

        if not _is_supported(path):
            logger.debug("unsupported format: %s", path)
            return None

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("cannot read %s: %s", path, exc)
            return None

        doc_id = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]

        doc = Document(
            doc_id=doc_id,
            source_path=str(path),
            title=path.stem,
            content=content,
        )
        self._documents[doc_id] = doc
        self._chunks[doc_id] = chunk_text(content, doc_id, chunk_size=chunk_size)
        logger.debug("ingested: %s (%d chunks)", path, len(self._chunks[doc_id]))
        return doc

    def ingest_directory(self, root: Path, *, chunk_size: int = 500) -> list[Document]:
        """Ingest all supported files under root."""
        docs = []
        if not root.is_dir():
            return docs
        for path in sorted(root.rglob("*")):
            if path.is_file():
                doc = self.ingest(path, chunk_size=chunk_size)
                if doc:
                    docs.append(doc)
        return docs

    def get_document(self, doc_id: str) -> Document | None:
        return self._documents.get(doc_id)

    def get_chunks(self, doc_id: str) -> list[Chunk]:
        return self._chunks.get(doc_id, [])

    def remove(self, doc_id: str) -> bool:
        removed = self._documents.pop(doc_id, None) is not None
        self._chunks.pop(doc_id, None)
        return removed

    @property
    def document_count(self) -> int:
        return len(self._documents)

    @property
    def chunk_count(self) -> int:
        return sum(len(chunks) for chunks in self._chunks.values())

    def all_documents(self) -> list[Document]:
        return list(self._documents.values())


# ── Retriever ───────────────────────────────────────────────────────

class Retriever:
    """Lexical retriever over a DocumentStore.

    Uses simple term-frequency scoring. The interface allows future
    replacement with BM25, embeddings, or hybrid without changing callers.
    """

    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        """Retrieve the most relevant chunks for a query."""
        if not query.strip():
            return RetrievalResult(chunks=[], query=query)

        query_terms = set(re.findall(r"\w+", query.lower()))
        if not query_terms:
            return RetrievalResult(chunks=[], query=query)

        scored: list[tuple[float, Chunk, str]] = []

        for doc_id, chunks in self._store._chunks.items():
            doc = self._store._documents.get(doc_id)
            source_path = doc.source_path if doc else ""

            for chunk in chunks:
                chunk_lower = chunk.content.lower()
                chunk_terms = set(re.findall(r"\w+", chunk_lower))
                if not chunk_terms:
                    continue

                matched = query_terms & chunk_terms
                if not matched:
                    continue

                # Simple TF score: fraction of query terms found
                score = len(matched) / len(query_terms)

                # Boost for title/heading proximity
                if any(term in (doc.title.lower() if doc else "") for term in matched):
                    score += 0.1

                scored.append((score, chunk, source_path))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        return RetrievalResult(
            chunks=[item[1] for item in top],
            query=query,
            source_paths=[item[2] for item in top],
            scores=[item[0] for item in top],
        )
