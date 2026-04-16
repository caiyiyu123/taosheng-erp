from datetime import datetime, timezone, date
from sqlalchemy import String, Float, Integer, DateTime, Date, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class CommissionTable(Base):
    __tablename__ = "commission_tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    filename: Mapped[str] = mapped_column(String(200), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    rates: Mapped[list["CommissionRate"]] = relationship(
        back_populates="table", cascade="all, delete-orphan"
    )


class CommissionRate(Base):
    __tablename__ = "commission_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("commission_tables.id", ondelete="CASCADE")
    )
    category: Mapped[str] = mapped_column(String(200), default="")
    product_name: Mapped[str] = mapped_column(String(200), default="")
    rate: Mapped[float] = mapped_column(Float, default=0.0)
    extra_rates: Mapped[dict] = mapped_column(JSON, default=dict)
    table: Mapped["CommissionTable"] = relationship(back_populates="rates")


class ShippingTemplate(Base):
    __tablename__ = "shipping_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    rates: Mapped[list["ShippingRate"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class ShippingRate(Base):
    __tablename__ = "shipping_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("shipping_templates.id", ondelete="CASCADE")
    )
    density_min: Mapped[float] = mapped_column(Float, default=0.0)
    density_max: Mapped[float] = mapped_column(Float, default=0.0)
    price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    template: Mapped["ShippingTemplate"] = relationship(back_populates="rates")
