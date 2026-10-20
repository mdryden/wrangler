from pathlib import Path

from pydantic import model_validator
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

    # Centralized Local Data Directory
    # If set, automatically derives default DATABASE_URL and RECEIPT_STORAGE_DIR
    DATA_DIR: Path | None = None

    # Admin Credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    # JWT Session Management
    JWT_SECRET_KEY: str = "change-me-in-production-secret-key-32-chars-long"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Receipt Storage
    RECEIPT_STORAGE_DIR: Path = Path("receipts").resolve()

    # Static Assets Directory (Compiled Vue SPA)
    STATIC_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"

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

    @model_validator(mode="after")
    def resolve_paths(self) -> Settings:
        if self.DATA_DIR is not None:
            resolved_data = self.DATA_DIR.expanduser().resolve()
            resolved_data.mkdir(parents=True, exist_ok=True)

            # Default DATABASE_URL to DATA_DIR/wrangler.db if not explicitly customized
            if self.DATABASE_URL == "sqlite:///./wrangler.db":
                db_file = (resolved_data / "wrangler.db").as_posix()
                self.DATABASE_URL = f"sqlite:///{db_file}"

            # Default RECEIPT_STORAGE_DIR to DATA_DIR/receipts if not explicitly customized
            if Path(self.RECEIPT_STORAGE_DIR).resolve() == Path("receipts").resolve():
                self.RECEIPT_STORAGE_DIR = (resolved_data / "receipts").resolve()

        # Ensure receipt storage directory exists
        self.RECEIPT_STORAGE_DIR = Path(self.RECEIPT_STORAGE_DIR).expanduser().resolve()
        self.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return self


settings = Settings()
