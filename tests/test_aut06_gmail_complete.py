import base64
import json
from email import message_from_bytes
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from actions import email_control


def _client_file(path: Path) -> Path:
    path.write_text(json.dumps({"installed": {
        "client_id": "test", "auth_uri": "https://example.test/auth",
        "token_uri": "https://example.test/token",
    }}), encoding="utf-8")
    return path


def test_oauth_discovery_refuses_ambiguous_download_candidates(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    _client_file(downloads / "client_secret_one.json")
    _client_file(downloads / "client_secret_two.json")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("GMAIL_OAUTH_CLIENT_FILE", raising=False)
    with patch.object(email_control, "_secret_store") as store:
        store.return_value.get.return_value = ""
        with pytest.raises(email_control.GmailConnectionError, match="Multiple"):
            email_control._discover_gmail_client_path()


def test_explicit_oauth_path_wins_even_with_other_candidates(tmp_path):
    chosen = _client_file(tmp_path / "chosen.json")
    assert email_control._discover_gmail_client_path(str(chosen)) == chosen.resolve()


def test_attachment_metadata_and_thread_normalization():
    payload = {
        "headers": [{"name": "Subject", "value": "Informe"}],
        "parts": [
            {"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(b"Hola").decode()}},
            {"filename": "datos.csv", "mimeType": "text/csv", "body": {"attachmentId": "att-1", "size": 12}},
        ],
    }
    item = email_control._normalise_gmail_message({"id": "m1", "threadId": "t1", "payload": payload})
    assert item["subject"] == "Informe"
    assert item["body"] == "Hola"
    assert item["attachments"] == [{
        "filename": "datos.csv", "mime_type": "text/csv", "size": 12, "attachment_id": "att-1",
    }]


def test_thread_retrieval_uses_threads_api():
    service = MagicMock()
    service.users.return_value.threads.return_value.get.return_value.execute.return_value = {
        "messages": [{"id": "m1", "threadId": "t1", "snippet": "texto", "payload": {"headers": []}}]
    }
    with patch.object(email_control, "_gmail_service", return_value=service):
        result = email_control._gmail_thread("t1")
    assert "Gmail thread t1 (1 messages)" in result
    service.users.return_value.threads.return_value.get.assert_called_once_with(userId="me", id="t1", format="full")


def test_attachment_download_is_contained_and_decoded(tmp_path):
    service = MagicMock()
    encoded = base64.urlsafe_b64encode(b"payload").decode().rstrip("=")
    service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.return_value = {"data": encoded}
    with patch.object(email_control, "_gmail_service", return_value=service):
        result = email_control._gmail_download_attachment("m1", "a1", "../safe.txt", str(tmp_path))
    assert (tmp_path / "safe.txt").read_bytes() == b"payload"
    assert "downloaded" in result.lower()
    second = email_control._gmail_download_attachment("m1", "a1", "safe.txt", str(tmp_path))
    assert "already exists" in second


def test_raw_message_contains_attachment(tmp_path):
    attachment = tmp_path / "résumé.txt"
    attachment.write_text("contenido", encoding="utf-8")
    raw = email_control._gmail_raw_message({
        "to": "a@example.com", "cc": "", "bcc": "", "subject": "Prueba",
        "body": "Hola", "attachments": [str(attachment)],
    })
    message = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert message.is_multipart()
    assert message.get_payload()[1].get_filename() == "résumé.txt"


def test_create_draft_never_calls_send():
    service = MagicMock()
    service.users.return_value.drafts.return_value.create.return_value.execute.return_value = {"id": "d1"}
    with patch.object(email_control, "_gmail_service", return_value=service):
        result = email_control._gmail_create_draft({
            "to": "a@example.com", "cc": "", "bcc": "", "subject": "S", "body": "B", "attachments": [],
        })
    assert "Nothing was sent" in result
    service.users.return_value.messages.return_value.send.assert_not_called()


def test_draft_list_read_delete_are_api_backed():
    service = MagicMock()
    drafts = service.users.return_value.drafts.return_value
    drafts.list.return_value.execute.return_value = {"drafts": [{"id": "d1"}]}
    drafts.get.return_value.execute.side_effect = [
        {"id": "d1", "message": {"payload": {"headers": [{"name": "Subject", "value": "S"}]}}},
        {"id": "d1", "message": {"snippet": "B", "payload": {"headers": [{"name": "To", "value": "a@example.com"}]}}},
    ]
    drafts.delete.return_value.execute.return_value = {}
    with patch.object(email_control, "_gmail_service", return_value=service):
        assert "d1" in email_control._gmail_list_drafts(10)
        assert "a@example.com" in email_control._gmail_read_draft("d1")
        assert "deleted" in email_control._gmail_delete_draft("d1")


def test_prepare_with_attachment_stays_approval_gated(tmp_path):
    attachment = tmp_path / "a.txt"
    attachment.write_text("x", encoding="utf-8")
    email_control._clear_pending_email()
    result = email_control.email_control({
        "action": "prepare", "provider": "gmail", "to": "a@example.com",
        "subject": "S", "body": "B", "attachments": [str(attachment)],
    })
    assert result.startswith("EMAIL_APPROVAL_REQUIRED")
    assert email_control._get_pending_email()["delivery"] == "gmail_api"


def test_dispatch_requires_all_download_fields():
    assert "required" in email_control.email_control({"action": "download_attachment"})
