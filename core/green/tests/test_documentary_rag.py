"""Tests for Documentary RAG — Phase 9 of GREEN Foundation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.green.documentary_rag import (
    Chunk,
    Document,
    DocumentStore,
    RetrievalResult,
    Retriever,
    _is_excluded,
    chunk_text,
)


class TestExclusion(unittest.TestCase):
    def test_env_excluded(self):
        assert _is_excluded(Path(".env"))
        assert _is_excluded(Path(".env.local"))

    def test_credentials_excluded(self):
        assert _is_excluded(Path("credentials.json"))

    def test_git_excluded(self):
        assert _is_excluded(Path(".git/config"))

    def test_pycache_excluded(self):
        assert _is_excluded(Path("__pycache__/mod.pyc"))

    def test_binary_excluded(self):
        assert _is_excluded(Path("image.png"))
        assert _is_excluded(Path("app.exe"))

    def test_normal_not_excluded(self):
        assert not _is_excluded(Path("docs/ARCHITECTURE.md"))
        assert not _is_excluded(Path("main.py"))


class TestChunking(unittest.TestCase):
    def test_basic_chunking(self):
        text = "\n".join(f"Line {i}" for i in range(100))
        chunks = chunk_text(text, "doc1", chunk_size=200)
        assert len(chunks) > 1
        assert all(c.doc_id == "doc1" for c in chunks)

    def test_stable_ids(self):
        text = "Hello world\nSecond line"
        chunks1 = chunk_text(text, "doc1")
        chunks2 = chunk_text(text, "doc1")
        assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]

    def test_empty_text(self):
        chunks = chunk_text("", "empty")
        assert chunks == []

    def test_whitespace_only(self):
        chunks = chunk_text("   \n\n  ", "ws")
        assert chunks == []

    def test_single_chunk(self):
        text = "Short text"
        chunks = chunk_text(text, "short", chunk_size=1000)
        assert len(chunks) == 1


class TestDocumentStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _write_file(self, name: str, content: str) -> Path:
        p = Path(self.tmpdir) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_ingest_file(self):
        path = self._write_file("test.md", "# Hello\nWorld")
        store = DocumentStore()
        doc = store.ingest(path)
        assert doc is not None
        assert store.document_count == 1
        assert store.chunk_count > 0

    def test_ingest_excluded(self):
        path = self._write_file(".env", "SECRET=abc")
        store = DocumentStore()
        doc = store.ingest(path)
        assert doc is None
        assert store.document_count == 0

    def test_ingest_unsupported(self):
        path = self._write_file("image.png", "not really an image")
        store = DocumentStore()
        doc = store.ingest(path)
        assert doc is None

    def test_ingest_directory(self):
        self._write_file("docs/a.md", "Doc A content")
        self._write_file("docs/b.txt", "Doc B content")
        self._write_file("docs/.env", "SECRET=x")
        store = DocumentStore()
        docs = store.ingest_directory(Path(self.tmpdir))
        assert len(docs) == 2

    def test_duplicate_ingestion(self):
        path = self._write_file("test.md", "content v1")
        store = DocumentStore()
        store.ingest(path)
        path.write_text("content v2", encoding="utf-8")
        store.ingest(path)
        assert store.document_count == 1
        doc = store.all_documents()[0]
        assert "v2" in doc.content

    def test_get_document(self):
        path = self._write_file("test.md", "content")
        store = DocumentStore()
        doc = store.ingest(path)
        assert store.get_document(doc.doc_id) is doc

    def test_remove(self):
        path = self._write_file("test.md", "content")
        store = DocumentStore()
        doc = store.ingest(path)
        assert store.remove(doc.doc_id)
        assert store.document_count == 0
        assert store.chunk_count == 0

    def test_inaccessible_document(self):
        store = DocumentStore()
        doc = store.ingest(Path("/nonexistent/path/file.md"))
        assert doc is None

    def test_empty_directory(self):
        store = DocumentStore()
        docs = store.ingest_directory(Path(self.tmpdir))
        assert docs == []


class TestRetriever(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = DocumentStore()
        p1 = Path(self.tmpdir) / "architecture.md"
        p1.write_text("# JARVIS Architecture\nGemini Live session management and tool execution.\nRouter dispatches to handlers.", encoding="utf-8")
        p2 = Path(self.tmpdir) / "testing.md"
        p2.write_text("# Testing Guide\nRun pytest for automated tests.\nPhysical validation requires hardware.", encoding="utf-8")
        self.store.ingest(p1)
        self.store.ingest(p2)
        self.retriever = Retriever(self.store)

    def test_basic_retrieval(self):
        result = self.retriever.retrieve("architecture")
        assert len(result.chunks) > 0
        assert result.query == "architecture"

    def test_source_attribution(self):
        result = self.retriever.retrieve("Gemini")
        assert len(result.source_paths) > 0
        assert any("architecture" in p for p in result.source_paths)

    def test_empty_query(self):
        result = self.retriever.retrieve("")
        assert result.chunks == []

    def test_no_match(self):
        result = self.retriever.retrieve("xyznonexistent")
        assert result.chunks == []

    def test_scores_sorted(self):
        result = self.retriever.retrieve("architecture router tool")
        if len(result.scores) > 1:
            assert result.scores == sorted(result.scores, reverse=True)

    def test_top_k(self):
        result = self.retriever.retrieve("testing", top_k=1)
        assert len(result.chunks) <= 1

    def test_empty_corpus(self):
        empty_store = DocumentStore()
        retriever = Retriever(empty_store)
        result = retriever.retrieve("anything")
        assert result.chunks == []

    def test_malformed_text(self):
        p = Path(self.tmpdir) / "bad.md"
        p.write_text("" * 0 + "\x00\x01\x02 some text", encoding="utf-8")
        self.store.ingest(p)
        result = self.retriever.retrieve("some text")
        assert isinstance(result, RetrievalResult)


if __name__ == "__main__":
    unittest.main()
