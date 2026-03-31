from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel

ShopType = Literal["cross_border", "local"]


class ShopCreate(BaseModel):
    name: str
    type: ShopType
    api_token: str


class ShopUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[ShopType] = None
    api_token: Optional[str] = None
    is_active: Optional[bool] = None


class ShopOut(BaseModel):
    id: int
    name: str
    type: str
    is_active: bool
    last_sync_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
