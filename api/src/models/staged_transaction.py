import datetime
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

from .staged_allocation import StagedAllocation


class StagedTransaction(Base):
    __tablename__ = "staged_transactions"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_staged_transactions_source_external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency_code: Mapped[str] = mapped_column(String, nullable=False, default="CAD")
    receipt_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="STAGED", index=True)
    is_marked_imported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ledger_transaction_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.datetime.now(datetime.UTC))

    allocations: Mapped[list[StagedAllocation]] = relationship(
        "StagedAllocation",
        back_populates="staged_transaction",
        cascade="all, delete-orphan",
    )
