from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.health import router as health_router
from app.api.v1.sessions import router as sessions_router

router = APIRouter()

router.include_router(health_router, tags=["Health"])
router.include_router(chat_router, tags=["Chat"])
router.include_router(sessions_router, tags=["Sessions"])
