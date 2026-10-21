import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, description="Company name")


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, description="Company name")


class CompanyResponse(CompanyBase):
    id: uuid.UUID
    transaction_count: int = 0
    unlocked_allocation_count: int = 0
    unlocked_amount_total: Decimal = Decimal("0.00")
    locked_allocation_count: int = 0
    wave_business_id: str | None = None
    wave_business_name: str | None = None
    wave_anchor_account_id: str | None = None
    is_wave_connected: bool = False

    model_config = ConfigDict(from_attributes=True)


class CompanyLockBatchRequest(BaseModel):
    allocation_ids: list[uuid.UUID] | None = None


CompanySyncStatusBatchRequest = CompanyLockBatchRequest


class WaveTestTokenRequest(BaseModel):
    token: str = Field(..., min_length=1)


class WaveBusinessAccountsRequest(BaseModel):
    token: str = Field(..., min_length=1)
    business_id: str = Field(..., min_length=1)


class WaveBusinessItem(BaseModel):
    id: str
    name: str
    is_personal: bool


class WaveAccountItem(BaseModel):
    id: str
    name: str
    type: str
    subtype: str | None = None
    is_uncategorized: bool = False


class WaveBusinessAccountsResponse(BaseModel):
    anchor_accounts: list[WaveAccountItem]
    expense_categories: list[WaveAccountItem]


class WaveConnectRequest(BaseModel):
    token: str = Field(..., min_length=1, description="Wave Full Access Bearer Token")
    business_id: str = Field(..., min_length=1, description="Wave Business ID")
    business_name: str = Field(..., min_length=1, description="Wave Business Name")
    anchor_account_id: str = Field(..., min_length=1, description="Selected Wave Anchor Account ID")
    equity_account_id: str | None = Field(default=None, description="Legacy fallback alias for anchor_account_id")

    @model_validator(mode="before")
    @classmethod
    def fallback_equity_account_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "anchor_account_id" not in data and "equity_account_id" in data:
                data = dict(data)
                data["anchor_account_id"] = data["equity_account_id"]
        return data


class WaveCategoryResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    wave_account_id: str
    name: str
    account_type: str
    account_subtype: str | None = None
    is_uncategorized: bool = False

    model_config = ConfigDict(from_attributes=True)


class WaveSyncBatchRequest(BaseModel):
    allocation_ids: list[uuid.UUID] | None = None


class WaveSyncErrorItem(BaseModel):
    allocation_id: uuid.UUID
    description: str
    error: str


class WaveSyncResponse(BaseModel):
    total_processed: int
    synced_count: int
    failed_count: int
    errors: list[WaveSyncErrorItem] = Field(default_factory=list)
