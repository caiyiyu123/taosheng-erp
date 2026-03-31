from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.product import SkuMapping, Product
from app.utils.deps import get_current_user

router = APIRouter(prefix="/api/finance", tags=["finance"])


@router.get("/summary")
def finance_summary(
    shop_id: Optional[int] = Query(None),
    order_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(OrderItem).join(Order)
    if shop_id:
        query = query.filter(Order.shop_id == shop_id)
    if order_type:
        query = query.filter(Order.order_type == order_type)
    items = query.all()

    total_sales = sum(i.price * i.quantity for i in items)
    total_commission = sum(i.commission for i in items)
    total_logistics = sum(i.logistics_cost for i in items)

    # Single query with JOIN to calculate purchase cost (avoids N+1)
    purchase_query = (
        db.query(func.sum(Product.purchase_price * OrderItem.quantity))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(SkuMapping, (SkuMapping.shop_id == Order.shop_id) & (SkuMapping.shop_sku == OrderItem.sku))
        .join(Product, Product.id == SkuMapping.product_id)
    )
    if shop_id:
        purchase_query = purchase_query.filter(Order.shop_id == shop_id)
    if order_type:
        purchase_query = purchase_query.filter(Order.order_type == order_type)
    total_purchase_cost = purchase_query.scalar() or 0.0

    total_profit = total_sales - total_purchase_cost - total_commission - total_logistics
    return {
        "total_sales": total_sales,
        "total_commission": total_commission,
        "total_logistics": total_logistics,
        "total_purchase_cost": total_purchase_cost,
        "total_profit": total_profit,
        "order_count": len(set(i.order_id for i in items)),
    }
