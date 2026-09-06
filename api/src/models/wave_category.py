import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

from .company import Company


class WaveCategory(Base):
    __tablename__ = "wave_categories"
    __table_args__ = (UniqueConstraint("company_id", "wave_account_id", name="uq_wave_categories_company_wave_account_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    wave_account_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)

    company: Mapped[Company] = relationship("Company")
