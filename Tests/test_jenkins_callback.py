from fastapi.testclient import TestClient

from Src.main import app
from Src.jenkins.runs import mark_ci_run_running, reserve_ci_run


def _headers(token: str = "callback-secret") -> dict[str, str]:
    return {"X-Internal-Token": token}


def _payload(**overrides) -> dict:
    payload = {
        "pipeline": "BUILD",
        "project_id": "42",
        "mr_id": "7",
        "source_branch": "feature/example",
        "target_branch": "main",
        "commit_sha": "abc123",
        "repository_url": "https://gitlab.example/repo.git",
        "build_result": "SUCCESS",
        "lint_result": "SUCCESS",
    }
    payload.update(overrides)
    return payload


def test_successful_build_enqueues_review(isolated_database, monkeypatch) -> None:
    monkeypatch.setenv("JENKINS_CALLBACK_TOKEN", "callback-secret")

    response = TestClient(app).post(
        "/internal/jenkins/result",
        headers=_headers(),
        json=_payload(),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "queued", "event_type": "REVIEW"}
    row = isolated_database.query_one(
        "SELECT event_type, status, payload FROM job_queue"
    )
    assert row["event_type"] == "REVIEW"
    assert row["status"] == "WAITING"
    assert '"repository_url": "https://gitlab.example/repo.git"' in row["payload"]


def test_failed_build_enqueues_build_fix(isolated_database, monkeypatch) -> None:
    monkeypatch.setenv("JENKINS_CALLBACK_TOKEN", "callback-secret")
    messages = []

    async def capture(project_id: str, mr_id: str, message: str) -> None:
        messages.append((project_id, mr_id, message))

    monkeypatch.setattr("Src.jenkins.callback.post_comment", capture)

    response = TestClient(app).post(
        "/internal/jenkins/result",
        headers=_headers(),
        json=_payload(build_result="FAILED", lint_result="NOT_RUN"),
    )

    assert response.status_code == 202
    assert isolated_database.query_scalar(
        "SELECT event_type FROM job_queue"
    ) == "BUILD_FIX"
    assert messages[0][:2] == ("42", "7")
    assert "## ❌ ビルドに失敗しました" in messages[0][2]


def test_lint_failure_posts_comment_without_queue(
    isolated_database, monkeypatch
) -> None:
    monkeypatch.setenv("JENKINS_CALLBACK_TOKEN", "callback-secret")
    messages = []

    async def capture(project_id: str, mr_id: str, message: str) -> None:
        messages.append((project_id, mr_id, message))

    monkeypatch.setattr("Src.jenkins.callback.post_comment", capture)
    response = TestClient(app).post(
        "/internal/jenkins/result",
        headers=_headers(),
        json=_payload(lint_result="FAILED"),
    )

    assert response.status_code == 202
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0
    assert messages and messages[0][:2] == ("42", "7")


def test_callback_rejects_invalid_token(isolated_database, monkeypatch) -> None:
    monkeypatch.setenv("JENKINS_CALLBACK_TOKEN", "callback-secret")

    response = TestClient(app).post(
        "/internal/jenkins/result",
        headers=_headers("invalid"),
        json=_payload(),
    )

    assert response.status_code == 401
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_build_callback_starts_pending_commit(
    isolated_database, monkeypatch
) -> None:
    monkeypatch.setenv("JENKINS_CALLBACK_TOKEN", "callback-secret")
    calls = []

    async def trigger(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("Src.jenkins.orchestrator.trigger_build", trigger)
    common = {
        "project_id": "42",
        "mr_id": "7",
        "source_branch": "feature/example",
        "target_branch": "main",
        "repository_url": "https://gitlab.example/repo.git",
    }
    assert reserve_ci_run(commit_sha="sha-1", **common) == "TRIGGERING"
    mark_ci_run_running("42", "7", "sha-1")
    assert reserve_ci_run(commit_sha="sha-2", **common) == "PENDING"

    response = TestClient(app).post(
        "/internal/jenkins/result",
        headers=_headers(),
        json=_payload(commit_sha="sha-1"),
    )

    assert response.status_code == 202
    assert calls[0]["commit_sha"] == "sha-2"
    with isolated_database.engine.connect() as connection:
        statuses = dict(
            connection.exec_driver_sql(
                "SELECT commit_sha, status FROM ci_runs"
            ).all()
        )
    assert statuses == {"sha-1": "COMPLETED", "sha-2": "RUNNING"}


def test_successful_re_review_build_enqueues_re_review(
    isolated_database, monkeypatch
) -> None:
    monkeypatch.setenv("JENKINS_CALLBACK_TOKEN", "callback-secret")
    common = {
        "project_id": "42",
        "mr_id": "7",
        "commit_sha": "abc123",
        "source_branch": "feature/example",
        "target_branch": "main",
        "repository_url": "https://gitlab.example/repo.git",
        "review_event_type": "RE_REVIEW",
    }
    assert reserve_ci_run(**common) == "TRIGGERING"
    mark_ci_run_running("42", "7", "abc123", "RE_REVIEW")

    response = TestClient(app).post(
        "/internal/jenkins/result",
        headers=_headers(),
        json=_payload(),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "queued", "event_type": "RE_REVIEW"}
    assert isolated_database.query_scalar(
        "SELECT event_type FROM job_queue"
    ) == "RE_REVIEW"


def test_successful_post_resolution_build_enqueues_test_generation(
    isolated_database, monkeypatch
) -> None:
    monkeypatch.setenv("JENKINS_CALLBACK_TOKEN", "callback-secret")
    common = {
        "project_id": "42",
        "mr_id": "7",
        "commit_sha": "abc123",
        "source_branch": "feature/example",
        "target_branch": "main",
        "repository_url": "https://gitlab.example/repo.git",
        "review_event_type": "POST_RESOLUTION",
    }
    assert reserve_ci_run(**common) == "TRIGGERING"
    mark_ci_run_running("42", "7", "abc123", "POST_RESOLUTION")

    response = TestClient(app).post(
        "/internal/jenkins/result",
        headers=_headers(),
        json=_payload(),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "queued", "event_type": "UNIT_TEST_GEN"}
    assert isolated_database.query_scalar(
        "SELECT event_type FROM job_queue"
    ) == "UNIT_TEST_GEN"
