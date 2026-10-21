import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.types import Receive, Scope, Send

from core.config import settings
from core.security import AuthenticationMiddleware
from database import get_db
from routers.allocations import router as allocations_router
from routers.auth import router as auth_router
from routers.companies import router as companies_router
from routers.importers import router as importers_router
from routers.receipts import router as receipts_router
from routers.staging import router as staging_router
from routers.transactions import router as transactions_router
from services.backup_scheduler import run_backup_scheduler
from services.mcp import mcp

_mcp_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
# Streamable HTTP transport (POST/GET/DELETE on /sse), used by modern clients such as Goose
mcp_stream_app = mcp.streamable_http_app(streamable_http_path="/sse", json_response=True, transport_security=_mcp_security)
# Legacy HTTP+SSE transport (GET /sse, POST /messages/), used by clients configured with `type: sse`
mcp_legacy_sse_app = mcp.sse_app(transport_security=_mcp_security)


class MCPTransportDispatcher:
    """Serve both MCP HTTP transports under one mount.

    A GET on /sse without an Mcp-Session-Id header opens a legacy SSE stream and /messages/ receives its
    posts; every other request goes to the Streamable HTTP transport.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope["path"].removeprefix(scope.get("root_path", ""))
            headers = {k.lower(): v for k, v in scope["headers"]}
            legacy_stream = path == "/sse" and scope["method"] == "GET" and b"mcp-session-id" not in headers
            if legacy_stream or path.startswith("/messages/"):
                await mcp_legacy_sse_app(scope, receive, send)
                return
        await mcp_stream_app(scope, receive, send)


mcp_app = MCPTransportDispatcher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure receipt storage directory exists on startup
    settings.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    if not settings.BACKUP_DIR and not os.getenv("BACKUP_DIR"):
        print("\n" + "=" * 64)
        print(" WARNING: BACKUP_DIR is not configured!")
        print(" Automatic database snapshots on exit will be skipped.")
        print(" Set BACKUP_DIR in your .env to safeguard your financial data.")
        print("=" * 64 + "\n")

    # Start background backup scheduler task if BACKUP_DIR is configured
    scheduler_task = None
    if settings.BACKUP_DIR:
        scheduler_task = asyncio.create_task(run_backup_scheduler())

    session_mgr = getattr(mcp._lowlevel_server, "_session_manager", None)
    if session_mgr is not None:
        session_mgr._has_started = False
    try:
        async with mcp_stream_app.router.lifespan_context(mcp_stream_app):
            yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        if session_mgr is not None:
            session_mgr._has_started = False


app = FastAPI(
    title="Wrangler API",
    description="Family Accounting and Wave Synchronization API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(AuthenticationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/mcp", mcp_app)

app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(transactions_router)
app.include_router(receipts_router)
app.include_router(allocations_router)
app.include_router(importers_router)
app.include_router(staging_router)


@app.get("/api/health")
def health_check(response: Response, db: Annotated[Session, Depends(get_db)]):
    try:
        bind = db.get_bind()
        db_path = Path(bind.url.database).name if bind.url.database else "wrangler.db"
    except Exception:
        db_path = "wrangler.db"

    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "healthy",
            "meta": {
                "database_path": db_path,
            },
        }
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "unhealthy",
            "meta": {
                "database_path": db_path,
                "error": str(exc),
            },
        }


if settings.STATIC_DIR.is_dir() and (settings.STATIC_DIR / "index.html").is_file():
    assets_dir = settings.STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith(("api", "mcp", "etc")):
            raise HTTPException(status_code=404, detail="Endpoint not found")

        candidate_file = (settings.STATIC_DIR / full_path).resolve()
        if candidate_file.is_file() and candidate_file.is_relative_to(settings.STATIC_DIR):
            return FileResponse(candidate_file)

        return FileResponse(settings.STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
