import subprocess
from pathlib import Path, PurePosixPath

from .client import project_path, request


class PatchError(RuntimeError):
    pass


def _safe_path(raw: str) -> str | None:
    raw = raw.strip().split("\t", 1)[0]
    if raw == "/dev/null":
        return None
    if raw.startswith(("a/", "b/")):
        raw = raw[2:]
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise PatchError(f"unsafe path in patch: {raw}")
    return str(path)


def _patch_files(patch: str) -> list[tuple[str | None, str | None]]:
    files: list[tuple[str | None, str | None]] = []
    old_path: str | None = None
    for line in patch.splitlines():
        if line.startswith("--- "):
            old_path = _safe_path(line[4:])
        elif line.startswith("+++ "):
            new_path = _safe_path(line[4:])
            if old_path is None and new_path is None:
                raise PatchError("patch cannot have /dev/null on both sides")
            files.append((old_path, new_path))
            old_path = None
    if not files:
        raise PatchError("patch does not contain any file changes")
    return files


def _run_git(workspace: Path, args: list[str], patch: str | None = None) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        input=patch,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise PatchError(f"git {' '.join(args)} failed: {detail}")


async def commit_patch(
    project_id: str,
    branch: str,
    finding_id: str,
    patch: str,
    workspace: str,
) -> None:
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise PatchError(f"workspace not found: {root}")
    files = _patch_files(patch)
    touched = sorted({path for pair in files for path in pair if path})
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *touched],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise PatchError("patch target files contain local changes")

    _run_git(root, ["apply", "--check", "-"], patch)
    _run_git(root, ["apply", "-"], patch)
    try:
        actions = []
        for old_path, new_path in files:
            if old_path is None and new_path is not None:
                actions.append(
                    {
                        "action": "create",
                        "file_path": new_path,
                        "content": (root / new_path).read_text(),
                    }
                )
            elif new_path is None and old_path is not None:
                actions.append({"action": "delete", "file_path": old_path})
            elif old_path == new_path and new_path is not None:
                actions.append(
                    {
                        "action": "update",
                        "file_path": new_path,
                        "content": (root / new_path).read_text(),
                    }
                )
            elif old_path is not None and new_path is not None:
                actions.append(
                    {
                        "action": "move",
                        "previous_path": old_path,
                        "file_path": new_path,
                        "content": (root / new_path).read_text(),
                    }
                )
        await request(
            "POST",
            f"projects/{project_path(project_id)}/repository/commits",
            json={
                "branch": branch,
                "commit_message": f"fix(ai-review): apply {finding_id}",
                "actions": actions,
            },
            expected_statuses=(201,),
        )
    finally:
        _run_git(root, ["apply", "--reverse", "-"], patch)


async def commit_generated_files(
    project_id: str,
    branch: str,
    files: list[tuple[str, str]],
) -> None:
    actions = []
    for file_path, content in files:
        safe_path = _safe_path(file_path)
        if safe_path is None:
            raise PatchError("generated test path cannot be /dev/null")
        response = await request(
            "GET",
            f"projects/{project_path(project_id)}/repository/files/"
            f"{project_path(safe_path)}",
            params={"ref": branch},
            expected_statuses=(200, 404),
        )
        actions.append(
            {
                "action": "update" if response.status_code == 200 else "create",
                "file_path": safe_path,
                "content": content,
            }
        )
    await request(
        "POST",
        f"projects/{project_path(project_id)}/repository/commits",
        json={
            "branch": branch,
            "commit_message": "test(ai-review): add generated unit tests",
            "actions": actions,
        },
        expected_statuses=(201,),
    )
