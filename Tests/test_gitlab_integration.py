import asyncio
from pathlib import Path

import httpx

from Src.gitlab.comments import (
    format_ai_review_usage_comment,
    format_build_failure_comment,
    format_review_comment,
)
from Src.gitlab.commits import PatchError, commit_patch
from Src.gitlab.discussions import all_discussions_resolved


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
    assert "/ai approve R1" in comment


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
