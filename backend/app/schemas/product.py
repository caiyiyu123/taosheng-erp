from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class ProductCreate(BaseModel):
    sku: str
    name: str = ""
    purchase_price: float = 0.0
    weight: float = 0.0
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0


class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    purchase_price: Optional[float] = None
    weight: Optional[float] = None
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    image: str
    purchase_price: float
    weight: float
    length: float
    width: float
    height: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
