import subprocess


def build_diff_context(changed_files: list[str], event_type: str) -> str:
    result = subprocess.run(
        ["git", "diff", "-W", "origin/main...HEAD", "--", *changed_files],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout or "（差分なし）"
