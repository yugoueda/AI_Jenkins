import hmac
import os

from fastapi import HTTPException


def verify_signature(token: str) -> None:
    secret = os.getenv("GITLAB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret is not configured")
    if not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Invalid token")
