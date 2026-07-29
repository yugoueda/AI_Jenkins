import asyncio
from pathlib import Path

import Src.worker as worker
from Src.agent import dispatcher
from Src.webhook.queue import enqueue


FAKE_CLI = Path(__file__).parent / "fixtures" / "fake_claude.py"


def test_worker_marks_success(isolated_database, monkeypatch) -> None:
    job_id = enqueue("10", "REVIEW", {})

    async def successful_dispatch(job: dict) -> None:
        assert job["job_id"] == job_id

    monkeypatch.setattr(worker, "dispatch", successful_dispatch)

    assert asyncio.run(worker.process_once())
    assert isolated_database.query_scalar(
        "SELECT status FROM job_queue WHERE job_id=:job_id",
        {"job_id": job_id},
    ) == "DONE"


def test_worker_marks_failure(isolated_database, monkeypatch) -> None:
    job_id = enqueue("10", "REVIEW", {})

    async def failed_dispatch(job: dict) -> None:
        raise RuntimeError("expected test failure")

    monkeypatch.setattr(worker, "dispatch", failed_dispatch)

    assert asyncio.run(worker.process_once())
    assert isolated_database.query_scalar(
        "SELECT status FROM job_queue WHERE job_id=:job_id",
        {"job_id": job_id},
    ) == "FAILED"


def test_worker_runs_review_through_cli(
    isolated_database, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(FAKE_CLI))
    monkeypatch.setenv("AGENT_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        dispatcher.review_prompt,
        "build_review_prompt_with_ci",
        lambda *args, **kwargs: "review prompt",
    )
    job_id = enqueue(
        "20",
        "REVIEW",
        {"workspace_path": str(tmp_path), "changed_files": []},
    )

    assert asyncio.run(worker.process_once())
    assert isolated_database.query_scalar(
        "SELECT status FROM job_queue WHERE job_id=:job_id",
        {"job_id": job_id},
    ) == "DONE"
    assert isolated_database.query_scalar(
        "SELECT COUNT(*) FROM findings WHERE mr_id='20'"
    ) == 0
