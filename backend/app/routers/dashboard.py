from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.inventory import Inventory
from app.utils.deps import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
def dashboard_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders = db.query(Order).filter(Order.created_at >= today_start).count()
    today_sales_result = (
        db.query(func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0))
        .join(Order).filter(Order.created_at >= today_start).scalar()
    )
    pending_shipment = db.query(Order).filter(Order.status == "pending").count()
    low_stock_count = db.query(Inventory).filter(
        (Inventory.stock_fbs + Inventory.stock_fbw) < Inventory.low_stock_threshold
    ).count()
    recent_orders = db.query(Order).order_by(Order.created_at.desc()).limit(10).all()
    return {
        "today_orders": today_orders,
        "today_sales": float(today_sales_result),
        "pending_shipment": pending_shipment,
        "low_stock_count": low_stock_count,
        "recent_orders": [
            {"id": o.id, "wb_order_id": o.wb_order_id, "shop_id": o.shop_id,
             "order_type": o.order_type, "status": o.status, "total_price": o.total_price,
             "created_at": o.created_at.isoformat()} for o in recent_orders
        ],
    }
