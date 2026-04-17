from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.shop import Shop
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.utils.security import hash_password
from app.utils.deps import require_role, get_current_user

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/names")
def list_user_names(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Return all user display names (or username fallback). Available to any authenticated user."""
    users = db.query(User).all()
    return [{"display_name": u.display_name, "username": u.username} for u in users]


def _user_to_out(user: User) -> dict:
    """Convert User model to dict with shop_ids and permissions."""
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or "",
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "shop_ids": [s.id for s in user.shops],
        "permissions": user.permissions.split(",") if user.permissions else [],
    }


def _set_user_shops(db: Session, user: User, shop_ids: list[int]):
    """Set user's shop associations."""
    if shop_ids:
        shops = db.query(Shop).filter(Shop.id.in_(shop_ids)).all()
        user.shops = shops
    else:
        user.shops = []


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    users = db.query(User).all()
    return [_user_to_out(u) for u in users]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        username=data.username,
        display_name=data.display_name or "",
        password_hash=hash_password(data.password),
        role=data.role,
        permissions=",".join(data.permissions) if data.permissions else "",
    )
    db.add(user)
    db.flush()
    _set_user_shops(db, user, data.shop_ids)
    db.commit()
    db.refresh(user)
    return _user_to_out(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.username is not None:
        user.username = data.username
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.password is not None:
        user.password_hash = hash_password(data.password)
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.permissions is not None:
        user.permissions = ",".join(data.permissions) if data.permissions else ""
    if data.shop_ids is not None:
        _set_user_shops(db, user, data.shop_ids)
    db.commit()
    db.refresh(user)
    return _user_to_out(user)


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role("admin"))):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"detail": "User deleted"}
