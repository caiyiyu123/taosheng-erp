from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.inventory import Inventory
from app.utils.deps import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# China timezone (UTC+8), consistent with WB cross-border store backend
_CN_TZ = timezone(timedelta(hours=8))


@router.get("/stats")
def dashboard_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    # "Today" in China time (UTC+8) to match WB store backend
    now_cn = datetime.now(_CN_TZ)
    today_start_cn = now_cn.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_cn.astimezone(timezone.utc).replace(tzinfo=None)

    today_orders = db.query(Order).filter(Order.created_at >= today_start_utc).count()
    today_sales_result = (
        db.query(func.coalesce(func.sum(Order.total_price), 0))
        .filter(Order.created_at >= today_start_utc).scalar()
    )
    pending_shipment = db.query(Order).filter(Order.status == "pending").count()
    in_transit_count = db.query(Order).filter(Order.status == "in_transit").count()
    low_stock_count = db.query(Inventory).filter(
        (Inventory.stock_fbs + Inventory.stock_fbw) < Inventory.low_stock_threshold
    ).count()
    total_orders = db.query(Order).count()
    total_sales = float(
        db.query(func.coalesce(func.sum(Order.total_price), 0)).scalar()
    )
    recent_orders = db.query(Order).order_by(Order.created_at.desc()).limit(10).all()
    return {
        "today_orders": today_orders,
        "today_sales": float(today_sales_result),
        "pending_shipment": pending_shipment,
        "in_transit_count": in_transit_count,
        "low_stock_count": low_stock_count,
        "total_orders": total_orders,
        "total_sales": total_sales,
        "recent_orders": [
            {"id": o.id, "wb_order_id": o.wb_order_id, "shop_id": o.shop_id,
             "order_type": o.order_type, "status": o.status, "total_price": o.total_price,
             "currency": o.currency, "created_at": o.created_at.isoformat()} for o in recent_orders
        ],
    }
