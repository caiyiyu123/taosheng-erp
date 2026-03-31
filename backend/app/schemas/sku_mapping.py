from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class SkuMappingOut(BaseModel):
    id: int
    shop_id: int
    shop_sku: str
    product_id: Optional[int] = None
    wb_product_name: str
    wb_barcode: str
    created_at: datetime

    class Config:
        from_attributes = True


class SkuMappingUpdate(BaseModel):
    product_sku: str
