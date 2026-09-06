from datetime import timedelta

from fastapi import APIRouter, HTTPException, status

from core.config import settings
from core.security import (
    CurrentUser,
    allow_anonymous,
    create_access_token,
    verify_admin_credentials,
)
from schemas.auth import LoginRequest, Token

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login", response_model=Token)
@allow_anonymous
def login(credentials: LoginRequest) -> Token:
    if not verify_admin_credentials(
        username=credentials.username,
        password=credentials.password,
        expected_username=settings.ADMIN_USERNAME,
        expected_password=settings.ADMIN_PASSWORD,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": credentials.username},
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/auth/me")
def get_me(current_user: CurrentUser) -> dict[str, str]:
    return {"username": current_user}


@router.get("/protected")
def protected_status() -> dict[str, str]:
    """Test endpoint that takes no user arguments, proving all endpoints are secure by default."""
    return {"status": "authenticated"}
