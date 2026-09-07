import uuid

from pydantic import BaseModel, ConfigDict, Field


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, description="Company name")


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, description="Company name")


class CompanyResponse(CompanyBase):
    id: uuid.UUID
    transaction_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CompanySyncStatusBatchRequest(BaseModel):
    allocation_ids: list[uuid.UUID] | None = None
