from ...gitlab.comments import post_comment
from ...jenkins.client import JenkinsError, trigger_build


async def handle(payload: dict) -> None:
    attrs = payload["object_attributes"]
    mr_id = str(attrs["iid"])
    project_id = str(payload["project"]["id"])
    source_branch = attrs.get("source_branch") or ""
    target_branch = attrs.get("target_branch") or ""
    last_commit = attrs.get("last_commit") or payload.get("last_commit") or {}
    commit_sha = last_commit.get("id") or attrs.get("sha") or ""
    repository_url = (
        payload.get("project", {}).get("git_http_url")
        or payload.get("repository", {}).get("git_http_url")
        or ""
    )
    try:
        await trigger_build(
            project_id=project_id,
            mr_id=mr_id,
            source_branch=source_branch,
            target_branch=target_branch,
            commit_sha=commit_sha,
            repository_url=repository_url,
        )
    except JenkinsError as exc:
        await post_comment(
            project_id,
            mr_id,
            f"⚠️ Jenkinsビルドを開始できませんでした: {exc}",
        )
