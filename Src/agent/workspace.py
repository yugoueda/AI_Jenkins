import base64
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse


class WorkspaceError(RuntimeError):
    pass


def _git_auth_args() -> list[str]:
    token = os.getenv("GITLAB_TOKEN", "")
    if not token:
        raise WorkspaceError("GITLAB_TOKEN is required to prepare the workspace")
    encoded = base64.b64encode(f"oauth2:{token}".encode()).decode()
    return ["-c", f"http.extraHeader=Authorization: Basic {encoded}"]


def _run(cwd: Path, args: list[str]) -> None:
    result = subprocess.run(
        ["git", *_git_auth_args(), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WorkspaceError(f"git operation failed: {detail}")


def _validate_repository_url(repository_url: str) -> None:
    repository = urlparse(repository_url)
    gitlab = urlparse(os.getenv("GITLAB_URL", ""))
    if repository.scheme not in ("http", "https") or not repository.hostname:
        raise WorkspaceError("repository URL must use HTTP(S)")
    if repository.username or repository.password:
        raise WorkspaceError("repository URL must not contain credentials")
    if gitlab.hostname and repository.hostname != gitlab.hostname:
        raise WorkspaceError("repository URL host does not match GITLAB_URL")


def prepare_workspace(payload: dict, mr_id: str) -> str:
    explicit = payload.get("workspace_path")
    workspace_root = Path(os.getenv("AGENT_WORKSPACE_ROOT", "/workspace")).resolve()
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_absolute():
            candidate = workspace_root / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(workspace_root):
            raise WorkspaceError(f"workspace is outside AGENT_WORKSPACE_ROOT: {candidate}")
        return str(candidate)

    repository_url = str(payload.get("repository_url") or "")
    project_id = str(payload.get("project_id") or "")
    source_branch = str(payload.get("source_branch") or "")
    target_branch = str(payload.get("target_branch") or "main")
    commit_sha = str(payload.get("commit_sha") or "")
    if not repository_url:
        return str(workspace_root)
    if not project_id or not source_branch:
        raise WorkspaceError("project_id and source_branch are required")
    _validate_repository_url(repository_url)

    workspace = (workspace_root / project_id / mr_id).resolve()
    if not workspace.is_relative_to(workspace_root):
        raise WorkspaceError("derived workspace is outside AGENT_WORKSPACE_ROOT")
    workspace.parent.mkdir(parents=True, exist_ok=True)
    if not (workspace / ".git").is_dir():
        workspace.mkdir(exist_ok=True)
        _run(workspace, ["clone", "--no-checkout", repository_url, "."])
    else:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if remote.returncode != 0 or remote.stdout.strip() != repository_url:
            raise WorkspaceError("existing workspace origin does not match webhook project")

    _run(
        workspace,
        [
            "fetch",
            "--prune",
            "origin",
            f"+refs/heads/{source_branch}:refs/remotes/origin/{source_branch}",
            f"+refs/heads/{target_branch}:refs/remotes/origin/{target_branch}",
        ],
    )
    # A newer branch tip may exist by the time a queued review starts. Check
    # out the exact commit that Jenkins built so the recorded checkpoint and
    # the reviewed HEAD always refer to the same source state.
    checkout_ref = commit_sha or f"origin/{source_branch}"
    _run(workspace, ["checkout", "-B", source_branch, checkout_ref])
    return str(workspace)
