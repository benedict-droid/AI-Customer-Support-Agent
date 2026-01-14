from fastapi import APIRouter
from api.routes import health, chat

app_router = APIRouter()

app_router.include_router(health.router)
app_router.include_router(chat.router, prefix="/chat", tags=["chat"])

