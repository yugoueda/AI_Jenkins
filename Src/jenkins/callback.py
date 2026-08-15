import hmac
import os
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..gitlab.comments import post_comment
from ..webhook.queue import enqueue


router = APIRouter(prefix="/internal/jenkins", tags=["jenkins"])


class JenkinsResult(BaseModel):
    pipeline: Literal["BUILD", "TEST"]
    project_id: str
    mr_id: str
    source_branch: str
    target_branch: str | None = None
    commit_sha: str | None = None
    repository_url: str | None = None
    build_result: str | None = None
    build_log: str | None = None
    lint_result: str | None = None
    lint_log: str | None = None
    test_result: str | None = None
    test_log: str | None = None
    c0: float | None = Field(default=None, ge=0, le=100)
    c1: float | None = Field(default=None, ge=0, le=100)


def _verify_callback_token(token: str) -> None:
    expected = os.getenv("JENKINS_CALLBACK_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="Jenkins callback token is not configured",
        )
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid Jenkins callback token")


@router.post("/result", status_code=202)
async def receive_result(
    result: JenkinsResult,
    x_internal_token: str = Header(...),
) -> dict[str, str]:
    _verify_callback_token(x_internal_token)

    if result.pipeline == "BUILD":
        build_result = (result.build_result or "UNKNOWN").upper()
        lint_result = (result.lint_result or "NOT_RUN").upper()
        payload = {
            "project_id": result.project_id,
            "source_branch": result.source_branch,
            "target_branch": result.target_branch,
            "commit_sha": result.commit_sha,
            "repository_url": result.repository_url,
            "changed_files": [],
            "build_result": build_result,
            "build_log": (result.build_log or "")[-20_000:],
            "lint_result": lint_result,
            "lint_log": (result.lint_log or "")[-20_000:],
        }
        if build_result != "SUCCESS":
            enqueue(result.mr_id, "BUILD_FIX", payload)
            return {"status": "queued", "event_type": "BUILD_FIX"}
        if lint_result != "SUCCESS":
            await post_comment(
                result.project_id,
                result.mr_id,
                "⚠️ 静的解析に失敗しました。ログを確認し、必要であれば "
                "`/ai review` でレビューを開始してください。",
            )
            return {"status": "reported", "event_type": "LINT_FAILED"}
        enqueue(result.mr_id, "REVIEW", payload)
        return {"status": "queued", "event_type": "REVIEW"}

    test_result = (result.test_result or "UNKNOWN").upper()
    coverage = (
        f"C0: {result.c0:.1f}% / C1: {result.c1:.1f}%"
        if result.c0 is not None and result.c1 is not None
        else "カバレッジ: 取得できませんでした"
    )
    await post_comment(
        result.project_id,
        result.mr_id,
        f"## AI生成テスト結果\n\n- 実行結果: **{test_result}**\n- {coverage}"
        + (
            f"\n\n<details><summary>テストログ</summary>\n\n```text\n"
            f"{result.test_log[-10_000:]}\n```\n</details>"
            if result.test_log
            else ""
        ),
    )
    return {"status": "reported", "event_type": "TEST"}
