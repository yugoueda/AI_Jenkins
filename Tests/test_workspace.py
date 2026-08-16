from Src.agent import workspace


def test_prepare_workspace_fetches_fully_qualified_branch_refs(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    calls = []
    monkeypatch.setattr(workspace, "_run", lambda cwd, args: calls.append(args))

    result = workspace.prepare_workspace(
        {
            "repository_url": "https://gitlab.example.com/group/project.git",
            "project_id": "123",
            "source_branch": "develop",
            "target_branch": "main",
            "commit_sha": "abc123",
        },
        "7",
    )

    assert result == str(tmp_path / "123" / "7")
    assert calls[1] == [
        "fetch",
        "--prune",
        "origin",
        "+refs/heads/develop:refs/remotes/origin/develop",
        "+refs/heads/main:refs/remotes/origin/main",
    ]
    assert calls[2] == ["checkout", "-B", "develop", "abc123"]


def test_prepare_workspace_uses_source_tip_without_commit_sha(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    calls = []
    monkeypatch.setattr(workspace, "_run", lambda cwd, args: calls.append(args))

    workspace.prepare_workspace(
        {
            "repository_url": "https://gitlab.example.com/group/project.git",
            "project_id": "123",
            "source_branch": "develop",
            "target_branch": "main",
        },
        "7",
    )

    assert calls[2] == ["checkout", "-B", "develop", "origin/develop"]
