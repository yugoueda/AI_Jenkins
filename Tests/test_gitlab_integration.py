import asyncio
from pathlib import Path

import httpx

from Src.gitlab.comments import (
    format_ai_review_usage_comment,
    format_build_failure_comment,
    format_review_comment,
    post_review_findings,
)
from Src.gitlab.client import GitLabError
from Src.gitlab.commits import PatchApplyError, PatchError, commit_patch, patch_paths
from Src.gitlab.discussions import all_discussions_resolved
from Src.db.Src import database as db


def test_ai_review_usage_comment_lists_supported_commands() -> None:
    comment = format_ai_review_usage_comment()

    assert "## AIレビューの使い方" in comment
    assert "`/ai review`" in comment
    assert "`/ai test`" in comment
    assert "`/ai apply <指摘ID>`" in comment
    assert "`/ai approve <指摘ID>`" in comment
    assert "`/ai reject <指摘ID>`" in comment
    assert "Developer以上" in comment


def test_build_failure_comment_explains_follow_up() -> None:
    comment = format_build_failure_comment()

    assert "## ❌ ビルドに失敗しました" in comment
    assert "AIが原因と修正案を解析しています" in comment


def test_review_comment_contains_finding_details() -> None:
    comment = format_review_comment(
        [
            {
                "id": "R1",
                "file_path": "lib/order.dart",
                "line_start": 10,
                "line_end": 12,
                "description": "null checkがありません",
                "suggestion": None,
                "fix_patch": "-old\n+new",
            }
        ]
    )

    assert "## AI レビュー結果" in comment
    assert "### R1" in comment
    assert "`lib/order.dart` L10-12" in comment
    assert comment.count("null checkがありません") == 1
    assert "/ai approve R1" in comment


def test_review_findings_are_posted_as_inline_discussions(
    isolated_database, monkeypatch
) -> None:
    db.execute(
        "INSERT INTO findings "
        "(id, mr_id, source, status, file_path, line_start, line_end, description, "
        "created_at, updated_at) VALUES "
        "('R1', '7', 'AI', 'OPEN', 'lib/order.dart', 10, 12, 'null check', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    requests = []

    async def fake_request(method, path, **kwargs):
        requests.append((method, path, kwargs))
        if method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "base_commit_sha": "base",
                        "head_commit_sha": "head",
                        "start_commit_sha": "start",
                    }
                ],
            )
        return httpx.Response(201, json={})

    monkeypatch.setattr("Src.gitlab.comments.request", fake_request)

    asyncio.run(post_review_findings("42", "7", ["R1"]))

    assert requests[1][1].endswith("/merge_requests/7/discussions")
    assert requests[1][2]["json"]["position"] == {
        "position_type": "text",
        "base_sha": "base",
        "head_sha": "head",
        "start_sha": "start",
        "new_path": "lib/order.dart",
        "new_line": 10,
    }
    assert "### R1" in requests[1][2]["json"]["body"]


def test_review_finding_falls_back_to_note_when_line_is_not_in_diff(
    isolated_database, monkeypatch
) -> None:
    db.execute(
        "INSERT INTO findings "
        "(id, mr_id, source, status, file_path, line_start, description, "
        "created_at, updated_at) VALUES "
        "('R1', '7', 'AI', 'OPEN', 'lib/order.dart', 10, 'null check', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    requests = []

    async def fake_request(method, path, **kwargs):
        requests.append((method, path, kwargs))
        if method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "base_commit_sha": "base",
                        "head_commit_sha": "head",
                        "start_commit_sha": "start",
                    }
                ],
            )
        if path.endswith("/discussions"):
            raise GitLabError("line is not part of the diff")
        return httpx.Response(201, json={})

    monkeypatch.setattr("Src.gitlab.comments.request", fake_request)

    asyncio.run(post_review_findings("42", "7", ["R1"]))

    assert requests[-1][1].endswith("/merge_requests/7/notes")
    assert "### R1" in requests[-1][2]["json"]["body"]


def test_discussions_require_every_resolvable_note_to_be_resolved(monkeypatch) -> None:
    async def fake_request(*args, **kwargs):
        return httpx.Response(
            200,
            json=[{"notes": [{"resolvable": True, "resolved": False}]}],
        )

    monkeypatch.setattr("Src.gitlab.discussions.request", fake_request)

    assert not asyncio.run(all_discussions_resolved("42", "7"))


def test_commit_patch_builds_gitlab_commit_and_restores_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    source = tmp_path / "example.txt"
    source.write_text("old\n")
    subprocess.run(["git", "add", "example.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
    )
    requests = []

    async def fake_request(method, path, **kwargs):
        requests.append((method, path, kwargs))
        return httpx.Response(201, json={})

    monkeypatch.setattr("Src.gitlab.commits.request", fake_request)
    patch = """diff --git a/example.txt b/example.txt
--- a/example.txt
+++ b/example.txt
@@ -1 +1 @@
-old
+new
"""

    asyncio.run(commit_patch("42", "feature", "R1", patch, str(tmp_path)))

    assert source.read_text() == "old\n"
    assert requests[0][2]["json"]["actions"] == [
        {"action": "update", "file_path": "example.txt", "content": "new\n"}
    ]


def test_commit_patch_repairs_incorrect_hunk_counts(
    tmp_path: Path, monkeypatch
) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    source = tmp_path / "example.txt"
    source.write_text("one\ntwo\nthree\n")
    subprocess.run(["git", "add", "example.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
    )
    requests = []

    async def fake_request(method, path, **kwargs):
        requests.append((method, path, kwargs))
        return httpx.Response(201, json={})

    monkeypatch.setattr("Src.gitlab.commits.request", fake_request)
    patch = """--- a/example.txt
+++ b/example.txt
@@ -1,99 +1,88 @@
 one
-two
+changed
 three
"""

    asyncio.run(commit_patch("42", "feature", "R1", patch, str(tmp_path)))

    assert source.read_text() == "one\ntwo\nthree\n"
    assert requests[0][2]["json"]["actions"] == [
        {
            "action": "update",
            "file_path": "example.txt",
            "content": "one\nchanged\nthree\n",
        }
    ]


def test_commit_patch_accepts_multiple_files_without_diff_git_headers(
    tmp_path: Path, monkeypatch
) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("old first\n")
    second.write_text("old second\n")
    subprocess.run(["git", "add", "first.txt", "second.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
    )
    requests = []

    async def fake_request(method, path, **kwargs):
        requests.append((method, path, kwargs))
        return httpx.Response(201, json={})

    monkeypatch.setattr("Src.gitlab.commits.request", fake_request)
    patch = """--- a/first.txt
+++ b/first.txt
@@ -1 +1 @@
-old first
+new first
--- a/second.txt
+++ b/second.txt
@@ -1 +1 @@
-old second
+new second
"""

    asyncio.run(commit_patch("42", "feature", "R1", patch, str(tmp_path)))

    assert requests[0][2]["json"]["actions"] == [
        {"action": "update", "file_path": "first.txt", "content": "new first\n"},
        {"action": "update", "file_path": "second.txt", "content": "new second\n"},
    ]


def test_commit_patch_rejects_unsafe_paths(tmp_path: Path) -> None:
    patch = """--- a/../secret
+++ b/../secret
@@ -1 +1 @@
-old
+new
"""
    try:
        asyncio.run(commit_patch("42", "feature", "R1", patch, str(tmp_path)))
    except PatchError as exc:
        assert "unsafe path" in str(exc)
    else:
        raise AssertionError("unsafe patch was accepted")


def test_commit_patch_marks_context_mismatch_as_recoverable(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    source = tmp_path / "example.txt"
    source.write_text("current\n")
    subprocess.run(["git", "add", "example.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
    )
    patch = "--- a/example.txt\n+++ b/example.txt\n@@ -1 +1 @@\n-old\n+new\n"

    try:
        asyncio.run(commit_patch("42", "feature", "R1", patch, str(tmp_path)))
    except PatchApplyError:
        pass
    else:
        raise AssertionError("stale patch was not identified")


def test_patch_paths_rejects_unsafe_paths() -> None:
    patch = "--- a/../secret\n+++ b/../secret\n@@ -1 +1 @@\n-old\n+new\n"

    try:
        patch_paths(patch)
    except PatchError:
        pass
    else:
        raise AssertionError("unsafe path was accepted")


def test_commit_patch_accepts_metadata_only_delete(
    tmp_path: Path, monkeypatch
) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    ignore = tmp_path / ".gitignore"
    generated = tmp_path / "generated.txt"
    ignore.write_text("cache\n")
    generated.write_text("large generated content\n")
    subprocess.run(["git", "add", ".gitignore", "generated.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
    )
    requests = []

    async def fake_request(method, path, **kwargs):
        requests.append((method, path, kwargs))
        return httpx.Response(201, json={})

    monkeypatch.setattr("Src.gitlab.commits.request", fake_request)
    patch = """diff --git a/.gitignore b/.gitignore
--- a/.gitignore
+++ b/.gitignore
@@ -1 +1,2 @@
 cache
+generated.txt
diff --git a/generated.txt b/generated.txt
deleted file mode 100644
--- a/generated.txt
+++ /dev/null
@@ -1 +0,0 @@
-(generated content omitted)
"""

    asyncio.run(commit_patch("42", "feature", "R1", patch, str(tmp_path)))

    assert ignore.read_text() == "cache\n"
    assert generated.read_text() == "large generated content\n"
    assert requests[0][2]["json"]["actions"] == [
        {
            "action": "update",
            "file_path": ".gitignore",
            "content": "cache\ngenerated.txt\n",
        },
        {"action": "delete", "file_path": "generated.txt"},
    ]
