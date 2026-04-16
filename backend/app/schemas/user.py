from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel

RoleType = Literal["admin", "operator"]


class UserCreate(BaseModel):
    username: str
    display_name: str = ""
    password: str
    role: RoleType = "operator"
    shop_ids: list[int] = []
    permissions: list[str] = []


class UserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[RoleType] = None
    is_active: Optional[bool] = None
    shop_ids: Optional[list[int]] = None
    permissions: Optional[list[str]] = None


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str = ""
    role: str
    is_active: bool
    created_at: datetime
    shop_ids: list[int] = []
    permissions: list[str] = []

    class Config:
        from_attributes = True
