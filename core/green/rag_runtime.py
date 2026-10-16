"""Documentary RAG Runtime — read-only retrieval integration into JARVIS.

Exposes the Documentary RAG system as a low-risk retrieval surface.
Separate from personal memory (LILITH). Only retrieves technical
documentation with source attribution.

Feature flag: JARVIS_RAG_RUNTIME_ENABLED (default off).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from core.green.documentary_rag import (
    DocumentStore,
    Retriever,
    RetrievalResult,
    Document,
)

logger = logging.getLogger("jarvis.green.rag_runtime")

RAG_RUNTIME_ENABLED = os.environ.get("JARVIS_RAG_RUNTIME_ENABLED", "0") == "1"

_store: DocumentStore | None = None
_retriever: Retriever | None = None

_DEFAULT_DOC_DIRS = [
    "docs",
    "docs/architecture",
    "docs/audits",
]


def _ensure_initialized() -> tuple[DocumentStore, Retriever]:
    """Lazy-init store and index default documentation directories."""
    global _store, _retriever
    if _store is None:
        _store = DocumentStore()
        _retriever = Retriever(_store)
        project_root = Path(__file__).resolve().parent.parent.parent
        for rel_dir in _DEFAULT_DOC_DIRS:
            doc_dir = project_root / rel_dir
            if doc_dir.is_dir():
                _store.ingest_directory(doc_dir)
        logger.debug(
            "RAG runtime initialized: %d docs, %d chunks",
            _store.document_count,
            _store.chunk_count,
        )
    return _store, _retriever


def search_docs(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Search technical documentation. Returns attributed results."""
    if not RAG_RUNTIME_ENABLED:
        return []
    try:
        store, retriever = _ensure_initialized()
        result = retriever.retrieve(query, top_k=top_k)
        return [
            {
                "content": chunk.content[:500],
                "source": source,
                "score": round(score, 3),
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
            }
            for chunk, source, score in zip(
                result.chunks, result.source_paths, result.scores
            )
        ]
    except Exception:
        logger.debug("search_docs failed — isolated", exc_info=True)
        return []


def list_indexed_docs() -> list[dict[str, str]]:
    """List all indexed documents (read-only)."""
    if not RAG_RUNTIME_ENABLED:
        return []
    try:
        store, _ = _ensure_initialized()
        return [
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "source_path": doc.source_path,
            }
            for doc in store.all_documents()
        ]
    except Exception:
        logger.debug("list_indexed_docs failed — isolated", exc_info=True)
        return []


def get_doc_content(doc_id: str) -> str | None:
    """Read the full content of an indexed document."""
    if not RAG_RUNTIME_ENABLED:
        return None
    try:
        store, _ = _ensure_initialized()
        doc = store.get_document(doc_id)
        return doc.content if doc else None
    except Exception:
        logger.debug("get_doc_content failed — isolated", exc_info=True)
        return None


def index_directory(path: str) -> int:
    """Index an additional documentation directory. Returns count of docs indexed."""
    if not RAG_RUNTIME_ENABLED:
        return 0
    try:
        store, _ = _ensure_initialized()
        docs = store.ingest_directory(Path(path))
        return len(docs)
    except Exception:
        logger.debug("index_directory failed — isolated", exc_info=True)
        return 0


def rag_status() -> dict[str, Any]:
    """Return RAG system status summary."""
    if not RAG_RUNTIME_ENABLED:
        return {"enabled": False}
    try:
        store, _ = _ensure_initialized()
        return {
            "enabled": True,
            "document_count": store.document_count,
            "chunk_count": store.chunk_count,
            "indexed_dirs": _DEFAULT_DOC_DIRS,
        }
    except Exception:
        logger.debug("rag_status failed — isolated", exc_info=True)
        return {"enabled": True, "error": "initialization failed"}


def reset_store() -> None:
    """Reset store and retriever (for testing)."""
    global _store, _retriever
    _store = None
    _retriever = None
