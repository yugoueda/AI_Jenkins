from fastapi import FastAPI

from .jenkins.callback import router as jenkins_callback_router
from .webhook.router import router as webhook_router


app = FastAPI(title="AI Review Webhook")
app.include_router(webhook_router)
app.include_router(jenkins_callback_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
