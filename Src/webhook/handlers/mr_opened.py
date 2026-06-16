from ..queue import enqueue


async def handle(payload: dict) -> None:
    attrs = payload["object_attributes"]
    mr_id = str(attrs["iid"])
    project_id = str(payload["project"]["id"])
    enqueue(
        mr_id,
        "REVIEW",
        {
            "project_id": project_id,
            "source_branch": attrs.get("source_branch"),
            "target_branch": attrs.get("target_branch"),
            "changed_files": [],
            "build_result": payload.get("build_result"),
            "lint_result": payload.get("lint_result"),
        },
    )
