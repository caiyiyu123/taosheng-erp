import threading
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from sqlalchemy import func

from app.database import get_db, SessionLocal
from app.models.product import ShopProduct
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem
from app.models.shop import Shop
from app.models.setting import SystemSetting
from app.utils.deps import get_current_user, get_accessible_shop_ids, require_module, require_role

router = APIRouter(prefix="/api/shop-products", tags=["shop-products"])

_sync_status = {"status": "idle"}
_sync_lock = threading.Lock()


@router.get("")
def list_shop_products(
    shop_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("products")),
):
    query = db.query(ShopProduct)
    if accessible_shops is not None:
        query = query.filter(ShopProduct.shop_id.in_(accessible_shops))
    if shop_id:
        query = query.filter(ShopProduct.shop_id == shop_id)
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            ShopProduct.vendor_code.ilike(keyword) | ShopProduct.title.ilike(keyword)
        )
    total = query.count()
    items = query.order_by(ShopProduct.feedbacks_count.desc()).offset((page - 1) * page_size).limit(page_size).all()

    if not items:
        return {"total": total, "items": []}

    # Build stock lookup: FBS and FBW separately per vendor_code (case-insensitive)
    vendor_codes = [p.vendor_code for p in items if p.vendor_code]
    stock_map = {}
    if vendor_codes:
        vc_lower = [vc.lower() for vc in vendor_codes]
        stock_rows = db.query(
            func.lower(Inventory.sku),
            func.sum(Inventory.stock_fbs),
            func.sum(Inventory.stock_fbw),
        ).filter(
            func.lower(Inventory.sku).in_(vc_lower),
        ).group_by(func.lower(Inventory.sku)).all()
        for row in stock_rows:
            if row[0]:
                stock_map[row[0]] = {"fbs": int(row[1] or 0), "fbw": int(row[2] or 0)}

    # Get shop types for all relevant shops
    shop_ids = list({p.shop_id for p in items})
    shop_types = {}
    for s in db.query(Shop.id, Shop.type).filter(Shop.id.in_(shop_ids)).all():
        shop_types[s.id] = s.type

    # Get exchange rate
    rate_setting = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate_cny_rub").first()
    exchange_rate = float(rate_setting.value) if rate_setting and rate_setting.value else 0

    # For cross-border shops: get most frequent order price_rub per nm_id
    cross_border_shop_ids = [sid for sid, stype in shop_types.items() if stype == "cross_border"]
    rub_from_orders = {}
    if cross_border_shop_ids:
        cross_nm_ids = [str(p.nm_id) for p in items if p.shop_id in cross_border_shop_ids]
        if cross_nm_ids:
            order_rows = db.query(
                OrderItem.wb_product_id,
                Order.price_rub,
                func.count().label("cnt"),
            ).join(Order, OrderItem.order_id == Order.id).filter(
                Order.shop_id.in_(cross_border_shop_ids),
                OrderItem.wb_product_id.in_(cross_nm_ids),
                Order.price_rub > 0,
            ).group_by(OrderItem.wb_product_id, Order.price_rub).all()
            freq = {}
            for row in order_rows:
                nm_key = row[0]
                price = float(row[1])
                cnt = row[2]
                if nm_key not in freq:
                    freq[nm_key] = {}
                freq[nm_key][price] = cnt
            for nm_key, prices in freq.items():
                rub_from_orders[nm_key] = max(prices, key=prices.get)

    result = []
    for p in items:
        stype = shop_types.get(p.shop_id, "local")
        if stype == "cross_border":
            price_cny = p.price if p.price else 0
            order_rub = rub_from_orders.get(str(p.nm_id), 0)
            # Validate: if rub/cny ratio < 5, order price is wrong → use exchange rate
            if order_rub > 0 and price_cny > 0 and order_rub / price_cny >= 5:
                price_rub = order_rub
            else:
                price_rub = round(price_cny * exchange_rate, 2) if exchange_rate > 0 and price_cny > 0 else 0
        else:
            price_rub = p.price if p.price else 0
            price_cny = round(price_rub / exchange_rate, 2) if exchange_rate > 0 and price_rub > 0 else 0

        result.append({
            "id": p.id,
            "shop_id": p.shop_id,
            "nm_id": p.nm_id,
            "title": p.title,
            "vendor_code": p.vendor_code,
            "image_url": p.image_url,
            "price_rub": price_rub,
            "price_cny": price_cny,
            "discount": p.discount,
            "rating": p.rating,
            "feedbacks_count": p.feedbacks_count,
            "stock_fbs": stock_map.get(p.vendor_code.lower(), {"fbs": 0, "fbw": 0})["fbs"] if p.vendor_code else 0,
            "stock_fbw": stock_map.get(p.vendor_code.lower(), {"fbs": 0, "fbw": 0})["fbw"] if p.vendor_code else 0,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })

    return {"total": total, "items": result}


def _run_product_sync():
    from app.services.sync import sync_shop_products, sync_shop_inventory

    db = SessionLocal()
    try:
        shops = db.query(Shop).filter(Shop.is_active == True).all()
        synced = 0
        for shop in shops:
            try:
                sync_shop_inventory(db, shop)
                sync_shop_products(db, shop)
                synced += 1
            except Exception as e:
                print(f"[ProductSync] Failed for {shop.name}: {e}")
        with _sync_lock:
            _sync_status["status"] = "done"
            _sync_status["detail"] = f"已同步 {synced}/{len(shops)} 个店铺的产品"
    except Exception as e:
        with _sync_lock:
            _sync_status["status"] = "error"
            _sync_status["detail"] = str(e)
    finally:
        db.close()


@router.post("/sync")
def trigger_product_sync(_=Depends(require_role("admin", "operator"))):
    with _sync_lock:
        if _sync_status["status"] == "running":
            return {"detail": "产品同步正在进行中"}
        _sync_status["status"] = "running"
        _sync_status["detail"] = ""
    thread = threading.Thread(target=_run_product_sync, daemon=True)
    thread.start()
    return {"detail": "产品同步已开始"}


@router.get("/sync/status")
def product_sync_status(_=Depends(require_role("admin", "operator"))):
    with _sync_lock:
        return dict(_sync_status)
