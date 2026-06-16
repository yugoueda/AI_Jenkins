import hashlib
import json
import logging

from .parser import parse_and_save_review, parse_and_save_unit_tests, parse_fix_diff
from .prompts import fix as fix_prompt
from .prompts import review as review_prompt
from .prompts import unit_test as unit_test_prompt
from .runner import run_agent
from ..db.Src import database as db


async def dispatch(job: dict) -> None:
    event_type = job["event_type"]
    payload = json.loads(job["payload"])
    mr_id = job["mr_id"]

    if event_type in ("REVIEW", "RE_REVIEW"):
        changed_files = payload.get("changed_files", [])
        prompt = review_prompt.build_review_prompt_with_ci(
            mr_id,
            changed_files,
            build_result=payload.get("build_result"),
            lint_result=payload.get("lint_result"),
        )
        returncode, output = await run_agent(prompt, event_type)
        if returncode == 0:
            parse_and_save_review(mr_id, output)
        else:
            await _handle_failure(mr_id, event_type, output)
        return

    if event_type == "APPROVE":
        finding_id = payload["finding_id"]
        prompt = fix_prompt.build_fix_prompt(finding_id)
        returncode, output = await run_agent(prompt, event_type)
        if returncode == 0:
            diff = parse_fix_diff(output)
            row = db.query_one(
                "SELECT fix_patch_sha256 FROM findings WHERE id=:finding_id",
                {"finding_id": finding_id},
            )
            expected_hash = row["fix_patch_sha256"] if row else None
            actual_hash = hashlib.sha256(diff.encode()).hexdigest()
            if expected_hash != actual_hash:
                await _handle_failure(mr_id, event_type, "fix_patch sha256 mismatch")
                return
            db.execute(
                "UPDATE findings SET status='APPLIED', updated_at=CURRENT_TIMESTAMP "
                "WHERE id=:finding_id",
                {"finding_id": finding_id},
            )
        else:
            await _handle_failure(mr_id, event_type, output)
        return

    if event_type == "UNIT_TEST_GEN":
        changed_files = payload.get("changed_files", [])
        uncovered_lines = payload.get("uncovered_lines", {})
        prompt = unit_test_prompt.build_unit_test_prompt(mr_id, changed_files, uncovered_lines)
        returncode, output = await run_agent(prompt, event_type)
        if returncode == 0:
            parse_and_save_unit_tests(mr_id, output)
        else:
            await _handle_failure(mr_id, event_type, output)
        return

    raise ValueError(f"unsupported event_type: {event_type}")


async def _handle_failure(mr_id: str, event_type: str, error_output: str) -> None:
    logging.error("[%s] mr=%s error=%s", event_type, mr_id, error_output[:500])
