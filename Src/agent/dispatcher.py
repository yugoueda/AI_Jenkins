import hashlib
import json
import logging

from .checkpoints import get_review_checkpoint, save_review_checkpoint
from .prompts import build_fix as build_fix_prompt
from .parser import parse_and_save_review, parse_and_save_unit_tests
from .prompts import review as review_prompt
from .prompts import unit_test as unit_test_prompt
from .runner import run_agent
from .workspace import prepare_workspace
from ..db.Src import database as db
from ..gitlab import comments as gitlab_comments
from ..gitlab.commits import PatchError, commit_generated_files, commit_patch
from ..jenkins.client import JenkinsError, trigger_test
from ..jenkins.orchestrator import schedule_build
from ..webhook.queue import enqueue


class AgentExecutionError(RuntimeError):
    pass


async def dispatch(job: dict) -> None:
    event_type = job["event_type"]
    payload = json.loads(job["payload"])
    mr_id = job["mr_id"]
    working_directory = prepare_workspace(payload, mr_id)
    project_id = str(payload.get("project_id") or "")
    source_branch = str(payload.get("source_branch") or "")
    target_branch = str(payload.get("target_branch") or "main")

    if event_type == "BUILD_FIX":
        prompt = build_fix_prompt.build_build_fix_prompt(
            mr_id,
            payload.get("changed_files", []),
            _ci_result(payload, "build") or "ビルド失敗（詳細なし）",
            working_directory,
            target_branch,
        )
        returncode, output = await run_agent(prompt, event_type, working_directory)
        if returncode != 0:
            await _handle_failure(project_id, mr_id, event_type, output)
        await _post_comment(
            project_id,
            mr_id,
            "## ビルドエラー修正案\n\n" + output[:20_000],
        )
        return

    if event_type in ("REVIEW", "RE_REVIEW"):
        changed_files = payload.get("changed_files", [])
        commit_sha = str(payload.get("commit_sha") or "")
        base_commit = get_review_checkpoint(project_id, mr_id)
        prompt = review_prompt.build_review_prompt_with_ci(
            mr_id,
            changed_files,
            build_result=_ci_result(payload, "build"),
            lint_result=_ci_result(payload, "lint"),
            working_directory=working_directory,
            target_branch=target_branch,
            base_commit=base_commit,
        )
        returncode, output = await run_agent(prompt, event_type, working_directory)
        if returncode == 0:
            try:
                finding_ids = parse_and_save_review(mr_id, output)
            except (TypeError, ValueError) as exc:
                await _handle_failure(project_id, mr_id, event_type, str(exc))
            await _require_project(project_id)
            await gitlab_comments.post_review_findings(
                project_id,
                mr_id,
                finding_ids,
            )
            if commit_sha:
                save_review_checkpoint(project_id, mr_id, commit_sha)
            if event_type == "RE_REVIEW" and not finding_ids:
                enqueue(
                    mr_id,
                    "UNIT_TEST_GEN",
                    {
                        **payload,
                        "project_id": project_id,
                        "source_branch": source_branch,
                    },
                )
        else:
            await _handle_failure(project_id, mr_id, event_type, output)
        return

    if event_type in ("APPLY", "APPROVE"):
        finding_id = payload["finding_id"]
        row = db.query_one(
            "SELECT fix_patch, fix_patch_sha256 FROM findings "
            "WHERE id=:finding_id AND mr_id=:mr_id AND status='OPEN'",
            {"finding_id": finding_id, "mr_id": mr_id},
        )
        if row is None or not row["fix_patch"]:
            await _handle_failure(
                project_id,
                mr_id,
                event_type,
                f"open finding or patch not found: {finding_id}",
            )
        patch = row["fix_patch"]
        if hashlib.sha256(patch.encode()).hexdigest() != row["fix_patch_sha256"]:
            await _handle_failure(
                project_id,
                mr_id,
                event_type,
                "fix_patch sha256 mismatch",
            )
        await _require_project(project_id)
        if event_type == "APPLY":
            await gitlab_comments.post_comment(
                project_id,
                mr_id,
                f"## {finding_id} 修正差分\n\n```diff\n{patch}\n```\n\n"
                f"適用する場合は `/ai approve {finding_id}` を実行してください。",
            )
        else:
            if not source_branch:
                await _handle_failure(
                    project_id,
                    mr_id,
                    event_type,
                    "source branch is missing",
                )
            try:
                commit_sha = await commit_patch(
                    project_id,
                    source_branch,
                    finding_id,
                    patch,
                    working_directory,
                )
            except PatchError as exc:
                await _handle_failure(
                    project_id,
                    mr_id,
                    event_type,
                    str(exc),
                )
            db.execute(
                "UPDATE findings SET status='APPLIED', updated_at=CURRENT_TIMESTAMP "
                "WHERE id=:finding_id AND mr_id=:mr_id",
                {"finding_id": finding_id, "mr_id": mr_id},
            )
            await gitlab_comments.post_comment(
                project_id,
                mr_id,
                f"✅ {finding_id} の修正パッチを `{source_branch}` にコミットしました。",
            )
            if not db.query_scalar(
                "SELECT COUNT(*) FROM findings "
                "WHERE mr_id=:mr_id AND status='OPEN'",
                {"mr_id": mr_id},
            ):
                if not commit_sha:
                    await gitlab_comments.post_comment(
                        project_id,
                        mr_id,
                        "⚠️ 修正コミットSHAを取得できず、再ビルドを開始できませんでした。",
                    )
                else:
                    try:
                        build_status = await schedule_build(
                            project_id=project_id,
                            mr_id=mr_id,
                            source_branch=source_branch,
                            target_branch=target_branch,
                            commit_sha=commit_sha,
                            repository_url=str(payload.get("repository_url") or ""),
                            review_event_type="RE_REVIEW",
                        )
                    except JenkinsError as exc:
                        await gitlab_comments.post_comment(
                            project_id,
                            mr_id,
                            f"⚠️ 再レビュー用ビルドを開始できませんでした: {exc}",
                        )
                    else:
                        await gitlab_comments.post_comment(
                            project_id,
                            mr_id,
                            f"🔄 全指摘の対応が完了したため、再レビュー用ビルドを開始しました（{build_status}）。",
                        )
        return

    if event_type == "UNIT_TEST_GEN":
        changed_files = payload.get("changed_files", [])
        uncovered_lines = payload.get("uncovered_lines", {})
        prompt = unit_test_prompt.build_unit_test_prompt(
            mr_id,
            changed_files,
            uncovered_lines,
            working_directory=working_directory,
            target_branch=target_branch,
        )
        returncode, output = await run_agent(prompt, event_type, working_directory)
        if returncode == 0:
            generated_files = parse_and_save_unit_tests(mr_id, output)
            if not generated_files:
                await _handle_failure(
                    project_id,
                    mr_id,
                    event_type,
                    "agent did not return any generated tests",
                )
            await _require_project(project_id)
            if not source_branch:
                await _handle_failure(
                    project_id,
                    mr_id,
                    event_type,
                    "source branch is missing",
                )
            await commit_generated_files(
                project_id,
                source_branch,
                generated_files,
            )
            await trigger_test(
                project_id=project_id,
                mr_id=mr_id,
                source_branch=source_branch,
                repository_url=str(payload.get("repository_url") or ""),
            )
        else:
            await _handle_failure(project_id, mr_id, event_type, output)
        return

    raise ValueError(f"unsupported event_type: {event_type}")


async def _require_project(project_id: str) -> None:
    if not project_id:
        raise AgentExecutionError("project_id is missing from job payload")


def _ci_result(payload: dict, name: str) -> str | None:
    result = payload.get(f"{name}_result")
    log = payload.get(f"{name}_log")
    if result is None and not log:
        return None
    return f"status: {result or 'UNKNOWN'}\n\nlog:\n{log or '（ログなし）'}"


async def _post_comment(project_id: str, mr_id: str, message: str) -> None:
    await _require_project(project_id)
    await gitlab_comments.post_comment(project_id, mr_id, message)


async def _handle_failure(
    project_id: str,
    mr_id: str,
    event_type: str,
    error_output: str,
) -> None:
    logging.error("[%s] mr=%s error=%s", event_type, mr_id, error_output[:500])
    if project_id:
        await gitlab_comments.post_comment(
            project_id,
            mr_id,
            f"⚠️ {event_type} ジョブに失敗しました: {error_output[:1000]}",
        )
    raise AgentExecutionError(f"{event_type} failed for MR {mr_id}: {error_output[:500]}")
