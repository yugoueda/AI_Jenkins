import json
import re

from ..db.Src import database as db


def parse_and_save_review(mr_id: str, raw_output: str) -> list[str]:
    data = json.loads(raw_output)
    saved_ids: list[str] = []
    max_n = db.query_scalar(
        "SELECT COALESCE(MAX(CAST(SUBSTR(id, 2) AS INTEGER)), 0) "
        "FROM findings WHERE mr_id=:mr_id AND source='AI'",
        {"mr_id": mr_id},
    )

    for i, finding in enumerate(data.get("findings", []), start=1):
        finding_id = f"R{int(max_n or 0) + i}"
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
                "fix_patch": finding.get("fix_patch"),
                "fix_patch_sha256": finding.get("fix_patch_sha256"),
            },
        )
        saved_ids.append(finding_id)

    return saved_ids


def parse_fix_diff(raw_output: str) -> str:
    return raw_output.strip()


def parse_and_save_unit_tests(mr_id: str, raw_output: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    blocks = re.split(r"(?=^// test/)", raw_output, flags=re.MULTILINE)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        first_line, _, rest = block.partition("\n")
        file_path = first_line.removeprefix("// ").strip()
        results.append((file_path, rest.strip()))
    return results
