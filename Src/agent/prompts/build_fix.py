from ..context import build_diff_context


def build_build_fix_prompt(
    mr_id: str,
    changed_files: list[str],
    build_result: str,
    working_directory: str | None = None,
    target_branch: str = "main",
) -> str:
    diff = build_diff_context(
        changed_files,
        "BUILD_FIX",
        working_directory,
        target_branch,
    )
    return f"""あなたはビルドエラーの診断担当です。
MR !{mr_id} の差分とビルド結果を確認し、ビルドエラーの原因と最小の修正案を提示してください。
コードを直接変更せず、Markdownで原因・対象箇所・修正案を返してください。

ビルド結果:
{build_result}

差分:
{diff}
"""
