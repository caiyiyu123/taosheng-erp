from typing import Optional
from fastapi import APIRouter, Depends, Query
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

    total_purchase_cost = 0.0
    for item in items:
        order = db.query(Order).filter(Order.id == item.order_id).first()
        mapping = db.query(SkuMapping).filter(
            SkuMapping.shop_id == order.shop_id, SkuMapping.shop_sku == item.sku
        ).first()
        if mapping and mapping.product_id:
            product = db.query(Product).filter(Product.id == mapping.product_id).first()
            if product:
                total_purchase_cost += product.purchase_price * item.quantity

    total_profit = total_sales - total_purchase_cost - total_commission - total_logistics
    return {
        "total_sales": total_sales,
        "total_commission": total_commission,
        "total_logistics": total_logistics,
        "total_purchase_cost": total_purchase_cost,
        "total_profit": total_profit,
        "order_count": len(set(i.order_id for i in items)),
    }
