from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, Date, DateTime, Text, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class FinanceOrderRecord(Base):
    __tablename__ = "finance_order_records"
    __table_args__ = (
        UniqueConstraint("shop_id", "srid", name="uq_finance_shop_srid"),
        Index("ix_finance_shop_sale_date", "shop_id", "sale_date"),
        Index("ix_finance_shop_mapping", "shop_id", "has_sku_mapping"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"), index=True)
    srid: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(10))
    order_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    sale_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    nm_id: Mapped[str] = mapped_column(String(50), default="")
    shop_sku: Mapped[str] = mapped_column(String(200), default="")
    product_name: Mapped[str] = mapped_column(String(500), default="")
    barcode: Mapped[str] = mapped_column(String(100), default="")
    category: Mapped[str] = mapped_column(String(200), default="")
    size: Mapped[str] = mapped_column(String(50), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    return_quantity: Mapped[int] = mapped_column(Integer, default=0)
    retail_price: Mapped[float] = mapped_column(Float, default=0.0)
    sold_price: Mapped[float] = mapped_column(Float, default=0.0)
    commission_rate: Mapped[float] = mapped_column(Float, default=0.0)
    commission_amount: Mapped[float] = mapped_column(Float, default=0.0)
    net_to_seller: Mapped[float] = mapped_column(Float, default=0.0)
    delivery_fee: Mapped[float] = mapped_column(Float, default=0.0)
    fine: Mapped[float] = mapped_column(Float, default=0.0)
    storage_fee: Mapped[float] = mapped_column(Float, default=0.0)
    deduction: Mapped[float] = mapped_column(Float, default=0.0)
    purchase_cost: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    has_sku_mapping: Mapped[bool] = mapped_column(Boolean, default=False)
    warehouse: Mapped[str] = mapped_column(String(200), default="")
    country: Mapped[str] = mapped_column(String(10), default="")
    sale_type: Mapped[str] = mapped_column(String(50), default="")
    has_return_row: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class FinanceOtherFee(Base):
    __tablename__ = "finance_other_fees"
    __table_args__ = (
        Index("ix_other_fee_shop_date", "shop_id", "sale_date"),
        Index("ix_other_fee_shop_type", "shop_id", "fee_type"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"), index=True)
    currency: Mapped[str] = mapped_column(String(10))
    sale_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fee_type: Mapped[str] = mapped_column(String(50))
    fee_description: Mapped[str] = mapped_column(String(500), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    raw_row: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class FinanceSyncLog(Base):
    __tablename__ = "finance_sync_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"), index=True)
    triggered_by: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="running")
    rows_fetched: Mapped[int] = mapped_column(Integer, default=0)
    orders_merged: Mapped[int] = mapped_column(Integer, default=0)
    other_fees_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
