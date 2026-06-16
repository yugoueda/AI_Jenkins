from .. import gitlab_stub as gitlab
from ..queue import enqueue


async def handle(payload: dict) -> None:
    attrs = payload["object_attributes"]
    mr_id = str(attrs["iid"])
    project_id = str(payload["project"]["id"])
    if not await gitlab.all_discussions_resolved(project_id, mr_id):
        return
    enqueue(
        mr_id,
        "RE_REVIEW",
        {
            "project_id": project_id,
            "changed_files": [],
            "build_result": payload.get("build_result"),
            "lint_result": payload.get("lint_result"),
        },
    )
