from subprocess import CompletedProcess

from Src.agent import context


def test_initial_review_uses_normal_target_branch_diff(monkeypatch, tmp_path) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, stdout="diff", stderr="")

    monkeypatch.setattr(context.subprocess, "run", run)

    assert context.build_diff_context([], "REVIEW", str(tmp_path), "main") == "diff"
    assert calls == [
        ["git", "diff", "--unified=3", "origin/main...HEAD", "--"]
    ]


def test_subsequent_review_diffs_from_checkpoint(monkeypatch, tmp_path) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, stdout="diff", stderr="")

    monkeypatch.setattr(context.subprocess, "run", run)

    context.build_diff_context(
        ["lib/example.dart"],
        "RE_REVIEW",
        str(tmp_path),
        "main",
        base_commit="abc123",
    )

    assert calls == [
        [
            "git",
            "diff",
            "--unified=3",
            "abc123",
            "HEAD",
            "--",
            "lib/example.dart",
        ]
    ]
