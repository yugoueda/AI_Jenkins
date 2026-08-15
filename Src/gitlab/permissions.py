from .client import project_path, request


DEVELOPER_ACCESS_LEVEL = 30


async def user_can_operate(project_id: str, user_id: str) -> bool:
    response = await request(
        "GET",
        f"projects/{project_path(project_id)}/members/all/{user_id}",
        expected_statuses=(200, 404),
    )
    if response.status_code == 404:
        return False
    return int(response.json().get("access_level", 0)) >= DEVELOPER_ACCESS_LEVEL
