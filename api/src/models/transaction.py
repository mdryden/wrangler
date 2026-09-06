import datetime
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Date, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

from .allocation import Allocation


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_transactions_source_external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    receipt_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    allocations: Mapped[list[Allocation]] = relationship(
        "Allocation",
        back_populates="transaction",
        cascade="all, delete-orphan",
    )
