import asyncio
import logging
import os
import time
from pathlib import Path


DEFAULT_MODEL = "sonnet"
logger = logging.getLogger(__name__)


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
    progress_interval = max(
        0.1,
        float(os.getenv("AGENT_PROGRESS_INTERVAL_SECONDS", "15")),
    )
    max_turns = os.getenv("CLAUDE_MAX_TURNS", "30")
    model = _model_for(event_type)
    command = [
        cli_path,
        "--print",
        "--model",
        model,
        "--max-turns",
        max_turns,
    ]
    if event_type in ("REVIEW", "RE_REVIEW", "UNIT_TEST_GEN"):
        command.extend(
            ["--disallowedTools", "Write", "Edit", "NotebookEdit"]
        )
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

    started_at = time.monotonic()
    logger.info(
        "Claude CLI started: event_type=%s model=%s max_turns=%s timeout_seconds=%g",
        event_type,
        model,
        max_turns,
        timeout_seconds,
    )
    communication = asyncio.create_task(proc.communicate(input=prompt.encode()))
    try:
        while True:
            elapsed = time.monotonic() - started_at
            remaining = timeout_seconds - elapsed
            if remaining <= 0:
                raise TimeoutError
            done, _ = await asyncio.wait(
                {communication},
                timeout=min(progress_interval, remaining),
            )
            if done:
                stdout, stderr = await communication
                break
            logger.info(
                "Claude CLI running: event_type=%s elapsed_seconds=%.1f",
                event_type,
                time.monotonic() - started_at,
            )
    except TimeoutError:
        proc.kill()
        await communication
        logger.error(
            "Claude CLI timed out: event_type=%s elapsed_seconds=%.1f",
            event_type,
            time.monotonic() - started_at,
        )
        return 124, f"Claude CLI timed out after {timeout_seconds:g} seconds"

    logger.info(
        "Claude CLI finished: event_type=%s exit_code=%s elapsed_seconds=%.1f "
        "stdout_bytes=%d stderr_bytes=%d",
        event_type,
        proc.returncode,
        time.monotonic() - started_at,
        len(stdout),
        len(stderr),
    )
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
        logger.info(
            "Claude CLI attempt: event_type=%s attempt=%d/%d",
            event_type,
            attempt,
            attempts,
        )
        last_result = await _run_once(prompt, event_type, working_directory)
        if last_result[0] == 0 or attempt == attempts:
            return last_result
        logger.warning(
            "Claude CLI retry scheduled: event_type=%s attempt=%d/%d exit_code=%d",
            event_type,
            attempt,
            attempts,
            last_result[0],
        )
        await asyncio.sleep(min(attempt, 3))
    return last_result
