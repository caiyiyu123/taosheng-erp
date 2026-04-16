from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Table, Column, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


# 用户-店铺关联表
user_shops = Table(
    "user_shops",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("shop_id", Integer, ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(50), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="operator")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    permissions: Mapped[str] = mapped_column(Text, default="")  # 逗号分隔的模块名
    shops = relationship("Shop", secondary=user_shops, lazy="selectin")

    # 全部可用模块
    ALL_MODULES = ["dashboard", "orders", "products", "ads", "finance", "customer_service", "commission_shipping", "inventory", "shops"]

    def has_permission(self, module: str) -> bool:
        if self.role == "admin":
            return True
        if not self.permissions:
            return False
        return module in self.permissions.split(",")
