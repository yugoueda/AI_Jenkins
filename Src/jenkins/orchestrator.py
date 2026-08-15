from .client import JenkinsError, trigger_build
from .runs import (
    claim_next_pending_ci_run,
    mark_ci_run_failed,
    mark_ci_run_running,
    reserve_ci_run,
)


async def schedule_build(
    *,
    project_id: str,
    mr_id: str,
    source_branch: str,
    target_branch: str,
    commit_sha: str,
    repository_url: str = "",
) -> str:
    if not commit_sha:
        await trigger_build(
            project_id=project_id,
            mr_id=mr_id,
            source_branch=source_branch,
            target_branch=target_branch,
            commit_sha=commit_sha,
            repository_url=repository_url,
        )
        return "STARTED"

    status = reserve_ci_run(
        project_id=project_id,
        mr_id=mr_id,
        commit_sha=commit_sha,
        source_branch=source_branch,
        target_branch=target_branch,
        repository_url=repository_url,
    )
    if status == "DUPLICATE":
        return status
    if status == "PENDING":
        return status

    await _start_reserved_build(
        {
            "project_id": project_id,
            "mr_id": mr_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "commit_sha": commit_sha,
            "repository_url": repository_url,
        }
    )
    return "STARTED"


async def start_next_pending_build(project_id: str, mr_id: str) -> dict | None:
    run = claim_next_pending_ci_run(project_id, mr_id)
    if run is None:
        return None
    await _start_reserved_build(run)
    return run


async def _start_reserved_build(run: dict) -> None:
    try:
        await trigger_build(
            project_id=run["project_id"],
            mr_id=run["mr_id"],
            source_branch=run["source_branch"],
            target_branch=run["target_branch"],
            commit_sha=run["commit_sha"],
            repository_url=run["repository_url"],
        )
    except JenkinsError:
        mark_ci_run_failed(
            run["project_id"],
            run["mr_id"],
            run["commit_sha"],
        )
        raise
    mark_ci_run_running(
        run["project_id"],
        run["mr_id"],
        run["commit_sha"],
    )
