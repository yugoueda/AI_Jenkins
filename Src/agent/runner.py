import asyncio
import os
from pathlib import Path


DEFAULT_MODEL = "sonnet"


def _model_for(event_type: str) -> str:
    event_override = os.getenv(f"CLAUDE_MODEL_{event_type}")
    return event_override or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)


async def _run_once(
    prompt: str,
    event_type: str,
    working_directory: str | None,
) -> tuple[int, str]:
    cli_path = os.getenv("CLAUDE_CLI_PATH", "claude")
    timeout_seconds = float(os.getenv("AGENT_TIMEOUT_SECONDS", "600"))
    max_turns = os.getenv("CLAUDE_MAX_TURNS", "3")
    command = [
        cli_path,
        "--print",
        "--model",
        _model_for(event_type),
        "--max-turns",
        max_turns,
    ]
    cwd = None
    if working_directory:
        cwd_path = Path(working_directory).resolve()
        if not cwd_path.is_dir():
            return 2, f"Working directory not found: {cwd_path}"
        cwd = str(cwd_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "DISABLE_AUTOUPDATER": "1"},
            cwd=cwd,
        )
    except FileNotFoundError:
        return 127, f"Claude CLI not found: {cli_path}"

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return 124, f"Claude CLI timed out after {timeout_seconds:g} seconds"

    output = stdout.decode(errors="replace")
    if proc.returncode != 0:
        error = stderr.decode(errors="replace").strip()
        return proc.returncode or 1, error or output or "Claude CLI failed without output"

    max_output_bytes = int(os.getenv("AGENT_MAX_OUTPUT_BYTES", str(5 * 1024 * 1024)))
    if len(stdout) > max_output_bytes:
        return 1, f"Claude CLI output exceeded {max_output_bytes} bytes"
    if not output.strip():
        return 1, "Claude CLI returned empty output"
    return 0, output


async def run_agent(
    prompt: str,
    event_type: str = "REVIEW",
    working_directory: str | None = None,
) -> tuple[int, str]:
    attempts = max(1, int(os.getenv("AGENT_MAX_ATTEMPTS", "2")))
    last_result = (1, "Claude CLI was not executed")
    for attempt in range(1, attempts + 1):
        last_result = await _run_once(prompt, event_type, working_directory)
        if last_result[0] == 0 or attempt == attempts:
            return last_result
        await asyncio.sleep(min(attempt, 3))
    return last_result
