from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat, health, session
from app.session_store import SessionStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session_store = SessionStore(ttl_minutes=settings.session_ttl_minutes)
    yield


app = FastAPI(title="Insurance Claim Guide", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [health.router, session.router, chat.router]:
    app.include_router(router)
    app.include_router(router, prefix="/api")
