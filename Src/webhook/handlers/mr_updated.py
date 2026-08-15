from ... import gitlab
from ...db.Src import database as db
from ...gitlab.comments import post_comment
from ...jenkins.client import JenkinsError
from ...jenkins.orchestrator import schedule_build
from ..queue import enqueue


async def handle(payload: dict) -> None:
    attrs = payload["object_attributes"]
    mr_id = str(attrs["iid"])
    project_id = str(payload["project"]["id"])
    if attrs.get("oldrev"):
        await _handle_commit_added(payload, project_id, mr_id)
        return
    if not await gitlab.all_discussions_resolved(project_id, mr_id):
        return
    enqueue(
        mr_id,
        "RE_REVIEW",
        {
            "project_id": project_id,
            "source_branch": attrs.get("source_branch"),
            "target_branch": attrs.get("target_branch"),
            "repository_url": payload.get("project", {}).get("git_http_url", ""),
            "changed_files": [],
            "build_result": payload.get("build_result"),
            "lint_result": payload.get("lint_result"),
        },
    )


async def _handle_commit_added(payload: dict, project_id: str, mr_id: str) -> None:
    attrs = payload["object_attributes"]
    if attrs.get("state") != "opened" and attrs.get("state_id") != 1:
        return
    if db.query_scalar(
        "SELECT COUNT(*) FROM findings WHERE mr_id=:mr_id",
        {"mr_id": mr_id},
    ):
        return

    last_commit = attrs.get("last_commit") or payload.get("last_commit") or {}
    commit_sha = str(last_commit.get("id") or attrs.get("sha") or "")
    if not commit_sha or commit_sha == str(attrs.get("oldrev") or ""):
        return

    try:
        await schedule_build(
            project_id=project_id,
            mr_id=mr_id,
            source_branch=str(attrs.get("source_branch") or ""),
            target_branch=str(attrs.get("target_branch") or ""),
            commit_sha=commit_sha,
            repository_url=str(payload.get("project", {}).get("git_http_url") or ""),
        )
    except JenkinsError as exc:
        await post_comment(
            project_id,
            mr_id,
            f"⚠️ 追加コミットの再ビルドを開始できませんでした: {exc}",
        )
