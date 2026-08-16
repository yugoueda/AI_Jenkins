import asyncio
import hashlib
import json
from pathlib import Path

from Src.agent import dispatcher


def _job(event_type: str, payload: dict | None = None) -> dict:
    return {
        "event_type": event_type,
        "mr_id": "7",
        "payload": json.dumps(
            {
                "project_id": "42",
                "source_branch": "feature/example",
                "target_branch": "main",
                "repository_url": "https://gitlab.example/repo.git",
                **(payload or {}),
            }
        ),
    }


def _insert_finding(database, patch: str = "patch") -> None:
    database.execute(
        "INSERT INTO findings "
        "(id, mr_id, source, status, fix_patch, fix_patch_sha256) "
        "VALUES ('R1', '7', 'AI', 'OPEN', :patch, :patch_hash)",
        {
            "patch": patch,
            "patch_hash": hashlib.sha256(patch.encode()).hexdigest(),
        },
    )


def _use_workspace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        dispatcher,
        "prepare_workspace",
        lambda payload, mr_id: str(tmp_path),
    )


def test_apply_posts_saved_patch(isolated_database, monkeypatch, tmp_path) -> None:
    _insert_finding(isolated_database)
    _use_workspace(monkeypatch, tmp_path)
    messages = []

    async def capture(project_id, mr_id, message):
        messages.append(message)

    monkeypatch.setattr(dispatcher.gitlab_comments, "post_comment", capture)

    asyncio.run(dispatcher.dispatch(_job("APPLY", {"finding_id": "R1"})))

    assert "```diff\npatch\n```" in messages[0]


def test_approve_commits_patch_and_updates_status(
    isolated_database, monkeypatch, tmp_path
) -> None:
    patch = "--- a/a\n+++ b/a\n"
    _insert_finding(isolated_database, patch)
    _use_workspace(monkeypatch, tmp_path)
    calls = []
    builds = []

    async def commit(*args):
        calls.append(args)
        return "new-sha"

    async def schedule(**kwargs):
        builds.append(kwargs)
        return "STARTED"

    async def comment(*args):
        return None

    monkeypatch.setattr(dispatcher, "commit_patch", commit)
    monkeypatch.setattr(dispatcher, "schedule_build", schedule)
    monkeypatch.setattr(dispatcher.gitlab_comments, "post_comment", comment)

    asyncio.run(dispatcher.dispatch(_job("APPROVE", {"finding_id": "R1"})))

    assert calls[0][:4] == ("42", "feature/example", "R1", patch)
    assert isolated_database.query_scalar(
        "SELECT status FROM findings WHERE id='R1'"
    ) == "APPLIED"
    assert builds[0]["commit_sha"] == "new-sha"
    assert builds[0]["review_event_type"] == "RE_REVIEW"


def test_approve_posts_patch_failure(
    isolated_database, monkeypatch, tmp_path
) -> None:
    _insert_finding(isolated_database, "invalid patch")
    _use_workspace(monkeypatch, tmp_path)
    messages = []

    async def fail_commit(*args):
        raise dispatcher.PatchError("git apply --check failed")

    async def capture(project_id, mr_id, message):
        messages.append(message)

    monkeypatch.setattr(dispatcher, "commit_patch", fail_commit)
    monkeypatch.setattr(dispatcher.gitlab_comments, "post_comment", capture)

    try:
        asyncio.run(dispatcher.dispatch(_job("APPROVE", {"finding_id": "R1"})))
    except dispatcher.AgentExecutionError:
        pass
    else:
        raise AssertionError("patch failure did not fail the job")

    assert messages == [
        "⚠️ APPROVE ジョブに失敗しました: git apply --check failed"
    ]


def test_clean_re_review_enqueues_unit_test_generation(
    isolated_database, monkeypatch, tmp_path
) -> None:
    _use_workspace(monkeypatch, tmp_path)

    async def run_agent(*args):
        return 0, '{"findings": []}'

    async def post_review(*args):
        return None

    monkeypatch.setattr(dispatcher, "run_agent", run_agent)
    monkeypatch.setattr(
        dispatcher.review_prompt,
        "build_review_prompt_with_ci",
        lambda *args, **kwargs: "prompt",
    )
    monkeypatch.setattr(
        dispatcher.gitlab_comments,
        "post_review_findings",
        post_review,
    )

    asyncio.run(dispatcher.dispatch(_job("RE_REVIEW")))

    assert isolated_database.query_scalar(
        "SELECT event_type FROM job_queue"
    ) == "UNIT_TEST_GEN"


def test_review_uses_and_advances_successful_checkpoint(
    isolated_database, monkeypatch, tmp_path
) -> None:
    _use_workspace(monkeypatch, tmp_path)
    dispatcher.save_review_checkpoint("42", "7", "old-sha")
    prompt_calls = []

    async def run_agent(*args):
        return 0, '{"findings": []}'

    async def post_review(*args):
        return None

    def build_prompt(*args, **kwargs):
        prompt_calls.append(kwargs)
        return "prompt"

    monkeypatch.setattr(dispatcher, "run_agent", run_agent)
    monkeypatch.setattr(
        dispatcher.review_prompt,
        "build_review_prompt_with_ci",
        build_prompt,
    )
    monkeypatch.setattr(
        dispatcher.gitlab_comments,
        "post_review_findings",
        post_review,
    )

    asyncio.run(
        dispatcher.dispatch(
            _job("REVIEW", {"commit_sha": "new-sha"})
        )
    )

    assert prompt_calls[0]["base_commit"] == "old-sha"
    assert dispatcher.get_review_checkpoint("42", "7") == "new-sha"


def test_failed_review_does_not_advance_checkpoint(
    isolated_database, monkeypatch, tmp_path
) -> None:
    _use_workspace(monkeypatch, tmp_path)
    dispatcher.save_review_checkpoint("42", "7", "old-sha")

    async def run_agent(*args):
        return 0, "not json"

    async def comment(*args):
        return None

    monkeypatch.setattr(dispatcher, "run_agent", run_agent)
    monkeypatch.setattr(
        dispatcher.review_prompt,
        "build_review_prompt_with_ci",
        lambda *args, **kwargs: "prompt",
    )
    monkeypatch.setattr(dispatcher.gitlab_comments, "post_comment", comment)

    try:
        asyncio.run(
            dispatcher.dispatch(
                _job("REVIEW", {"commit_sha": "failed-sha"})
            )
        )
    except dispatcher.AgentExecutionError:
        pass
    else:
        raise AssertionError("invalid review did not fail")

    assert dispatcher.get_review_checkpoint("42", "7") == "old-sha"


def test_unit_test_generation_commits_and_starts_jenkins(
    isolated_database, monkeypatch, tmp_path
) -> None:
    _use_workspace(monkeypatch, tmp_path)
    commits = []
    triggers = []

    async def run_agent(*args):
        return 0, "// test/example_test.dart\nvoid main() {}"

    async def commit(project_id, branch, files):
        commits.append((project_id, branch, files))

    async def trigger(**kwargs):
        triggers.append(kwargs)

    monkeypatch.setattr(dispatcher, "run_agent", run_agent)
    monkeypatch.setattr(
        dispatcher.unit_test_prompt,
        "build_unit_test_prompt",
        lambda *args, **kwargs: "prompt",
    )
    monkeypatch.setattr(dispatcher, "commit_generated_files", commit)
    monkeypatch.setattr(dispatcher, "trigger_test", trigger)

    asyncio.run(dispatcher.dispatch(_job("UNIT_TEST_GEN")))

    assert commits == [
        (
            "42",
            "feature/example",
            [("test/example_test.dart", "void main() {}")],
        )
    ]
    assert triggers[0]["repository_url"] == "https://gitlab.example/repo.git"
