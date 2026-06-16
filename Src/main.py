from fastapi import FastAPI

from .webhook.router import router as webhook_router


app = FastAPI(title="AI Review Webhook")
app.include_router(webhook_router)
