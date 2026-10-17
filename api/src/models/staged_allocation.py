from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Numeric, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .company import Company
    from .staged_transaction import StagedTransaction


class StagedAllocation(Base):
    __tablename__ = "staged_allocations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    staged_transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("staged_transactions.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_personal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True)

    staged_transaction: Mapped[StagedTransaction] = relationship("StagedTransaction", back_populates="allocations")
    company: Mapped[Company | None] = relationship("Company")
