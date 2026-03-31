from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import SkuMapping, Product
from app.schemas.sku_mapping import SkuMappingOut, SkuMappingUpdate
from app.utils.deps import get_current_user, require_role

router = APIRouter(tags=["sku-mappings"])


@router.get("/api/shops/{shop_id}/sku-mappings", response_model=list[SkuMappingOut])
def list_shop_sku_mappings(shop_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(SkuMapping).filter(SkuMapping.shop_id == shop_id).all()


@router.put("/api/sku-mappings/{mapping_id}", response_model=SkuMappingOut)
def update_sku_mapping(mapping_id: int, data: SkuMappingUpdate, db: Session = Depends(get_db), _=Depends(require_role("admin", "operator"))):
    mapping = db.query(SkuMapping).filter(SkuMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="SKU mapping not found")
    if data.product_sku == "":
        mapping.product_id = None
    else:
        product = db.query(Product).filter(Product.sku == data.product_sku).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product with SKU '{data.product_sku}' not found")
        mapping.product_id = product.id
    db.commit()
    db.refresh(mapping)
    return mapping
