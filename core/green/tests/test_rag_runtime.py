"""Tests for RAG Runtime — Phase 8 of GREEN runtime integration."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.green.rag_runtime import (
    search_docs,
    list_indexed_docs,
    get_doc_content,
    index_directory,
    rag_status,
    reset_store,
)

_FLAG = "core.green.rag_runtime.RAG_RUNTIME_ENABLED"


class TestDisabledIsNoop(unittest.TestCase):
    @patch(_FLAG, False)
    def test_search_disabled(self):
        assert search_docs("test") == []

    @patch(_FLAG, False)
    def test_list_disabled(self):
        assert list_indexed_docs() == []

    @patch(_FLAG, False)
    def test_get_content_disabled(self):
        assert get_doc_content("abc") is None

    @patch(_FLAG, False)
    def test_index_disabled(self):
        assert index_directory("/tmp") == 0

    @patch(_FLAG, False)
    def test_status_disabled(self):
        result = rag_status()
        assert result == {"enabled": False}


class TestRAGWithTempDocs(unittest.TestCase):
    def setUp(self):
        reset_store()
        self.tmpdir = tempfile.mkdtemp()
        (Path(self.tmpdir) / "readme.md").write_text(
            "# Test Project\nThis is a test project about GREEN architecture.\n"
            "It has execution traces and event bus.\n",
            encoding="utf-8",
        )
        (Path(self.tmpdir) / "guide.txt").write_text(
            "Installation guide\nStep 1: install Python\nStep 2: run pip install\n",
            encoding="utf-8",
        )
        (Path(self.tmpdir) / "secrets.env").write_text(
            "API_KEY=secret123\n",
            encoding="utf-8",
        )

    @patch(_FLAG, True)
    def test_index_directory(self):
        count = index_directory(self.tmpdir)
        assert count == 2  # .md and .txt, .env excluded

    @patch(_FLAG, True)
    def test_search_finds_content(self):
        index_directory(self.tmpdir)
        results = search_docs("GREEN architecture")
        assert len(results) > 0
        assert any("GREEN" in r["content"] for r in results)

    @patch(_FLAG, True)
    def test_search_returns_attribution(self):
        index_directory(self.tmpdir)
        results = search_docs("installation")
        assert len(results) > 0
        for r in results:
            assert "source" in r
            assert "score" in r
            assert "chunk_id" in r

    @patch(_FLAG, True)
    def test_search_empty_query(self):
        index_directory(self.tmpdir)
        assert search_docs("") == []

    @patch(_FLAG, True)
    def test_list_indexed(self):
        index_directory(self.tmpdir)
        docs = list_indexed_docs()
        assert len(docs) >= 2
        titles = [d["title"] for d in docs]
        assert "readme" in titles
        assert "guide" in titles

    @patch(_FLAG, True)
    def test_get_content(self):
        index_directory(self.tmpdir)
        docs = list_indexed_docs()
        assert len(docs) > 0
        content = get_doc_content(docs[0]["doc_id"])
        assert content is not None
        assert len(content) > 0

    @patch(_FLAG, True)
    def test_get_content_nonexistent(self):
        index_directory(self.tmpdir)
        assert get_doc_content("nonexistent_id") is None

    @patch(_FLAG, True)
    def test_secrets_excluded(self):
        index_directory(self.tmpdir)
        docs = list_indexed_docs()
        paths = [d["source_path"] for d in docs]
        assert not any("secrets.env" in p for p in paths)


class TestRAGStatus(unittest.TestCase):
    def setUp(self):
        reset_store()

    @patch(_FLAG, True)
    def test_status_enabled(self):
        result = rag_status()
        assert result["enabled"] is True
        assert "document_count" in result
        assert "chunk_count" in result
        assert "indexed_dirs" in result


class TestNoMemoryLeak(unittest.TestCase):
    @patch(_FLAG, True)
    def test_search_does_not_store_query(self):
        reset_store()
        search_docs("sensitive personal information")
        # RAG should not persist the query as personal memory
        docs = list_indexed_docs()
        for d in docs:
            content = get_doc_content(d["doc_id"])
            if content:
                assert "sensitive personal information" not in content


if __name__ == "__main__":
    unittest.main()
