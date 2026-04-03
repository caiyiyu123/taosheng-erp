from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.product import SkuMapping, Product
from app.utils.deps import get_current_user, get_accessible_shop_ids, require_module

router = APIRouter(prefix="/api/finance", tags=["finance"])


@router.get("/summary")
def finance_summary(
    shop_id: Optional[int] = Query(None),
    order_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("finance")),
):
    # Base filter conditions
    base_query = db.query(OrderItem).join(Order)
    if accessible_shops is not None:
        base_query = base_query.filter(Order.shop_id.in_(accessible_shops))
    if shop_id:
        base_query = base_query.filter(Order.shop_id == shop_id)
    if order_type:
        base_query = base_query.filter(Order.order_type == order_type)

    # Use SQL aggregation instead of loading all items into memory
    agg_result = base_query.with_entities(
        func.sum(OrderItem.price * OrderItem.quantity).label("total_sales"),
        func.sum(OrderItem.commission).label("total_commission"),
        func.sum(OrderItem.logistics_cost).label("total_logistics"),
        func.count(func.distinct(OrderItem.order_id)).label("order_count"),
    ).one()

    total_sales = agg_result.total_sales or 0.0
    total_commission = agg_result.total_commission or 0.0
    total_logistics = agg_result.total_logistics or 0.0
    order_count = agg_result.order_count or 0

    # Single query with JOIN to calculate purchase cost (avoids N+1)
    purchase_query = (
        db.query(func.sum(Product.purchase_price * OrderItem.quantity))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(SkuMapping, (SkuMapping.shop_id == Order.shop_id) & (SkuMapping.shop_sku == OrderItem.sku))
        .join(Product, Product.id == SkuMapping.product_id)
    )
    if accessible_shops is not None:
        purchase_query = purchase_query.filter(Order.shop_id.in_(accessible_shops))
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
        "order_count": order_count,
    }
