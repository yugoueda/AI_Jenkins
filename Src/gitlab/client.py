import os
from typing import Any
from urllib.parse import quote

import httpx


class GitLabError(RuntimeError):
    pass


def project_path(project_id: str) -> str:
    return quote(str(project_id), safe="")


async def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
    expected_statuses: tuple[int, ...] = (200,),
) -> httpx.Response:
    base_url = os.getenv("GITLAB_URL", "").rstrip("/")
    token = os.getenv("GITLAB_TOKEN", "")
    if not base_url or not token:
        raise GitLabError("GITLAB_URL and GITLAB_TOKEN must be configured")

    timeout = float(os.getenv("GITLAB_API_TIMEOUT_SECONDS", "15"))
    url = f"{base_url}/api/v4/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                headers={"PRIVATE-TOKEN": token},
                params=params,
                json=json,
            )
    except httpx.HTTPError as exc:
        raise GitLabError(f"GitLab API request failed: {exc}") from exc

    if response.status_code not in expected_statuses:
        detail = response.text.strip()[:500]
        raise GitLabError(
            f"GitLab API {method.upper()} {path} returned "
            f"{response.status_code}: {detail}"
        )
    return response
