from .client import project_path, request


async def all_discussions_resolved(project_id: str, mr_id: str) -> bool:
    page = 1
    while True:
        response = await request(
            "GET",
            f"projects/{project_path(project_id)}/merge_requests/{mr_id}/discussions",
            params={"per_page": 100, "page": page},
        )
        discussions = response.json()
        for discussion in discussions:
            for note in discussion.get("notes", []):
                if note.get("resolvable") and not note.get("resolved", False):
                    return False
        next_page = response.headers.get("x-next-page")
        if not next_page:
            return True
        page = int(next_page)
