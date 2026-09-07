from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_CORE_DIR = Path(__file__).resolve().parent
_API_DIR = _CORE_DIR.parent.parent
_ROOT_DIR = _API_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_API_DIR / ".env"),
            str(_ROOT_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Admin Credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    # JWT Session Management
    JWT_SECRET_KEY: str = "change-me-in-production-secret-key-32-chars-long"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Wave OAuth & API
    WAVE_CLIENT_ID: str = ""
    WAVE_CLIENT_SECRET: str = ""
    WAVE_REDIRECT_URI: str = "http://localhost:8000/api/wave/oauth/callback"
    WAVE_AUTHORIZE_URL: str = "https://api.waveapps.com/oauth2/authorize/"
    WAVE_TOKEN_URL: str = "https://api.waveapps.com/oauth2/token/"
    WAVE_GRAPHQL_URL: str = "https://api.waveapps.com/graphql/public"

    # Receipt Storage
    RECEIPT_STORAGE_DIR: Path = Path("receipts").resolve()

    # Database
    DATABASE_URL: str = "sqlite:///./wrangler.db"

    @field_validator("RECEIPT_STORAGE_DIR", mode="after")
    @classmethod
    def resolve_receipt_storage_dir(cls, v: Path | str) -> Path:
        return Path(v).expanduser().resolve()


settings = Settings()
