import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    wave_business_id: Mapped[str | None] = mapped_column(String, nullable=True)
    wave_access_token: Mapped[str | None] = mapped_column(String, nullable=True)
    wave_refresh_token: Mapped[str | None] = mapped_column(String, nullable=True)
    wave_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    wave_equity_account_id: Mapped[str] = mapped_column(String, nullable=False)
