import asyncio
import os


DEFAULT_MODEL = "claude-sonnet-4-5"

MODEL_MAP: dict[str, str] = {
    "REVIEW": DEFAULT_MODEL,
    "APPROVE": DEFAULT_MODEL,
    "RE_REVIEW": DEFAULT_MODEL,
    "UNIT_TEST_GEN": DEFAULT_MODEL,
}


async def run_agent(prompt: str, event_type: str = "REVIEW") -> tuple[int, str]:
    model = MODEL_MAP.get(event_type, DEFAULT_MODEL)
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "--model",
        model,
        "--print",
        "--prompt",
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ},
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode(errors="replace")
    if proc.returncode != 0 and stderr:
        output = stderr.decode(errors="replace")
    return proc.returncode or 0, output
