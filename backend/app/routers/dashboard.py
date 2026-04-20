from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.inventory import Inventory
from app.utils.deps import get_accessible_shop_ids, require_module

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Moscow timezone (UTC+3), consistent with WB ad API and store backend
_MSK_TZ = timezone(timedelta(hours=3))


def _shop_filter(query, model_shop_id, accessible_shops):
    if accessible_shops is not None:
        query = query.filter(model_shop_id.in_(accessible_shops))
    return query


@router.get("/stats")
def dashboard_stats(db: Session = Depends(get_db), accessible_shops: list[int] | None = Depends(get_accessible_shop_ids), _=Depends(require_module("dashboard"))):
    # "Today" in Moscow time (UTC+3) to match WB store backend
    now_msk = datetime.now(_MSK_TZ)
    today_start_msk = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_msk.astimezone(timezone.utc).replace(tzinfo=None)

    base_q = db.query(Order)
    if accessible_shops is not None:
        base_q = base_q.filter(Order.shop_id.in_(accessible_shops))

    today_orders = base_q.filter(Order.created_at >= today_start_utc).count()
    today_sales_q = db.query(func.coalesce(func.sum(Order.price_rub), 0)).filter(Order.created_at >= today_start_utc)
    if accessible_shops is not None:
        today_sales_q = today_sales_q.filter(Order.shop_id.in_(accessible_shops))
    today_sales_result = today_sales_q.scalar()

    # Yesterday
    yesterday_start_msk = today_start_msk - timedelta(days=1)
    yesterday_start_utc = yesterday_start_msk.astimezone(timezone.utc).replace(tzinfo=None)
    yesterday_orders = base_q.filter(Order.created_at >= yesterday_start_utc, Order.created_at < today_start_utc).count()
    yesterday_sales_q = db.query(func.coalesce(func.sum(Order.price_rub), 0)).filter(
        Order.created_at >= yesterday_start_utc, Order.created_at < today_start_utc
    )
    if accessible_shops is not None:
        yesterday_sales_q = yesterday_sales_q.filter(Order.shop_id.in_(accessible_shops))
    yesterday_sales_result = yesterday_sales_q.scalar()

    pending_shipment = base_q.filter(Order.status == "pending").count()
    in_transit_count = base_q.filter(Order.status == "in_transit").count()

    inv_q = db.query(Inventory).filter(
        (Inventory.stock_fbs + Inventory.stock_fbw) < Inventory.low_stock_threshold
    )
    if accessible_shops is not None:
        inv_q = inv_q.filter(Inventory.shop_id.in_(accessible_shops))
    low_stock_count = inv_q.count()

    # 近30天
    days30_start_msk = (now_msk - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    days30_start_utc = days30_start_msk.astimezone(timezone.utc).replace(tzinfo=None)

    days30_q = base_q.filter(Order.created_at >= days30_start_utc)
    days30_orders = days30_q.count()
    days30_sales_q = db.query(func.coalesce(func.sum(Order.price_rub), 0)).filter(Order.created_at >= days30_start_utc)
    if accessible_shops is not None:
        days30_sales_q = days30_sales_q.filter(Order.shop_id.in_(accessible_shops))
    days30_sales = float(days30_sales_q.scalar())

    # 近30天每日趋势（按莫斯科日期分组）
    from sqlalchemy import cast, Date, text
    from app.config import DATABASE_URL
    if DATABASE_URL.startswith("postgresql"):
        day_expr = cast(Order.created_at + text("interval '3 hours'"), Date).label('day')
    else:
        day_expr = func.date(Order.created_at, '+3 hours').label('day')
    daily_q = db.query(
        day_expr,
        func.count(Order.id),
        func.coalesce(func.sum(Order.price_rub), 0),
    ).filter(
        Order.created_at >= days30_start_utc,
    )
    if accessible_shops is not None:
        daily_q = daily_q.filter(Order.shop_id.in_(accessible_shops))
    daily_rows = daily_q.group_by('day').order_by('day').all()
    daily_map = {str(r[0]): {"orders": int(r[1]), "sales": float(r[2])} for r in daily_rows}

    # 填充无数据的日期为0
    daily_trend = []
    for i in range(30):
        d = (days30_start_msk + timedelta(days=i)).strftime('%Y-%m-%d')
        info = daily_map.get(d, {"orders": 0, "sales": 0.0})
        daily_trend.append({"date": d, "orders": info["orders"], "sales": info["sales"]})

    return {
        "today_orders": today_orders,
        "today_sales": float(today_sales_result),
        "yesterday_orders": yesterday_orders,
        "yesterday_sales": float(yesterday_sales_result),
        "pending_shipment": pending_shipment,
        "in_transit_count": in_transit_count,
        "low_stock_count": low_stock_count,
        "days30_orders": days30_orders,
        "days30_sales": days30_sales,
        "daily_trend": daily_trend,
    }


from app.models.shop import Shop


@router.get("/shops")
def dashboard_shops(
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("dashboard")),
):
    """返回当前用户可访问的店铺方块数据：今日订单/销售额、近30天销售额。"""
    from sqlalchemy import cast, Date, text, case
    from app.config import DATABASE_URL

    now_msk = datetime.now(_MSK_TZ)
    today = now_msk.date()
    d30_start = today - timedelta(days=29)

    if DATABASE_URL.startswith("postgresql"):
        order_date = cast(Order.created_at + text("interval '3 hours'"), Date)
    else:
        order_date = func.date(Order.created_at, '+3 hours')

    agg_q = db.query(
        Order.shop_id,
        func.sum(case((order_date == today, 1), else_=0)).label("today_orders"),
        func.sum(case((order_date == today, Order.price_rub), else_=0)).label("today_sales"),
        func.sum(case((order_date >= d30_start, Order.price_rub), else_=0)).label("last_30d_sales"),
    ).filter(order_date >= d30_start)
    if accessible_shops is not None:
        agg_q = agg_q.filter(Order.shop_id.in_(accessible_shops))
    agg_rows = agg_q.group_by(Order.shop_id).all()
    agg_map = {r.shop_id: r for r in agg_rows}

    shop_q = db.query(Shop)
    if accessible_shops is not None:
        shop_q = shop_q.filter(Shop.id.in_(accessible_shops))
    shops = shop_q.order_by(Shop.id).all()

    result = []
    for s in shops:
        agg = agg_map.get(s.id)
        result.append({
            "id": s.id,
            "name": s.name,
            "today_orders": int(agg.today_orders) if agg else 0,
            "today_sales": float(agg.today_sales) if agg else 0.0,
            "last_30d_sales": float(agg.last_30d_sales) if agg else 0.0,
        })
    return {"shops": result}
