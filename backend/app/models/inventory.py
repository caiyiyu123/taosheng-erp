from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Inventory(Base):
    __tablename__ = "inventories"
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"), index=True)
    wb_product_id: Mapped[str] = mapped_column(String(100), default="")
    product_name: Mapped[str] = mapped_column(String(500), default="")
    sku: Mapped[str] = mapped_column(String(200), default="")
    barcode: Mapped[str] = mapped_column(String(100), default="")
    stock_fbs: Mapped[int] = mapped_column(Integer, default=0)
    stock_fbw: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
