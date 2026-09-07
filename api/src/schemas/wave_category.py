import uuid

from pydantic import BaseModel, ConfigDict, Field


class WaveCategoryBase(BaseModel):
    company_id: uuid.UUID
    wave_account_id: str = Field(..., min_length=1, description="Wave account ID")
    name: str = Field(..., min_length=1, description="Wave account / category name")


class WaveCategoryResponse(WaveCategoryBase):
    id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)
