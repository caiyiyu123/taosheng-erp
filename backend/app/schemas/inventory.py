from datetime import datetime
from pydantic import BaseModel


class InventoryOut(BaseModel):
    id: int
    shop_id: int
    wb_product_id: str
    product_name: str
    sku: str
    barcode: str
    stock_fbs: int
    stock_fbw: int
    low_stock_threshold: int
    updated_at: datetime
    class Config:
        from_attributes = True
