from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    wb_order_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"))
    order_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    total_price: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    customer_name: Mapped[str] = mapped_column(String(200), default="")
    delivery_address: Mapped[str] = mapped_column(Text, default="")
    warehouse_name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", lazy="selectin")
    status_logs: Mapped[list["OrderStatusLog"]] = relationship(back_populates="order", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"))
    wb_product_id: Mapped[str] = mapped_column(String(100), default="")
    product_name: Mapped[str] = mapped_column(String(500), default="")
    sku: Mapped[str] = mapped_column(String(200), default="")
    barcode: Mapped[str] = mapped_column(String(100), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    logistics_cost: Mapped[float] = mapped_column(Float, default=0.0)
    order: Mapped["Order"] = relationship(back_populates="items")


class OrderStatusLog(Base):
    __tablename__ = "order_status_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"))
    status: Mapped[str] = mapped_column(String(50))
    wb_status: Mapped[str] = mapped_column(String(100), default="")
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    note: Mapped[str] = mapped_column(Text, default="")
    order: Mapped["Order"] = relationship(back_populates="status_logs")
