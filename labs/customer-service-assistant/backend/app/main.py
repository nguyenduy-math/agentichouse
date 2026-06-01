import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.mcp_client import MCPClientManager
from app.routers.chat import router as chat_router

_DIST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp = MCPClientManager()
    await mcp.start()
    app.state.mcp = mcp
    yield
    await mcp.stop()


app = FastAPI(title="Customer Service Assistant", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(chat_router, prefix="/api")

if os.path.exists(_DIST_DIR):
    _assets = os.path.join(_DIST_DIR, "assets")
    if os.path.exists(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(_DIST_DIR, "index.html"))
