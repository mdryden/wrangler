import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, description="Company name")
    wave_equity_account_id: str = Field(..., min_length=1, description="Wave offset/anchor equity account ID")
    wave_business_id: str | None = Field(default=None, description="Wave business ID")


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, description="Company name")
    wave_equity_account_id: str | None = Field(default=None, min_length=1, description="Wave offset/anchor equity account ID")
    wave_business_id: str | None = Field(default=None, description="Wave business ID")
    wave_access_token: str | None = Field(default=None, description="Wave access token")
    wave_refresh_token: str | None = Field(default=None, description="Wave refresh token")
    wave_token_expires_at: datetime | None = Field(default=None, description="Wave token expiration timestamp")


class CompanyResponse(CompanyBase):
    id: uuid.UUID
    wave_access_token: str | None = None
    wave_refresh_token: str | None = None
    wave_token_expires_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def is_connected(self) -> bool:
        return bool(self.wave_access_token)
