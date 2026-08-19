import hashlib
import os

from ... import gitlab
from ..parser import AiCommand, ReviewCommand, parse
from ..queue import enqueue
from ...db.Src import database as db
from ...jenkins.client import JenkinsError
from ...jenkins.orchestrator import schedule_build


class CommandError(Exception):
    pass


async def handle(payload: dict) -> None:
    attrs = payload.get("object_attributes", {})
    if attrs.get("noteable_type") != "MergeRequest":
        return

    mr = payload.get("merge_request", {})
    mr_id = str(mr.get("iid") or attrs.get("noteable_iid"))
    project_id = str(payload.get("project", {}).get("id") or "")
    source_branch = mr.get("source_branch") or ""
    target_branch = mr.get("target_branch") or ""
    repository_url = payload.get("project", {}).get("git_http_url") or ""
    last_commit = mr.get("last_commit") or {}
    commit_sha = str(last_commit.get("id") or mr.get("sha") or "")
    body = attrs.get("note", "")
    command = parse(body)
    if command is None:
        if body.strip().startswith(("/review", "/ai")):
            await _post_error(
                project_id,
                mr_id,
                "/review または /ai apply|approve|reject|test|review の形式で入力してください",
            )
        return

    try:
        if isinstance(command, ReviewCommand):
            await _handle_review(mr_id, command)
        elif isinstance(command, AiCommand):
            if os.getenv("GITLAB_ENFORCE_COMMAND_ROLES", "true").lower() not in (
                "0",
                "false",
                "no",
            ):
                user_id = str(
                    payload.get("user", {}).get("id")
                    or attrs.get("author_id")
                    or ""
                )
                if not project_id or not user_id:
                    raise CommandError("コマンド実行者を確認できません")
                if not await gitlab.user_can_operate(project_id, user_id):
                    raise CommandError(
                        "このコマンドにはDeveloper以上の権限が必要です"
                    )
            await _handle_ai(
                project_id,
                mr_id,
                source_branch,
                target_branch,
                repository_url,
                commit_sha,
                command,
            )
    except CommandError as exc:
        await _post_error(project_id, mr_id, str(exc))


async def _handle_review(mr_id: str, cmd: ReviewCommand) -> None:
    return


async def _handle_ai(
    project_id: str,
    mr_id: str,
    source_branch: str,
    target_branch: str,
    repository_url: str,
    commit_sha: str,
    cmd: AiCommand,
) -> None:
    if cmd.cmd in ("apply", "approve", "reject") and not cmd.finding_id:
        raise CommandError(f"/ai {cmd.cmd} にはIDが必要です")
    if cmd.cmd in ("test", "review") and cmd.finding_id:
        raise CommandError(f"/ai {cmd.cmd} にIDは指定できません")

    base_payload = {
        "project_id": project_id,
        "source_branch": source_branch,
        "target_branch": target_branch,
        "repository_url": repository_url,
    }

    if cmd.cmd == "apply":
        finding = _get_finding_or_error(mr_id, cmd.finding_id, required_status="OPEN")
        if not finding["fix_patch"]:
            raise CommandError(f"{cmd.finding_id} に修正パッチがありません")
        enqueue(
            mr_id,
            "APPLY",
            {**base_payload, "finding_id": cmd.finding_id},
        )
        return

    if cmd.cmd == "approve":
        finding = _get_finding_or_error(mr_id, cmd.finding_id, required_status="OPEN")
        if not finding["fix_patch"] or not finding["fix_patch_sha256"]:
            raise CommandError(f"{cmd.finding_id} に修正パッチがありません")
        actual_hash = hashlib.sha256(finding["fix_patch"].encode()).hexdigest()
        if actual_hash != finding["fix_patch_sha256"]:
            raise CommandError(f"{cmd.finding_id} の修正パッチハッシュが一致しません")
        enqueue(
            mr_id,
            "APPROVE",
            {**base_payload, "finding_id": cmd.finding_id},
        )
        return

    if cmd.cmd == "reject":
        _get_finding_or_error(mr_id, cmd.finding_id)
        db.execute(
            "UPDATE findings SET status='REJECTED', updated_at=CURRENT_TIMESTAMP "
            "WHERE mr_id=:mr_id AND id=:finding_id",
            {"mr_id": mr_id, "finding_id": cmd.finding_id},
        )
        await gitlab.post_comment(
            project_id,
            mr_id,
            f"✅ {cmd.finding_id} の指摘を却下しました。",
        )
        if not db.query_scalar(
            "SELECT COUNT(*) FROM findings "
            "WHERE mr_id=:mr_id AND status='OPEN'",
            {"mr_id": mr_id},
        ):
            if not commit_sha:
                await _post_error(
                    project_id,
                    mr_id,
                    "最新コミットSHAを取得できず、再ビルドを開始できません",
                )
                return
            try:
                await schedule_build(
                    project_id=project_id,
                    mr_id=mr_id,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    commit_sha=commit_sha,
                    repository_url=repository_url,
                    review_event_type="POST_RESOLUTION",
                )
            except JenkinsError as exc:
                await _post_error(
                    project_id,
                    mr_id,
                    f"再レビュー用ビルドを開始できません: {exc}",
                )
            else:
                await gitlab.post_comment(
                    project_id,
                    mr_id,
                    "🔄 全指摘の対応が完了したため、再レビュー用ビルドを開始しました。",
                )
        return

    if cmd.cmd == "test":
        enqueue(mr_id, "UNIT_TEST_GEN", base_payload)
        return

    if cmd.cmd == "review":
        enqueue(
            mr_id,
            "REVIEW",
            {
                **base_payload,
                "changed_files": [],
                "build_result": "MANUAL",
                "lint_result": "BYPASSED",
            },
        )


def _get_finding_or_error(
    mr_id: str,
    finding_id: str | None,
    required_status: str | None = None,
) -> dict:
    row = db.query_one(
        "SELECT id, status, fix_patch, fix_patch_sha256 "
        "FROM findings WHERE mr_id=:mr_id AND id=:finding_id",
        {"mr_id": mr_id, "finding_id": finding_id},
    )
    if row is None:
        raise CommandError(f"{finding_id} は存在しません")
    if required_status and row["status"] != required_status:
        raise CommandError(f"{finding_id} は現在 {row['status']} のため実行できません")
    return row


async def _post_error(project_id: str, mr_id: str, message: str) -> None:
    await gitlab.post_comment(project_id, mr_id, f"⚠️ エラー：{message}")
