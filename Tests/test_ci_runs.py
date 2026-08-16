import asyncio

from Src.jenkins import orchestrator
from Src.jenkins.runs import (
    claim_next_pending_ci_run,
    mark_ci_run_completed,
    mark_ci_run_running,
    reserve_ci_run,
)


def _reserve(commit_sha: str) -> str:
    return reserve_ci_run(
        project_id="42",
        mr_id="7",
        commit_sha=commit_sha,
        source_branch="feature/example",
        target_branch="main",
        repository_url="https://gitlab.example/repo.git",
    )


def test_ci_runs_deduplicate_and_queue_same_mr(isolated_database) -> None:
    assert _reserve("sha-1") == "TRIGGERING"
    mark_ci_run_running("42", "7", "sha-1")

    assert _reserve("sha-1") == "DUPLICATE"
    assert _reserve("sha-2") == "PENDING"
    assert claim_next_pending_ci_run("42", "7") is None

    mark_ci_run_completed("42", "7", "sha-1")
    pending = claim_next_pending_ci_run("42", "7")

    assert pending is not None
    assert pending["commit_sha"] == "sha-2"
    assert isolated_database.query_scalar(
        "SELECT status FROM ci_runs WHERE commit_sha='sha-2'"
    ) == "TRIGGERING"


def test_schedule_build_records_running_commit(
    isolated_database, monkeypatch
) -> None:
    calls = []

    async def trigger(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(orchestrator, "trigger_build", trigger)

    result = asyncio.run(
        orchestrator.schedule_build(
            project_id="42",
            mr_id="7",
            source_branch="feature/example",
            target_branch="main",
            commit_sha="sha-1",
            repository_url="https://gitlab.example/repo.git",
        )
    )

    assert result == "STARTED"
    assert calls[0]["commit_sha"] == "sha-1"
    assert isolated_database.query_scalar(
        "SELECT status FROM ci_runs WHERE commit_sha='sha-1'"
    ) == "RUNNING"


def test_same_commit_can_run_review_then_re_review(isolated_database) -> None:
    assert _reserve("sha-1") == "TRIGGERING"
    mark_ci_run_running("42", "7", "sha-1")
    mark_ci_run_completed("42", "7", "sha-1")

    assert reserve_ci_run(
        project_id="42",
        mr_id="7",
        commit_sha="sha-1",
        source_branch="feature/example",
        target_branch="main",
        repository_url="https://gitlab.example/repo.git",
        review_event_type="RE_REVIEW",
    ) == "TRIGGERING"
