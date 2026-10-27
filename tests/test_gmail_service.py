"""
Unit tests for Gmail Service:
Authentication state handling, safety confirmation enforcement, and message parsing logic.
"""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock
import pytest

from gmail_service import EmailDraft, EmailSummary, GmailService


def test_gmail_unauthenticated_state():
    with tempfile.TemporaryDirectory() as tmpdir:
        token_path = Path(tmpdir) / "token.json"
        creds_path = Path(tmpdir) / "creds.json"
        svc = GmailService(token_path=token_path, credentials_path=creds_path)

        assert not svc.is_authenticated()
        assert svc.get_user_email() is None
        assert not svc.has_client_credentials()


def test_gmail_send_requires_explicit_confirmation():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = GmailService(
            token_path=Path(tmpdir) / "token.json",
            credentials_path=Path(tmpdir) / "creds.json",
        )

        # Must raise PermissionError when user_confirmed is False
        with pytest.raises(PermissionError) as exc:
            svc.send_email(
                to="recipient@example.com",
                subject="Test Subject",
                body="Test Body",
                user_confirmed=False,
            )
        assert "explicit user confirmation" in str(exc.value)


def test_gmail_message_summary_parsing():
    svc = GmailService(token_path=Path("dummy"), credentials_path=Path("dummy"))

    raw_msg = {
        "id": "msg_12345",
        "threadId": "thread_67890",
        "snippet": "Preview of the incoming message...",
        "payload": {
            "headers": [
                {"name": "From", "value": "Google Cloud <no-reply@cloud.google.com>"},
                {"name": "Subject", "value": "Monthly Cloud Invoice"},
                {"name": "Date", "value": "Tue, 27 Oct 2026 12:00:00 +0000"},
            ]
        },
    }

    summary = svc._parse_summary(raw_msg)
    assert summary.id == "msg_12345"
    assert summary.sender == "Google Cloud <no-reply@cloud.google.com>"
    assert summary.subject == "Monthly Cloud Invoice"
    assert summary.snippet == "Preview of the incoming message..."


def test_gmail_mocked_draft_and_send():
    svc = GmailService(token_path=Path("dummy"), credentials_path=Path("dummy"))

    mock_service = MagicMock()
    mock_drafts = MagicMock()
    mock_messages = MagicMock()

    mock_drafts.create.return_value.execute.return_value = {"id": "draft_999"}
    mock_messages.send.return_value.execute.return_value = {"id": "sent_888"}

    mock_service.users.return_value.drafts.return_value = mock_drafts
    mock_service.users.return_value.messages.return_value = mock_messages

    svc._service = mock_service
    svc._creds = MagicMock()
    svc._creds.valid = True

    # Create draft
    draft = svc.create_draft(to="boss@corp.com", subject="Project Update", body="All tests passing.")
    assert draft.id == "draft_999"
    assert draft.recipient == "boss@corp.com"

    # Send with explicit confirmation
    sent_id = svc.send_email(
        to="boss@corp.com",
        subject="Project Update",
        body="All tests passing.",
        user_confirmed=True,
    )
    assert sent_id == "sent_888"
