import os
from urllib.parse import quote

import httpx


class JenkinsError(RuntimeError):
    pass


def _job_path(job_name: str) -> str:
    parts = [part for part in job_name.split("/") if part]
    if not parts:
        raise JenkinsError("Jenkins job name is not configured")
    return "/".join(f"job/{quote(part, safe='')}" for part in parts)


async def trigger_job(job_name: str, parameters: dict[str, str]) -> str | None:
    base_url = os.getenv("JENKINS_URL", "").rstrip("/")
    user = os.getenv("JENKINS_USER", "")
    token = os.getenv("JENKINS_TOKEN", "")
    if not base_url or not user or not token:
        raise JenkinsError(
            "JENKINS_URL, JENKINS_USER and JENKINS_TOKEN must be configured"
        )

    timeout = float(os.getenv("JENKINS_API_TIMEOUT_SECONDS", "15"))
    auth = (user, token)
    headers: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=timeout, auth=auth) as client:
            crumb = await client.get(f"{base_url}/crumbIssuer/api/json")
            if crumb.status_code == 200:
                crumb_data = crumb.json()
                headers[crumb_data["crumbRequestField"]] = crumb_data["crumb"]
            elif crumb.status_code not in (404,):
                raise JenkinsError(
                    f"Jenkins crumb request returned {crumb.status_code}: "
                    f"{crumb.text[:500]}"
                )

            response = await client.post(
                f"{base_url}/{_job_path(job_name)}/buildWithParameters",
                params=parameters,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise JenkinsError(f"Jenkins API request failed: {exc}") from exc

    if response.status_code not in (200, 201, 202):
        raise JenkinsError(
            f"Jenkins build request returned {response.status_code}: "
            f"{response.text[:500]}"
        )
    return response.headers.get("Location")


async def trigger_build(
    *,
    project_id: str,
    mr_id: str,
    source_branch: str,
    target_branch: str,
    commit_sha: str,
    repository_url: str = "",
) -> str | None:
    return await trigger_job(
        os.getenv("JENKINS_BUILD_JOB", "ai-review-build"),
        {
            "PROJECT_ID": project_id,
            "MR_IID": mr_id,
            "SOURCE_BRANCH": source_branch,
            "TARGET_BRANCH": target_branch,
            "COMMIT_SHA": commit_sha,
            "REPOSITORY_URL": repository_url,
        },
    )


async def trigger_test(
    *,
    project_id: str,
    mr_id: str,
    source_branch: str,
    repository_url: str = "",
) -> str | None:
    return await trigger_job(
        os.getenv("JENKINS_TEST_JOB", "ai-review-test"),
        {
            "PROJECT_ID": project_id,
            "MR_IID": mr_id,
            "SOURCE_BRANCH": source_branch,
            "REPOSITORY_URL": repository_url,
            "C0_TARGET": os.getenv("COVERAGE_C0_TARGET", "80"),
            "C1_TARGET": os.getenv("COVERAGE_C1_TARGET", "70"),
        },
    )
