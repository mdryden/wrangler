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

    # Receipt Storage
    RECEIPT_STORAGE_DIR: Path = Path("receipts").resolve()

    # Database
    DATABASE_URL: str = "sqlite:///./wrangler.db"

    # MCP Integration
    MCP_API_KEY: str = ""

    # AI Receipt Parsing Configuration
    AI_PROVIDER: str = "openai"  # "openai" or "mock"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    AI_TIMEOUT_SECONDS: int = 60
    AI_MAX_BATCH_CONCURRENCY: int = 3
    AI_MAX_PDF_PAGES: int = 3
    MAX_RECEIPT_FILE_SIZE: int = 20 * 1024 * 1024  # 20 MB

    @field_validator("RECEIPT_STORAGE_DIR", mode="after")
    @classmethod
    def resolve_receipt_storage_dir(cls, v: Path | str) -> Path:
        return Path(v).expanduser().resolve()


settings = Settings()
