from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .wave_category import WaveCategory


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    wave_api_token: Mapped[str | None] = mapped_column(String, nullable=True)
    wave_business_id: Mapped[str | None] = mapped_column(String, nullable=True)
    wave_business_name: Mapped[str | None] = mapped_column(String, nullable=True)
    wave_anchor_account_id: Mapped[str | None] = mapped_column(String, nullable=True)

    categories: Mapped[list[WaveCategory]] = relationship("WaveCategory", back_populates="company", cascade="all, delete-orphan")
