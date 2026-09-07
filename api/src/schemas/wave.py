from pydantic import BaseModel, Field


class WaveAuthorizeResponse(BaseModel):
    authorization_url: str = Field(..., description="Wave OAuth authorization URL")
    redirect_url: str = Field(..., description="Alias for authorization_url")
