from fastapi import APIRouter, Header, Request

from .handlers import mr_opened, mr_updated, note
from .signature import verify_signature


router = APIRouter()


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    x_gitlab_token: str = Header(...),
    x_gitlab_event: str = Header(...),
) -> dict[str, str]:
    verify_signature(x_gitlab_token)
    payload = await request.json()

    if x_gitlab_event == "Merge Request Hook":
        action = payload.get("object_attributes", {}).get("action")
        if action == "opened":
            await mr_opened.handle(payload)
        elif action == "update":
            changes = payload.get("changes", {})
            resolved = changes.get("blocking_discussions_resolved", {}).get("current")
            if resolved is True:
                await mr_updated.handle(payload)
    elif x_gitlab_event == "Note Hook":
        await note.handle(payload)

    return {"status": "ok"}
