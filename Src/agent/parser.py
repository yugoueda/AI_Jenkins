import hashlib
import json
import re

from ..db.Src import database as db


def _extract_json(raw_output: str) -> dict:
    output = raw_output.strip()
    decoder = json.JSONDecoder()

    # Prefer fenced blocks because agents sometimes add a short explanation
    # before an otherwise valid ```json response despite the prompt.
    candidates = [
        match.group("content").strip()
        for match in re.finditer(
            r"```(?:json)?\s*\r?\n(?P<content>.*?)```",
            output,
            flags=re.DOTALL | re.IGNORECASE,
        )
    ]
    candidates.append(output)

    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        # raw_decode lets us recover a JSON object surrounded by prose while
        # still parsing strings and nested braces according to JSON syntax.
        for match in re.finditer(r"\{", candidate):
            try:
                data, _ = decoder.raw_decode(candidate, match.start())
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if isinstance(data, dict) and isinstance(data.get("findings"), list):
                return data

    detail = f": {last_error}" if last_error else ""
    raise ValueError(f"agent returned invalid review JSON{detail}")


def parse_and_save_review(mr_id: str, raw_output: str) -> list[str]:
    data = _extract_json(raw_output)
    saved_ids: list[str] = []
    max_n = db.query_scalar(
        "SELECT COALESCE(MAX(CAST(SUBSTR(id, 2) AS INTEGER)), 0) "
        "FROM findings WHERE source='AI'",
    )

    for i, finding in enumerate(data.get("findings", []), start=1):
        finding_id = f"R{int(max_n or 0) + i}"
        fix_patch = finding.get("fix_patch")
        fix_patch_sha256 = (
            hashlib.sha256(fix_patch.encode()).hexdigest() if fix_patch else None
        )
        db.execute(
            "INSERT INTO findings "
            "(id, mr_id, source, status, file_path, line_start, line_end, "
            "description, suggestion, fix_patch, fix_patch_sha256, created_at, updated_at) "
            "VALUES (:id, :mr_id, 'AI', 'OPEN', :file_path, :line_start, :line_end, "
            ":description, :suggestion, :fix_patch, :fix_patch_sha256, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            {
                "id": finding_id,
                "mr_id": mr_id,
                "file_path": finding.get("file"),
                "line_start": finding.get("line_start"),
                "line_end": finding.get("line_end"),
                "description": finding.get("description"),
                "suggestion": json.dumps(finding.get("suggestion"), ensure_ascii=False),
                "fix_patch": fix_patch,
                "fix_patch_sha256": fix_patch_sha256,
            },
        )
        saved_ids.append(finding_id)

    return saved_ids


def parse_fix_diff(raw_output: str) -> str:
    return raw_output.strip()


def parse_and_save_unit_tests(mr_id: str, raw_output: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    # Agents occasionally wrap each generated file in its own Markdown code
    # block even when the prompt explicitly forbids it.  Strip fence-only
    # lines before finding file markers so that the opening fence for the next
    # file cannot leak into the previous Dart source.
    normalized_output = re.sub(
        r"^[ \t]*```(?:dart)?[ \t]*\r?\n?",
        "",
        raw_output,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    markers = list(
        re.finditer(
            r"^// (test/[^\r\n]+)\r?$",
            normalized_output,
            flags=re.MULTILINE,
        )
    )
    for index, marker in enumerate(markers):
        file_path = marker.group(1).strip()
        end = (
            markers[index + 1].start()
            if index + 1 < len(markers)
            else len(normalized_output)
        )
        content = normalized_output[marker.end() : end].strip()
        if not content:
            continue
        results.append((file_path, content))
    return results
