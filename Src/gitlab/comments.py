import json
from typing import Iterable, Mapping

from ..db.Src import database as db
from .client import GitLabError, project_path, request


def format_ai_review_usage_comment() -> str:
    return """\
## AIレビューの使い方

このMRでは、ビルドと静的解析の成功後にAIレビューが自動で始まります。
必要に応じて、MRコメントで次のコマンドを実行できます。

| コマンド | 動作 |
|---|---|
| `/ai review` | AIレビューを手動で開始 |
| `/ai test` | ユニットテストの生成と実行を開始 |
| `/ai apply <指摘ID>` | 修正案の差分を表示 |
| `/ai approve <指摘ID>` | 修正案をソースブランチへコミット |
| `/ai reject <指摘ID>` | 指摘を却下 |

`apply`、`approve`、`reject`には、AIレビュー結果に表示される指摘ID（例: `R1`）を指定してください。
コマンドの実行にはGitLabプロジェクトのDeveloper以上の権限が必要です。
"""


def format_build_failure_comment() -> str:
    return """\
## ❌ ビルドに失敗しました

Jenkinsのビルドが失敗しました。AIが原因と修正案を解析しています。
解析が完了すると、このMRへ追加のコメントを投稿します。
"""


def _suggestion_text(raw: str | None) -> str:
    if not raw:
        return "（修正提案なし）"
    try:
        suggestion = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return str(raw)
    if not isinstance(suggestion, dict):
        return str(suggestion)
    before = suggestion.get("before", "")
    after = suggestion.get("after", "")
    if not before and not after:
        return "（修正提案なし）"
    return f"```diff\n- {before}\n+ {after}\n```"


def _format_review_finding(finding: Mapping) -> str:
    finding_id = finding["id"]
    description = finding.get("description") or "指摘内容なし"
    file_path = finding.get("file_path") or "（ファイル不明）"
    line_start = finding.get("line_start")
    line_end = finding.get("line_end")
    if line_start is None:
        location = f"`{file_path}`"
    elif line_end and line_end != line_start:
        location = f"`{file_path}` L{line_start}-{line_end}"
    else:
        location = f"`{file_path}` L{line_start}"
    patch = finding.get("fix_patch")
    proposed = f"```diff\n{patch}\n```" if patch else _suggestion_text(
        finding.get("suggestion")
    )
    return (
        f"### {finding_id}\n"
        f"**ファイル：** {location}\n\n"
        f"**指摘：** {description}\n\n"
        f"**修正提案：**\n{proposed}\n\n"
        f"`/ai apply {finding_id}` で差分を確認し、"
        f"`/ai approve {finding_id}` で適用できます。"
    )


def format_review_comment(findings: Iterable[Mapping]) -> str:
    findings = list(findings)
    if not findings:
        return "## AI レビュー結果\n\n指摘はありませんでした。"

    sections = ["## AI レビュー結果"]
    for finding in findings:
        sections.append(_format_review_finding(finding))
    return "\n\n".join(sections)


async def post_comment(project_id: str, mr_id: str, message: str) -> None:
    await request(
        "POST",
        f"projects/{project_path(project_id)}/merge_requests/{mr_id}/notes",
        json={"body": message},
        expected_statuses=(201,),
    )


async def post_review_findings(
    project_id: str,
    mr_id: str,
    finding_ids: list[str],
) -> None:
    findings = []
    for finding_id in finding_ids:
        row = db.query_one(
            "SELECT id, file_path, line_start, line_end, description, suggestion, "
            "fix_patch FROM findings WHERE mr_id=:mr_id AND id=:finding_id",
            {"mr_id": mr_id, "finding_id": finding_id},
        )
        if row is not None:
            findings.append(row)

    if not findings:
        await post_comment(project_id, mr_id, format_review_comment([]))
        return

    try:
        response = await request(
            "GET",
            f"projects/{project_path(project_id)}/merge_requests/{mr_id}/versions",
        )
        versions = response.json()
        latest = versions[0]
        diff_refs = {
            "base_sha": latest["base_commit_sha"],
            "head_sha": latest["head_commit_sha"],
            "start_sha": latest["start_commit_sha"],
        }
    except (GitLabError, IndexError, KeyError, TypeError):
        await post_comment(project_id, mr_id, format_review_comment(findings))
        return

    fallback_findings = []
    for finding in findings:
        file_path = finding.get("file_path")
        try:
            line_start = int(finding.get("line_start"))
        except (TypeError, ValueError):
            fallback_findings.append(finding)
            continue
        if not file_path or line_start <= 0:
            fallback_findings.append(finding)
            continue

        try:
            await request(
                "POST",
                f"projects/{project_path(project_id)}/merge_requests/"
                f"{mr_id}/discussions",
                json={
                    "body": _format_review_finding(finding),
                    "position": {
                        "position_type": "text",
                        **diff_refs,
                        "new_path": file_path,
                        "new_line": line_start,
                    },
                },
                expected_statuses=(201,),
            )
        except GitLabError:
            # GitLab only accepts positions that belong to the current diff.
            # Findings on unchanged or outdated lines remain visible as a
            # regular MR note instead of being lost.
            fallback_findings.append(finding)

    if fallback_findings:
        await post_comment(
            project_id,
            mr_id,
            format_review_comment(fallback_findings),
        )
