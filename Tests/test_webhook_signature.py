import pytest
from fastapi import HTTPException

from Src.webhook.signature import verify_signature


def test_signature_accepts_matching_secret(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")

    verify_signature("test-secret")


def test_signature_rejects_invalid_secret(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")

    with pytest.raises(HTTPException) as exc_info:
        verify_signature("invalid")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


def test_signature_reports_missing_configuration(monkeypatch) -> None:
    monkeypatch.delenv("GITLAB_WEBHOOK_SECRET", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        verify_signature("anything")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Webhook secret is not configured"
