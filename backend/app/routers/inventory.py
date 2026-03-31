from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.inventory import Inventory
from app.schemas.inventory import InventoryOut
from app.utils.deps import get_current_user

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryOut])
def list_inventory(shop_id: Optional[int] = Query(None), db: Session = Depends(get_db), _=Depends(get_current_user)):
    query = db.query(Inventory)
    if shop_id:
        query = query.filter(Inventory.shop_id == shop_id)
    return query.all()


@router.get("/low-stock", response_model=list[InventoryOut])
def low_stock_alerts(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Inventory).filter(
        (Inventory.stock_fbs + Inventory.stock_fbw) < Inventory.low_stock_threshold
    ).all()
