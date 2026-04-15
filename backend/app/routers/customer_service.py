import httpx
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.shop import Shop
from app.models.product import ShopProduct
from app.utils.deps import get_current_user, get_accessible_shop_ids, require_module
from app.utils.security import decrypt_token
from app.services.wb_api import (
    fetch_feedbacks, reply_feedback,
    fetch_questions, reply_question,
    fetch_chats, fetch_chat_messages, send_chat_message,
)

router = APIRouter(prefix="/api/customer-service", tags=["customer-service"])


def _get_token(db: Session, shop_id: int, accessible_shops: list[int] | None) -> str:
    if accessible_shops is not None and shop_id not in accessible_shops:
        raise HTTPException(status_code=403, detail="No access to this shop")
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return decrypt_token(shop.api_token)


# ── Feedbacks ──

@router.get("/feedbacks")
def list_feedbacks(
    shop_id: int = Query(...),
    is_answered: bool = Query(False),
    take: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("customer_service")),
):
    token = _get_token(db, shop_id, accessible_shops)
    result = fetch_feedbacks(token, is_answered, take, skip)
    items = result.get("data", {}).get("feedbacks", [])
    _attach_images(db, shop_id, items)
    return result


def _attach_images(db: Session, shop_id: int, items: list):
    """Attach image_url from ShopProduct table to feedback/question items."""
    nm_ids = [str(item.get("productDetails", {}).get("nmId", "")) for item in items if item.get("productDetails")]
    nm_ids = [n for n in nm_ids if n]
    if not nm_ids:
        return
    products = db.query(ShopProduct.nm_id, ShopProduct.image_url).filter(
        ShopProduct.shop_id == shop_id, ShopProduct.nm_id.in_([int(n) for n in nm_ids])
    ).all()
    img_map = {str(p.nm_id): p.image_url for p in products if p.image_url}
    for item in items:
        nm = str(item.get("productDetails", {}).get("nmId", ""))
        item["_imageUrl"] = img_map.get(nm, "")


class TranslateBody(BaseModel):
    text: str


@router.post("/translate")
def translate_text(
    body: TranslateBody,
    _=Depends(require_module("customer_service")),
):
    """Translate a single text from Russian to Chinese."""
    if not body.text.strip():
        return {"translated": ""}
    try:
        resp = httpx.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "ru", "tl": "zh-CN", "dt": "t", "q": body.text},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            translated = "".join(part[0] for part in data[0] if part[0])
            return {"translated": translated}
    except Exception as e:
        print(f"[Translate] Error: {e}")
    return {"translated": ""}


class ReplyBody(BaseModel):
    shop_id: int
    id: str
    text: str


@router.post("/feedbacks/reply")
def do_reply_feedback(
    body: ReplyBody,
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("customer_service")),
):
    token = _get_token(db, body.shop_id, accessible_shops)
    result = reply_feedback(token, body.id, body.text)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Reply failed"))
    return {"detail": "ok"}


# ── Questions ──

@router.get("/questions")
def list_questions(
    shop_id: int = Query(...),
    is_answered: bool = Query(False),
    take: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("customer_service")),
):
    token = _get_token(db, shop_id, accessible_shops)
    result = fetch_questions(token, is_answered, take, skip)
    items = result.get("data", {}).get("questions", [])
    _attach_images(db, shop_id, items)
    return result


@router.post("/questions/reply")
def do_reply_question(
    body: ReplyBody,
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("customer_service")),
):
    token = _get_token(db, body.shop_id, accessible_shops)
    result = reply_question(token, body.id, body.text)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Reply failed"))
    return {"detail": "ok"}


# ── Chats ──

@router.get("/chats")
def list_chats(
    shop_id: int = Query(...),
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("customer_service")),
):
    token = _get_token(db, shop_id, accessible_shops)
    return fetch_chats(token)


@router.get("/chats/{chat_id}/messages")
def get_chat_messages(
    chat_id: str,
    shop_id: int = Query(...),
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("customer_service")),
):
    token = _get_token(db, shop_id, accessible_shops)
    return fetch_chat_messages(token, chat_id)


class ChatMessageBody(BaseModel):
    shop_id: int
    text: str


@router.post("/chats/{chat_id}/message")
def do_send_chat_message(
    chat_id: str,
    body: ChatMessageBody,
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("customer_service")),
):
    token = _get_token(db, body.shop_id, accessible_shops)
    result = send_chat_message(token, chat_id, body.text)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Send failed"))
    return {"detail": "ok"}
