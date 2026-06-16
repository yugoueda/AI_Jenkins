import re
from dataclasses import dataclass
from typing import Literal


REVIEW_PATTERN = re.compile(
    r"^/review\s+(?P<content>.+?)(?:\nfile:\s*(?P<file>.+?))?(?:\nline:\s*(?P<line>\d+))?$",
    re.DOTALL,
)
AI_PATTERN = re.compile(
    r"^/ai\s+(?P<cmd>approve|reject|test)(?:\s+(?P<id>\w+))?$",
)


@dataclass(frozen=True)
class ReviewCommand:
    content: str
    file: str | None
    line: int | None


@dataclass(frozen=True)
class AiCommand:
    cmd: Literal["approve", "reject", "test"]
    finding_id: str | None


def parse(body: str) -> ReviewCommand | AiCommand | None:
    body = body.strip()
    if match := REVIEW_PATTERN.match(body):
        line = int(match.group("line")) if match.group("line") else None
        return ReviewCommand(
            content=match.group("content").strip(),
            file=match.group("file"),
            line=line,
        )
    if match := AI_PATTERN.match(body):
        return AiCommand(cmd=match.group("cmd"), finding_id=match.group("id"))
    return None
