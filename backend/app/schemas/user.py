from typing import Literal, Optional
from pydantic import BaseModel

RoleType = Literal["admin", "operator", "viewer"]


class UserCreate(BaseModel):
    username: str
    password: str
    role: RoleType = "viewer"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[RoleType] = None
    is_active: Optional[bool] = None
