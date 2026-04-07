from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class OrderItemOut(BaseModel):
    id: int
    wb_product_id: str
    product_name: str
    sku: str
    barcode: str
    image_url: str = ""
    quantity: int
    price: float
    commission: float
    logistics_cost: float
    class Config:
        from_attributes = True


class OrderStatusLogOut(BaseModel):
    id: int
    status: str
    wb_status: str
    changed_at: datetime
    note: str
    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    wb_order_id: str
    shop_id: int
    order_type: str
    status: str
    total_price: float
    price_rub: float = 0.0
    price_cny: float = 0.0
    currency: str
    customer_name: str
    warehouse_name: str
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut] = []
    status_logs: list[OrderStatusLogOut] = []
    class Config:
        from_attributes = True


class OrderListOut(BaseModel):
    items: list[dict]
    total: int
