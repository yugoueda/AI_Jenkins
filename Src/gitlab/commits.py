import subprocess
import re
from pathlib import Path, PurePosixPath

from .client import project_path, request


class PatchError(RuntimeError):
    pass


_HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$"
)


def _normalize_hunk_counts(patch: str) -> str:
    """Repair incorrect unified-diff hunk counts produced by an agent."""
    lines = patch.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        raw_header = lines[index]
        header = raw_header.rstrip("\r\n")
        match = _HUNK_HEADER.match(header)
        if match is None:
            index += 1
            continue

        end = index + 1
        old_count = 0
        new_count = 0
        while end < len(lines):
            line = lines[end]
            if line.startswith(("@@ ", "diff --git ")):
                break
            if line in ("\n", "\r\n", ""):
                # A bare blank line in a hunk is intended as an unchanged
                # empty line but is missing the required leading space.
                lines[end] = " " + line
                old_count += 1
                new_count += 1
            elif line.startswith(" "):
                old_count += 1
                new_count += 1
            elif line.startswith("-"):
                old_count += 1
            elif line.startswith("+"):
                new_count += 1
            elif not line.startswith("\\ No newline at end of file"):
                raise PatchError(
                    f"invalid unified diff line {end + 1}: {line.rstrip()}"
                )
            end += 1

        newline = raw_header[len(header) :]
        lines[index] = (
            f"@@ -{match.group(1)},{old_count} "
            f"+{match.group(2)},{new_count} @@{match.group(3)}{newline}"
        )
        index = end
    return "".join(lines)


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


def _file_patch_sections(patch: str) -> list[str]:
    lines = patch.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith("diff --git ")]
    if not starts:
        return [patch]
    if any(line.strip() for line in lines[: starts[0]]):
        raise PatchError("patch contains content before the first file header")
    starts.append(len(lines))
    return ["".join(lines[start:end]) for start, end in zip(starts, starts[1:])]


def _prepare_patch(patch: str) -> tuple[list[tuple[str | None, str | None]], str]:
    patch = _normalize_hunk_counts(patch)
    files: list[tuple[str | None, str | None]] = []
    applicable_sections: list[str] = []
    for section in _file_patch_sections(patch):
        section_files = _patch_files(section)
        if len(section_files) != 1:
            raise PatchError("each patch section must change exactly one file")
        old_path, new_path = section_files[0]
        files.append((old_path, new_path))
        if new_path is None:
            if "deleted file mode " not in section:
                raise PatchError("deleted file patch is missing deleted file mode")
            continue
        applicable_sections.append(section)
    return files, "".join(applicable_sections)


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
) -> str | None:
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise PatchError(f"workspace not found: {root}")
    files, applicable_patch = _prepare_patch(patch)
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

    if applicable_patch:
        _run_git(root, ["apply", "--check", "-"], applicable_patch)
        _run_git(root, ["apply", "-"], applicable_patch)
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
        response = await request(
            "POST",
            f"projects/{project_path(project_id)}/repository/commits",
            json={
                "branch": branch,
                "commit_message": f"fix(ai-review): apply {finding_id}",
                "actions": actions,
            },
            expected_statuses=(201,),
        )
        commit_sha = str(response.json().get("id") or "") or None
    finally:
        if applicable_patch:
            _run_git(root, ["apply", "--reverse", "-"], applicable_patch)
    return commit_sha


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
