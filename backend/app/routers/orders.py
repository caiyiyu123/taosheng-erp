import threading
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models.order import Order, OrderItem, OrderStatusLog
from app.models.shop import Shop
from app.schemas.order import OrderOut, OrderListOut
from app.utils.deps import get_current_user, get_accessible_shop_ids, require_module, require_role
from app.services.sync import sync_shop_orders

router = APIRouter(prefix="/api/orders", tags=["orders"])

_order_sync_status = {"status": "idle"}
_order_sync_lock = threading.Lock()


@router.get("", response_model=OrderListOut)
def list_orders(
    shop_id: Optional[int] = Query(None),
    order_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="搜索订单号或产品SKU"),
    date_from: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("orders")),
):
    query = db.query(Order)
    if accessible_shops is not None:
        query = query.filter(Order.shop_id.in_(accessible_shops))
    if shop_id:
        query = query.filter(Order.shop_id == shop_id)
    if order_type:
        query = query.filter(Order.order_type == order_type)
    if status:
        query = query.filter(Order.status == status)
    if date_from:
        from datetime import datetime, timedelta, timezone
        _MSK = timezone(timedelta(hours=3))
        try:
            d = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=_MSK)
            query = query.filter(Order.created_at >= d.astimezone(timezone.utc).replace(tzinfo=None))
        except ValueError:
            pass
    if date_to:
        from datetime import datetime, timedelta, timezone
        _MSK = timezone(timedelta(hours=3))
        try:
            d = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=_MSK) + timedelta(days=1)
            query = query.filter(Order.created_at < d.astimezone(timezone.utc).replace(tzinfo=None))
        except ValueError:
            pass
    if search:
        keyword = f"%{search}%"
        # Find order IDs matching by SKU
        sku_order_ids = [
            row[0] for row in
            db.query(OrderItem.order_id).filter(OrderItem.sku.like(keyword)).all()
        ]
        # Search by order number or product SKU
        if sku_order_ids:
            query = query.filter(
                Order.wb_order_id.like(keyword) | Order.id.in_(sku_order_ids)
            )
        else:
            query = query.filter(Order.wb_order_id.like(keyword))
    total = query.count()
    orders = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return OrderListOut(items=orders, total=total)


# --- Sync endpoints (must be before /{order_id} to avoid route conflict) ---

def _run_order_sync():
    db = SessionLocal()
    try:
        shops = db.query(Shop).filter(Shop.is_active == True).all()
        synced = 0
        for shop in shops:
            try:
                sync_shop_orders(db, shop)
                synced += 1
            except Exception as e:
                print(f"[OrderSync] Failed for {shop.name}: {e}")
        with _order_sync_lock:
            _order_sync_status["status"] = "done"
            _order_sync_status["detail"] = f"已同步 {synced}/{len(shops)} 个店铺的订单"
    except Exception as e:
        with _order_sync_lock:
            _order_sync_status["status"] = "error"
            _order_sync_status["detail"] = str(e)
    finally:
        db.close()


@router.post("/sync")
def trigger_order_sync(_=Depends(require_role("admin", "operator"))):
    with _order_sync_lock:
        if _order_sync_status["status"] == "running":
            return {"status": "running", "detail": "订单同步进行中，请稍候"}
        _order_sync_status["status"] = "running"
        _order_sync_status["detail"] = ""
    thread = threading.Thread(target=_run_order_sync, daemon=True)
    thread.start()
    return {"status": "running", "detail": "订单同步已启动"}


@router.get("/sync/status")
def order_sync_status(_=Depends(require_role("admin", "operator"))):
    with _order_sync_lock:
        return dict(_order_sync_status)


# --- Single order detail ---

@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db), accessible_shops: list[int] | None = Depends(get_accessible_shop_ids), _=Depends(require_module("orders"))):
    query = db.query(Order).filter(Order.id == order_id)
    if accessible_shops is not None:
        query = query.filter(Order.shop_id.in_(accessible_shops))
    order = query.first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# --- 临时接口：清空 FBW 订单数据（用完后删除） ---
@router.delete("/cleanup-fbw")
def cleanup_fbw_orders(db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    fbw_orders = db.query(Order).filter(Order.order_type == "FBW").all()
    count = len(fbw_orders)
    for o in fbw_orders:
        db.query(OrderStatusLog).filter(OrderStatusLog.order_id == o.id).delete()
        db.query(OrderItem).filter(OrderItem.order_id == o.id).delete()
        db.delete(o)
    db.commit()
    return {"detail": f"已清除 {count} 条 FBW 订单"}
