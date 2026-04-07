import threading
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pydantic import BaseModel
from app.database import get_db, SessionLocal
from app.models.shop import Shop
from app.models.setting import SystemSetting
from app.schemas.shop import ShopCreate, ShopUpdate, ShopOut
from app.utils.security import encrypt_token, decrypt_token
from app.utils.deps import require_role, get_current_user, get_accessible_shop_ids, require_module

router = APIRouter(prefix="/api/shops", tags=["shops"])

# Track running sync tasks: shop_id → {"status": "running"|"done"|"error", "detail": str}
_sync_status: dict[int, dict] = {}
_sync_lock = threading.Lock()


@router.get("", response_model=list[ShopOut])
def list_shops(db: Session = Depends(get_db), shop_ids: list[int] | None = Depends(get_accessible_shop_ids)):
    query = db.query(Shop)
    if shop_ids is not None:
        query = query.filter(Shop.id.in_(shop_ids))
    return query.all()


class ExchangeRateBody(BaseModel):
    rate: float


@router.get("/exchange-rate")
def get_exchange_rate(db: Session = Depends(get_db), _=Depends(require_role("admin", "operator"))):
    setting = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate_cny_rub").first()
    rate = float(setting.value) if setting else 0
    return {"rate": rate}


@router.put("/exchange-rate")
def set_exchange_rate(body: ExchangeRateBody, db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    setting = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate_cny_rub").first()
    if setting:
        setting.value = str(body.rate)
    else:
        setting = SystemSetting(key="exchange_rate_cny_rub", value=str(body.rate))
        db.add(setting)
    db.commit()
    return {"rate": body.rate}


@router.post("", response_model=ShopOut, status_code=status.HTTP_201_CREATED)
def create_shop(data: ShopCreate, db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    shop = Shop(name=data.name, type=data.type, api_token=encrypt_token(data.api_token))
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop


@router.put("/{shop_id}", response_model=ShopOut)
def update_shop(shop_id: int, data: ShopUpdate, db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    if data.name is not None:
        shop.name = data.name
    if data.type is not None:
        shop.type = data.type
    if data.api_token is not None:
        shop.api_token = encrypt_token(data.api_token)
    if data.is_active is not None:
        shop.is_active = data.is_active
    db.commit()
    db.refresh(shop)
    return shop


@router.delete("/{shop_id}")
def delete_shop(shop_id: int, db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    from app.models.order import Order, OrderItem, OrderStatusLog
    from app.models.inventory import Inventory
    from app.models.ad import AdCampaign, AdDailyStat
    from app.models.product import SkuMapping, ShopProduct

    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Delete all related data
    order_ids = [o.id for o in db.query(Order.id).filter(Order.shop_id == shop_id).all()]
    if order_ids:
        db.query(OrderStatusLog).filter(OrderStatusLog.order_id.in_(order_ids)).delete(synchronize_session=False)
        db.query(OrderItem).filter(OrderItem.order_id.in_(order_ids)).delete(synchronize_session=False)
        db.query(Order).filter(Order.shop_id == shop_id).delete(synchronize_session=False)

    campaign_ids = [c.id for c in db.query(AdCampaign.id).filter(AdCampaign.shop_id == shop_id).all()]
    if campaign_ids:
        db.query(AdDailyStat).filter(AdDailyStat.campaign_id.in_(campaign_ids)).delete(synchronize_session=False)
        db.query(AdCampaign).filter(AdCampaign.shop_id == shop_id).delete(synchronize_session=False)

    db.query(Inventory).filter(Inventory.shop_id == shop_id).delete(synchronize_session=False)
    db.query(SkuMapping).filter(SkuMapping.shop_id == shop_id).delete(synchronize_session=False)
    db.query(ShopProduct).filter(ShopProduct.shop_id == shop_id).delete(synchronize_session=False)

    db.delete(shop)
    db.commit()
    return {"detail": "Shop and all related data deleted"}


from app.services.sync import sync_shop_orders, sync_shop_inventory, sync_shop_ads, sync_shop_products


def _run_sync(shop_id: int):
    """Run sync in background thread with its own DB session."""
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not shop:
            with _sync_lock:
                _sync_status[shop_id] = {"status": "error", "detail": "Shop not found"}
            return
        cards = sync_shop_orders(db, shop)
        sync_shop_inventory(db, shop)
        sync_shop_ads(db, shop, cards=cards)
        sync_shop_products(db, shop, cards=cards)
        with _sync_lock:
            _sync_status[shop_id] = {"status": "done", "detail": f"Sync completed for {shop.name}"}
    except Exception as e:
        with _sync_lock:
            _sync_status[shop_id] = {"status": "error", "detail": str(e)}
    finally:
        db.close()


@router.post("/{shop_id}/sync")
def trigger_sync(shop_id: int, db: Session = Depends(get_db), _=Depends(require_role("admin", "operator"))):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    with _sync_lock:
        current = _sync_status.get(shop_id)
        if current and current["status"] == "running":
            return {"status": "running", "detail": "Sync already in progress"}
        _sync_status[shop_id] = {"status": "running", "detail": ""}

    thread = threading.Thread(target=_run_sync, args=(shop_id,), daemon=True)
    thread.start()
    return {"status": "running", "detail": "Sync started"}


@router.get("/{shop_id}/sync-status")
def get_sync_status(shop_id: int, _=Depends(require_role("admin", "operator"))):
    with _sync_lock:
        info = _sync_status.get(shop_id)
    if not info:
        return {"status": "idle", "detail": ""}
    return info
