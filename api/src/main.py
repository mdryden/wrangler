from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings
from core.security import AuthenticationMiddleware
from database import get_db
from routers.auth import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure receipt storage directory exists on startup
    settings.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    yield


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

app.include_router(auth_router)


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
