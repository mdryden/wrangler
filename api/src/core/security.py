import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from .config import settings

http_bearer = HTTPBearer(auto_error=False)

ANONYMOUS_PATHS: set[str] = {
    "/api/health",
    "/api/login",
    "/docs",
    "/redoc",
    "/openapi.json",
}


def allow_anonymous[T: Callable[..., Any]](func: T) -> T:
    """Decorator to opt-in an endpoint for anonymous/unauthenticated access."""
    func._allow_anonymous = True  # type: ignore[attr-defined]
    return func


def verify_admin_credentials(
    username: str,
    password: str,
    expected_username: str,
    expected_password: str,
) -> bool:
    """Verify provided credentials against expected credentials using constant-time comparison."""
    is_correct_username = secrets.compare_digest(username.encode("utf-8"), expected_username.encode("utf-8"))
    is_correct_password = secrets.compare_digest(password.encode("utf-8"), expected_password.encode("utf-8"))
    return is_correct_username and is_correct_password


def create_access_token(
    data: dict,
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token with an expiration timestamp."""
    to_encode = data.copy()
    now = datetime.now(UTC)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=15)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_access_token(
    token: str,
    secret_key: str,
    algorithms: list[str] | None = None,
) -> dict:
    """Decode and validate a signed JWT access token."""
    algs = algorithms if algorithms is not None else ["HS256"]
    try:
        return jwt.decode(
            token,
            secret_key,
            algorithms=algs,
        )
    except jwt.PyJWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware that protects all endpoints across the system by default unless opted in as anonymous."""

    def __init__(self, app: Any, anonymous_paths: set[str] | None = None):
        super().__init__(app)
        self.anonymous_paths = anonymous_paths if anonymous_paths is not None else ANONYMOUS_PATHS

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path.rstrip("/")
        if not path:
            path = "/"

        if path in self.anonymous_paths or path.startswith(("/docs", "/redoc")):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = parts[1]
        try:
            payload = decode_access_token(
                token=token,
                secret_key=settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Could not validate credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        username: str | None = payload.get("sub")
        if username is None or not secrets.compare_digest(username.encode("utf-8"), settings.ADMIN_USERNAME.encode("utf-8")):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Could not validate credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        request.state.current_user = username
        return await call_next(request)


async def get_current_user(request: Request) -> str:
    """FastAPI dependency to extract the authenticated admin username from request.state."""
    username = getattr(request.state, "current_user", None)
    if username is not None:
        return username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


CurrentUser = Annotated[str, Depends(get_current_user)]
