import subprocess
from pathlib import Path


def build_diff_context(
    changed_files: list[str],
    event_type: str,
    working_directory: str | None = None,
) -> str:
    cwd = Path(working_directory).resolve() if working_directory else Path.cwd()
    result = subprocess.run(
        ["git", "diff", "-W", "origin/main...HEAD", "--", *changed_files],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or "unknown git diff error"
        raise RuntimeError(f"failed to build diff context in {cwd}: {error}")
    return result.stdout or "（差分なし）"
