import asyncio
import hashlib

from Src.webhook.handlers import mr_updated, note


def _note_payload(body: str, mr_id: int = 7) -> dict:
    return {
        "object_attributes": {
            "noteable_type": "MergeRequest",
            "note": body,
        },
        "merge_request": {"iid": mr_id},
    }


def _insert_finding(
    database,
    *,
    finding_id: str = "R1",
    mr_id: str = "7",
    status: str = "OPEN",
    patch: str | None = "diff --git a/a b/a",
    patch_hash: str | None = None,
) -> None:
    if patch_hash is None and patch is not None:
        patch_hash = hashlib.sha256(patch.encode()).hexdigest()
    database.execute(
        "INSERT INTO findings "
        "(id, mr_id, source, status, fix_patch, fix_patch_sha256) "
        "VALUES (:id, :mr_id, 'AI', :status, :patch, :patch_hash)",
        {
            "id": finding_id,
            "mr_id": mr_id,
            "status": status,
            "patch": patch,
            "patch_hash": patch_hash,
        },
    )


def test_approve_enqueues_job(isolated_database) -> None:
    _insert_finding(isolated_database)

    asyncio.run(note.handle(_note_payload("/ai approve R1")))

    row = isolated_database.query_one(
        "SELECT event_type, status, payload FROM job_queue"
    )
    assert row is not None
    assert (row["event_type"], row["status"]) == ("APPROVE", "WAITING")
    assert '"finding_id": "R1"' in row["payload"]


def test_reject_updates_finding(isolated_database) -> None:
    _insert_finding(isolated_database)

    asyncio.run(note.handle(_note_payload("/ai reject R1")))

    assert isolated_database.query_scalar(
        "SELECT status FROM findings WHERE id='R1'"
    ) == "REJECTED"


def test_test_command_enqueues_unit_test_job(isolated_database) -> None:
    asyncio.run(note.handle(_note_payload("/ai test")))

    assert isolated_database.query_scalar(
        "SELECT COUNT(*) FROM job_queue WHERE event_type='UNIT_TEST_GEN'"
    ) == 1


def test_command_errors_are_posted_to_gitlab(
    isolated_database, monkeypatch
) -> None:
    messages: list[tuple[str, str]] = []

    async def capture_comment(mr_id: str, message: str) -> None:
        messages.append((mr_id, message))

    monkeypatch.setattr(note.gitlab, "post_comment", capture_comment)

    asyncio.run(note.handle(_note_payload("/ai approve R404")))
    asyncio.run(note.handle(_note_payload("/ai test R1")))
    asyncio.run(note.handle(_note_payload("/ai unknown")))

    assert messages == [
        ("7", "⚠️ エラー：R404 は存在しません"),
        ("7", "⚠️ エラー：/ai test にIDは指定できません"),
        (
            "7",
            "⚠️ エラー：/review または /ai approve|reject|test の形式で入力してください",
        ),
    ]


def test_approve_validation_errors_are_posted(
    isolated_database, monkeypatch
) -> None:
    _insert_finding(
        isolated_database,
        finding_id="R1",
        status="REJECTED",
    )
    _insert_finding(
        isolated_database,
        finding_id="R2",
        patch=None,
    )
    messages: list[str] = []

    async def capture_comment(mr_id: str, message: str) -> None:
        messages.append(message)

    monkeypatch.setattr(note.gitlab, "post_comment", capture_comment)

    asyncio.run(note.handle(_note_payload("/ai approve")))
    asyncio.run(note.handle(_note_payload("/ai approve R1")))
    asyncio.run(note.handle(_note_payload("/ai approve R2")))

    assert messages == [
        "⚠️ エラー：/ai approve にはIDが必要です",
        "⚠️ エラー：R1 は現在 REJECTED のため実行できません",
        "⚠️ エラー：R2 に修正パッチがありません",
    ]
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_approve_rejects_invalid_patch_hash(
    isolated_database, monkeypatch
) -> None:
    _insert_finding(isolated_database, patch_hash="invalid")
    messages: list[str] = []

    async def capture_comment(mr_id: str, message: str) -> None:
        messages.append(message)

    monkeypatch.setattr(note.gitlab, "post_comment", capture_comment)

    asyncio.run(note.handle(_note_payload("/ai approve R1")))

    assert messages == ["⚠️ エラー：R1 の修正パッチハッシュが一致しません"]
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_unresolved_discussions_do_not_enqueue(
    isolated_database, monkeypatch
) -> None:
    async def unresolved(project_id: str, mr_id: str) -> bool:
        return False

    monkeypatch.setattr(mr_updated.gitlab, "all_discussions_resolved", unresolved)
    payload = {
        "project": {"id": 42},
        "object_attributes": {"iid": 7},
    }

    asyncio.run(mr_updated.handle(payload))

    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_review_and_non_command_comments_are_noops(
    isolated_database, monkeypatch
) -> None:
    messages: list[str] = []

    async def capture_comment(mr_id: str, message: str) -> None:
        messages.append(message)

    monkeypatch.setattr(note.gitlab, "post_comment", capture_comment)

    asyncio.run(note.handle(_note_payload("/review 確認してください")))
    asyncio.run(note.handle(_note_payload("普通のコメント")))

    assert messages == []
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0


def test_non_merge_request_note_is_ignored(
    isolated_database, monkeypatch
) -> None:
    messages: list[str] = []

    async def capture_comment(mr_id: str, message: str) -> None:
        messages.append(message)

    monkeypatch.setattr(note.gitlab, "post_comment", capture_comment)
    payload = _note_payload("/ai test")
    payload["object_attributes"]["noteable_type"] = "Issue"

    asyncio.run(note.handle(payload))

    assert messages == []
    assert isolated_database.query_scalar("SELECT COUNT(*) FROM job_queue") == 0
