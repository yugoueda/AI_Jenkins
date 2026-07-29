from Src.webhook.queue import (
    can_process,
    claim_next_waiting_job,
    complete_job,
    enqueue,
    is_agent_busy,
    recover_stale_jobs,
)


def test_job_lifecycle(isolated_database) -> None:
    first_id = enqueue("10", "REVIEW", {"changed_files": ["lib/a.dart"]})
    second_id = enqueue("11", "UNIT_TEST_GEN", {})

    assert not is_agent_busy()
    claimed = claim_next_waiting_job()

    assert claimed is not None
    assert claimed["job_id"] == first_id
    assert is_agent_busy()
    assert not can_process("10")
    assert can_process("11")
    assert claim_next_waiting_job() is None

    complete_job(first_id, succeeded=True)
    second = claim_next_waiting_job()
    assert second is not None
    assert second["job_id"] == second_id
    complete_job(second_id, succeeded=False)

    statuses = {
        first_id: isolated_database.query_scalar(
            "SELECT status FROM job_queue WHERE job_id=:job_id",
            {"job_id": first_id},
        ),
        second_id: isolated_database.query_scalar(
            "SELECT status FROM job_queue WHERE job_id=:job_id",
            {"job_id": second_id},
        ),
    }
    assert statuses == {first_id: "DONE", second_id: "FAILED"}


def test_recover_stale_jobs(isolated_database) -> None:
    job_id = enqueue("10", "REVIEW", {})
    assert claim_next_waiting_job() is not None

    assert recover_stale_jobs() == 1
    assert isolated_database.query_scalar(
        "SELECT status FROM job_queue WHERE job_id=:job_id",
        {"job_id": job_id},
    ) == "FAILED"
