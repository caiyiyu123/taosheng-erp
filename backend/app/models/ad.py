from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, DateTime, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class AdCampaign(Base):
    __tablename__ = "ad_campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"))
    wb_advert_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500), default="")
    type: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=0)
    daily_budget: Mapped[float] = mapped_column(Float, default=0.0)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    daily_stats: Mapped[list["AdDailyStat"]] = relationship(back_populates="campaign", lazy="select")


class AdDailyStat(Base):
    __tablename__ = "ad_daily_stats"
    __table_args__ = (
        UniqueConstraint("campaign_id", "nm_id", "date", name="uq_campaign_nm_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("ad_campaigns.id"), index=True)
    nm_id: Mapped[int] = mapped_column(Integer, default=0)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    cpc: Mapped[float] = mapped_column(Float, default=0.0)
    spend: Mapped[float] = mapped_column(Float, default=0.0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    order_amount: Mapped[float] = mapped_column(Float, default=0.0)
    atbs: Mapped[int] = mapped_column(Integer, default=0)
    cr: Mapped[float] = mapped_column(Float, default=0.0)
    campaign: Mapped["AdCampaign"] = relationship(back_populates="daily_stats")
