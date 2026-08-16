import json
import re
import hashlib

from ..db.Src import database as db


def _extract_json(raw_output: str) -> dict:
    output = raw_output.strip()
    if output.startswith("```"):
        _, _, output = output.partition("\n")
        if output.rstrip().endswith("```"):
            output = output.rstrip()[:-3].rstrip()
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"agent returned invalid review JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("findings", []), list):
        raise ValueError("agent review JSON must contain a findings array")
    return data


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
