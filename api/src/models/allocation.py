from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .company import Company
    from .transaction import Transaction
    from .wave_category import WaveCategory


class SyncStatus(StrEnum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    IGNORED = "IGNORED"


class Allocation(Base):
    __tablename__ = "allocations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_personal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    wave_category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("wave_categories.id", ondelete="SET NULL"), nullable=True)
    sync_status: Mapped[SyncStatus] = mapped_column(
        SQLEnum(SyncStatus, name="sync_status", native_enum=False),
        nullable=False,
        default=SyncStatus.PENDING,
    )
    wave_transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)

    transaction: Mapped[Transaction] = relationship("Transaction", back_populates="allocations")
    company: Mapped[Company | None] = relationship("Company")
    wave_category: Mapped[WaveCategory | None] = relationship("WaveCategory")
