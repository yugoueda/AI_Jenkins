import hashlib

from .. import gitlab_stub as gitlab
from ..parser import AiCommand, ReviewCommand, parse
from ..queue import enqueue
from ...db.Src import database as db


class CommandError(Exception):
    pass


async def handle(payload: dict) -> None:
    attrs = payload.get("object_attributes", {})
    if attrs.get("noteable_type") != "MergeRequest":
        return

    mr = payload.get("merge_request", {})
    mr_id = str(mr.get("iid") or attrs.get("noteable_iid"))
    command = parse(attrs.get("note", ""))
    if command is None:
        return

    try:
        if isinstance(command, ReviewCommand):
            await _handle_review(mr_id, command)
        elif isinstance(command, AiCommand):
            await _handle_ai(mr_id, command)
    except CommandError as exc:
        await _post_error(mr_id, str(exc))


async def _handle_review(mr_id: str, cmd: ReviewCommand) -> None:
    return


async def _handle_ai(mr_id: str, cmd: AiCommand) -> None:
    if cmd.cmd in ("approve", "reject") and not cmd.finding_id:
        raise CommandError(f"/ai {cmd.cmd} にはIDが必要です")

    if cmd.cmd == "approve":
        finding = _get_finding_or_error(mr_id, cmd.finding_id, required_status="OPEN")
        if not finding["fix_patch"] or not finding["fix_patch_sha256"]:
            raise CommandError(f"{cmd.finding_id} に修正パッチがありません")
        actual_hash = hashlib.sha256(finding["fix_patch"].encode()).hexdigest()
        if actual_hash != finding["fix_patch_sha256"]:
            raise CommandError(f"{cmd.finding_id} の修正パッチハッシュが一致しません")
        enqueue(mr_id, "APPROVE", {"finding_id": cmd.finding_id})
        return

    if cmd.cmd == "reject":
        _get_finding_or_error(mr_id, cmd.finding_id)
        db.execute(
            "UPDATE findings SET status='REJECTED', updated_at=CURRENT_TIMESTAMP "
            "WHERE id=:finding_id",
            {"finding_id": cmd.finding_id},
        )
        return

    if cmd.cmd == "test":
        enqueue(mr_id, "UNIT_TEST_GEN", {})


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


async def _post_error(mr_id: str, message: str) -> None:
    await gitlab.post_comment(mr_id, f"エラー: {message}")
