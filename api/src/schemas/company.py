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

    model_config = ConfigDict(from_attributes=True)
