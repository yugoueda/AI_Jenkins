import asyncio
from pathlib import Path

from Src.agent.runner import run_agent


FAKE_CLI = Path(__file__).parent / "fixtures" / "fake_claude.py"


def test_run_agent_passes_prompt_over_stdin(monkeypatch, tmp_path: Path) -> None:
    capture = tmp_path / "capture.txt"
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(FAKE_CLI))
    monkeypatch.setenv("FAKE_CLAUDE_CAPTURE", str(capture))
    monkeypatch.setenv("AGENT_MAX_ATTEMPTS", "1")

    returncode, output = asyncio.run(
        run_agent("secret source code", "REVIEW", str(tmp_path))
    )

    assert returncode == 0
    assert output.strip() == '{"findings":[]}'
    captured = capture.read_text()
    assert captured.startswith("secret source code\n")
    assert "secret source code" not in captured.partition("ARGS=")[2]
    assert "--print" in captured
    assert "--model sonnet" in captured


def test_run_agent_reports_missing_cli(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(tmp_path / "missing-claude"))
    monkeypatch.setenv("AGENT_MAX_ATTEMPTS", "1")

    returncode, output = asyncio.run(run_agent("prompt", working_directory=str(tmp_path)))

    assert returncode == 127
    assert "not found" in output


def test_run_agent_reports_missing_working_directory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(FAKE_CLI))
    monkeypatch.setenv("AGENT_MAX_ATTEMPTS", "1")

    missing = tmp_path / "missing-workspace"
    returncode, output = asyncio.run(
        run_agent("prompt", working_directory=str(missing))
    )

    assert returncode == 2
    assert "Working directory not found" in output


def test_run_agent_times_out(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(FAKE_CLI))
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "timeout")
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "0.05")
    monkeypatch.setenv("AGENT_MAX_ATTEMPTS", "1")

    returncode, output = asyncio.run(run_agent("prompt", working_directory=str(tmp_path)))

    assert returncode == 124
    assert "timed out" in output


def test_run_agent_rejects_large_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(FAKE_CLI))
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "large")
    monkeypatch.setenv("AGENT_MAX_OUTPUT_BYTES", "100")
    monkeypatch.setenv("AGENT_MAX_ATTEMPTS", "1")

    returncode, output = asyncio.run(run_agent("prompt", working_directory=str(tmp_path)))

    assert returncode == 1
    assert "exceeded" in output
