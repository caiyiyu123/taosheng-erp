from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    image: Mapped[str] = mapped_column(String(500), default="")
    purchase_price: Mapped[float] = mapped_column(Float, default=0.0)
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    length: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[float] = mapped_column(Float, default=0.0)
    height: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    sku_mappings: Mapped[list["SkuMapping"]] = relationship(back_populates="product")


class ShopProduct(Base):
    """WB store product — synced from Content API + Feedbacks API."""
    __tablename__ = "shop_products"
    __table_args__ = (UniqueConstraint("shop_id", "nm_id", name="uq_shop_nm"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"), index=True)
    nm_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    vendor_code: Mapped[str] = mapped_column(String(200), default="")  # SKU
    image_url: Mapped[str] = mapped_column(String(500), default="")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    price_rub: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    discount: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    feedbacks_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class SkuMapping(Base):
    __tablename__ = "sku_mappings"
    __table_args__ = (UniqueConstraint("shop_id", "shop_sku", name="uq_shop_sku"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"))
    shop_sku: Mapped[str] = mapped_column(String(200))
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("products.id"), nullable=True)
    wb_nm_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    wb_product_name: Mapped[str] = mapped_column(String(500), default="")
    wb_image_url: Mapped[str] = mapped_column(String(500), default="")
    wb_barcode: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    product: Mapped[Optional["Product"]] = relationship(back_populates="sku_mappings")
