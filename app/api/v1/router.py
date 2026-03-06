from fastapi import APIRouter

from app.api.v1.health import router as health_router

# Future routers plug in here
# from app.api.v1.chat import router as chat_router
# from app.api.v1.sessions import router as sessions_router

router = APIRouter()

router.include_router(health_router, tags=["Health"])
# router.include_router(chat_router, prefix="/chat", tags=["Chat"])
# router.include_router(sessions_router, prefix="/sessions", tags=["Sessions"])
