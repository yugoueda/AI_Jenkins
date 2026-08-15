from fastapi.testclient import TestClient

from Src.main import app


def _headers(token: str = "test-secret", event: str = "Merge Request Hook"):
    return {
        "X-Gitlab-Token": token,
        "X-Gitlab-Event": event,
    }


def _mr_payload(action: str) -> dict:
    return {
        "project": {"id": 42},
        "object_attributes": {
            "action": action,
            "iid": 7,
            "source_branch": "feature/example",
            "target_branch": "main",
        },
        "changes": {},
    }


def test_mr_open_event_triggers_jenkins(isolated_database, monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")
    calls = []
    comments = []

    async def trigger(**kwargs):
        calls.append(kwargs)

    async def comment(project_id, mr_id, message):
        comments.append((project_id, mr_id, message))

    monkeypatch.setattr("Src.webhook.handlers.mr_opened.trigger_build", trigger)
    monkeypatch.setattr("Src.webhook.handlers.mr_opened.post_comment", comment)

    response = TestClient(app).post(
        "/webhook", headers=_headers(), json=_mr_payload("open")
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == [
        {
            "project_id": "42",
            "mr_id": "7",
            "source_branch": "feature/example",
            "target_branch": "main",
            "commit_sha": "",
            "repository_url": "",
        }
    ]
    assert comments[0][:2] == ("42", "7")
    assert "## AIレビューの使い方" in comments[0][2]
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_legacy_mr_opened_event_is_accepted(isolated_database, monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")
    calls = []

    async def trigger(**kwargs):
        calls.append(kwargs)

    async def comment(*args):
        return None

    monkeypatch.setattr("Src.webhook.handlers.mr_opened.trigger_build", trigger)
    monkeypatch.setattr("Src.webhook.handlers.mr_opened.post_comment", comment)

    response = TestClient(app).post(
        "/webhook", headers=_headers(), json=_mr_payload("opened")
    )

    assert response.status_code == 200
    assert len(calls) == 1


def test_invalid_token_does_not_enqueue(isolated_database, monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")

    response = TestClient(app).post(
        "/webhook", headers=_headers(token="invalid"), json=_mr_payload("open")
    )

    assert response.status_code == 401
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_resolved_discussions_enqueue_re_review(
    isolated_database, monkeypatch
) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")

    async def all_resolved(project_id: str, mr_id: str) -> bool:
        assert (project_id, mr_id) == ("42", "7")
        return True

    monkeypatch.setattr(
        "Src.webhook.handlers.mr_updated.gitlab.all_discussions_resolved",
        all_resolved,
    )
    payload = _mr_payload("update")
    payload["changes"] = {
        "blocking_discussions_resolved": {"previous": False, "current": True}
    }

    response = TestClient(app).post("/webhook", headers=_headers(), json=payload)

    assert response.status_code == 200
    assert isolated_database.query_scalar(
        "SELECT COUNT(*) FROM job_queue WHERE event_type='RE_REVIEW'"
    ) == 1


def test_unhandled_event_returns_ok_without_enqueue(
    isolated_database, monkeypatch
) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")

    response = TestClient(app).post(
        "/webhook",
        headers=_headers(event="Push Hook"),
        json={"object_kind": "push"},
    )

    assert response.status_code == 200
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_note_event_dispatches_command(isolated_database, monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")
    payload = {
        "project": {"id": 42},
        "object_attributes": {
            "noteable_type": "MergeRequest",
            "note": "/ai test",
        },
        "merge_request": {"iid": 7, "source_branch": "feature/example"},
    }

    response = TestClient(app).post(
        "/webhook", headers=_headers(event="Note Hook"), json=payload
    )

    assert response.status_code == 200
    assert isolated_database.query_scalar(
        "SELECT COUNT(*) FROM job_queue WHERE event_type='UNIT_TEST_GEN'"
    ) == 1


def test_update_without_resolved_transition_does_not_enqueue(
    isolated_database, monkeypatch
) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")
    payload = _mr_payload("update")
    payload["changes"] = {
        "blocking_discussions_resolved": {"previous": True, "current": False}
    }

    response = TestClient(app).post("/webhook", headers=_headers(), json=payload)

    assert response.status_code == 200
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_required_delivery_headers_are_enforced(
    isolated_database, monkeypatch
) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-secret")

    response = TestClient(app).post("/webhook", json=_mr_payload("open"))

    assert response.status_code == 422
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
