# 订单同步重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写订单同步逻辑，FBS 和 FBW 独立函数处理，价格创建时一次性确定，消除回填步骤。

**Architecture:** `sync_shop_orders` 作为唯一入口，获取共享数据后分别调用 `_sync_fbs_orders` 和 `_sync_fbw_orders`。删除 `_backfill_order_prices` 和 `_update_order_rub_prices`。保留 `_update_order_statuses` 仅更新 FBS 活跃订单状态。

**Tech Stack:** Python, FastAPI, SQLAlchemy, httpx (WB API)

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/app/services/sync.py` | 重写 63-868 行 | `sync_shop_orders` + `_sync_fbs_orders`(新) + `_sync_fbw_orders`(新) + `_update_order_statuses`(保留)。删除 `_backfill_order_prices`(710-798) 和 `_update_order_rub_prices`(801-868) |
| `backend/app/services/wb_api.py` | 不改 | `fetch_statistics_orders`(flag=0+1) 和 `fetch_statistics_sales` 已就绪 |
| `backend/app/routers/orders.py` | 不改 | 路由层不受影响 |
| `backend/app/models/order.py` | 不改 | 模型不变 |

---

### Task 1: 重写 sync_shop_orders 入口函数

**Files:**
- Modify: `backend/app/services/sync.py:1-17` (imports)
- Modify: `backend/app/services/sync.py:63-334` (替换整个 sync_shop_orders)

- [ ] **Step 1: 更新 imports**

将 `sync.py` 顶部 imports 替换为：

```python
from datetime import datetime, timezone, timedelta, date
from sqlalchemy.orm import Session

from app.models.shop import Shop
from app.models.order import Order, OrderItem, OrderStatusLog
from app.models.inventory import Inventory
from app.models.product import SkuMapping
from app.models.ad import AdCampaign, AdDailyStat
from app.utils.security import decrypt_token
from app.services.wb_api import (
    fetch_new_orders, fetch_orders, fetch_order_statuses,
    fetch_warehouses, fetch_stocks, fetch_cards,
    fetch_statistics_orders, fetch_statistics_sales, fetch_report_detail,
    fetch_ad_campaign_ids, fetch_ad_details, fetch_ad_fullstats,
    fetch_ad_campaign_names, fetch_ad_budgets_batch,
    fetch_product_ratings, fetch_product_prices,
)

# WB supplier status → system status
SUPPLIER_STATUS_MAP = {
    "new": "pending",
    "confirm": "pending",
    "complete": "shipped",
    "cancel": "cancelled",
}

# WB platform status → system status
WB_STATUS_MAP = {
    "waiting": "pending",
    "sorted": "in_transit",
    "sold": "completed",
    "canceled": "cancelled",
    "canceled_by_client": "rejected",
    "declined_by_client": "cancelled",
    "defect": "returned",
    "ready_for_pickup": "in_transit",
    "delivered": "completed",
}

# Currency code mapping (WB uses numeric codes)
CURRENCY_MAP = {
    643: "RUB",
    840: "USD",
    978: "EUR",
    933: "BYN",
    398: "KZT",
    156: "CNY",
}


def _resolve_status(supplier_status: str, wb_status: str) -> str:
    if wb_status and wb_status in WB_STATUS_MAP:
        return WB_STATUS_MAP[wb_status]
    if supplier_status and supplier_status in SUPPLIER_STATUS_MAP:
        return SUPPLIER_STATUS_MAP[supplier_status]
    return "pending"
```

- [ ] **Step 2: 重写 sync_shop_orders**

删除旧的 `sync_shop_orders`（第 63-334 行），替换为：

```python
def _build_card_map(cards: list[dict]) -> dict:
    """Build nmId → card info lookup from product cards."""
    nm_card_map = {}
    for card in cards:
        nm_id = card.get("nmID")
        if nm_id:
            nm_card_map[nm_id] = {
                "name": card.get("title", ""),
                "vendorCode": card.get("vendorCode", ""),
                "photos": card.get("photos", []),
            }
    return nm_card_map


def sync_shop_orders(db: Session, shop: Shop) -> list[dict]:
    """Sync orders for a shop. Returns product cards for reuse by other sync functions.

    Flow:
      1. Fetch shared data (cards, statistics)
      2. Sync FBS orders from Marketplace API
      3. Sync FBW orders from Statistics + Report Detail
      4. Update FBS order statuses
    """
    api_token = decrypt_token(shop.api_token)

    # 1. Fetch shared data
    cards = fetch_cards(api_token)
    nm_card_map = _build_card_map(cards)
    stat_orders = fetch_statistics_orders(api_token)
    stat_sales = fetch_statistics_sales(api_token)

    # 2. Sync FBS orders
    _sync_fbs_orders(db, shop, api_token, nm_card_map, stat_orders)

    # 3. Sync FBW orders
    _sync_fbw_orders(db, shop, api_token, nm_card_map, stat_orders, stat_sales)

    # 4. Update statuses for active FBS orders
    terminal_statuses = ("completed", "cancelled", "returned", "rejected")
    active_orders = db.query(Order).filter(
        Order.shop_id == shop.id,
        Order.order_type == "FBS",
        ~Order.status.in_(terminal_statuses),
    ).all()
    active_wb_ids = [int(o.wb_order_id) for o in active_orders if o.wb_order_id.isdigit()]
    if active_wb_ids:
        _update_order_statuses(db, shop.id, api_token, active_wb_ids)

    shop.last_sync_at = datetime.now(timezone.utc)
    db.commit()
    return cards
```

- [ ] **Step 3: 验证编译**

Run: `cd backend && python -c "import py_compile; py_compile.compile('app/services/sync.py', doraise=True); print('OK')"`

此步预期会失败（`_sync_fbs_orders` 和 `_sync_fbw_orders` 尚未定义），确认错误信息即可。

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/sync.py
git commit -m "refactor: 重写 sync_shop_orders 入口函数，FBS/FBW 分离架构"
```

---

### Task 2: 实现 _sync_fbs_orders

**Files:**
- Modify: `backend/app/services/sync.py` (在 sync_shop_orders 之后插入)

- [ ] **Step 1: 实现 FBS 价格解析辅助函数**

在 `sync_shop_orders` 之后插入：

```python
def _parse_fbs_prices(raw: dict) -> tuple[float, float, str]:
    """Parse price_rub, total_price, currency from a Marketplace API order.

    WB returns prices in minor units (kopecks/fen).
    Handles multi-currency: if order currency is not RUB but converted is RUB,
    use converted price for price_rub.

    Returns: (price_rub, total_price, currency)
    """
    original_minor = (
        raw.get("salePrice", 0)
        or raw.get("finalPrice", 0)
        or raw.get("price", 0)
    )
    converted_minor = (
        raw.get("convertedFinalPrice", 0)
        or raw.get("convertedPrice", 0)
    )
    order_currency = raw.get("currencyCode", 643)
    converted_currency = raw.get("convertedCurrencyCode", 0)

    if converted_currency and converted_currency != order_currency:
        if converted_currency == 643:
            # Order in foreign currency, converted to RUB
            price_rub = converted_minor / 100.0
            total_price = converted_minor / 100.0
            currency = "RUB"
        else:
            # Order in RUB, converted to foreign (e.g. CNY for cross-border)
            price_rub = original_minor / 100.0
            total_price = converted_minor / 100.0
            currency = CURRENCY_MAP.get(converted_currency, "CNY")
    else:
        # Single currency
        price_rub = original_minor / 100.0
        total_price = original_minor / 100.0
        currency = CURRENCY_MAP.get(order_currency, "RUB")

    return price_rub, total_price, currency
```

- [ ] **Step 2: 实现 _sync_fbs_orders 主函数**

```python
def _sync_fbs_orders(db: Session, shop: Shop, api_token: str,
                     nm_card_map: dict, stat_orders: list[dict]):
    """Sync FBS orders from Marketplace API (90 days).

    Price is resolved at insert time:
      1. From Marketplace API (salePrice/convertedFinalPrice)
      2. Fallback: from Statistics Orders (by srid match)
    """
    # Fetch FBS orders from Marketplace API
    fbs_date_from = datetime.now(timezone.utc) - timedelta(days=90)
    historical = fetch_orders(api_token, date_from=fbs_date_from)
    new_orders = fetch_new_orders(api_token)

    # Merge: deduplicate by id, new orders take priority
    all_raw = {}
    for raw in historical:
        oid = raw.get("id")
        if oid:
            all_raw[oid] = raw
    for raw in new_orders:
        oid = raw.get("id")
        if oid:
            all_raw[oid] = raw

    # Build srid → Statistics lookup for price fallback
    stat_by_srid = {}
    for o in stat_orders:
        srid = o.get("srid", "")
        if srid:
            stat_by_srid[srid] = o

    created = 0
    updated = 0

    for wb_id, raw in all_raw.items():
        wb_order_id = str(wb_id)
        rid = raw.get("rid", "")

        # Parse prices
        price_rub, total_price, currency = _parse_fbs_prices(raw)

        # Fallback: if price_rub is 0, try Statistics by srid
        if price_rub == 0 and rid:
            stat = stat_by_srid.get(rid)
            if stat:
                price_rub = float(stat.get("finishedPrice", 0) or stat.get("priceWithDisc", 0) or 0)
                if total_price == 0:
                    total_price = price_rub

        # Product info
        nm_id = raw.get("nmId", 0)
        article = raw.get("article", "")
        skus = raw.get("skus", [])
        barcode = skus[0] if skus else ""
        card_info = nm_card_map.get(nm_id, {})
        product_name = card_info.get("name", article)
        sku = article or card_info.get("vendorCode", "") or barcode
        photos = card_info.get("photos", [])
        image_url = photos[0].get("c246x328", "") if photos else ""

        # Parse created time
        created_at_str = raw.get("createdAt", "")
        order_created = None
        if created_at_str:
            try:
                order_created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        # Determine order type from deliveryType
        delivery_type = raw.get("deliveryType", "fbs")
        order_type = delivery_type.upper() if delivery_type else "FBS"

        # Check if exists
        existing = db.query(Order).filter(Order.wb_order_id == wb_order_id).first()
        if existing:
            changed = False
            if existing.price_rub == 0 and price_rub > 0:
                existing.price_rub = price_rub
                changed = True
            if existing.total_price == 0 and total_price > 0:
                existing.total_price = total_price
                existing.currency = currency
                changed = True
            if rid and not existing.srid:
                existing.srid = rid
                changed = True
            if order_created and existing.created_at:
                api_time = order_created.replace(tzinfo=None)
                if abs((api_time - existing.created_at).total_seconds()) > 5:
                    existing.created_at = api_time
                    changed = True
            if image_url:
                item = db.query(OrderItem).filter(
                    OrderItem.order_id == existing.id, OrderItem.image_url == ""
                ).first()
                if item:
                    item.image_url = image_url
            if not db.query(OrderItem).filter(OrderItem.order_id == existing.id).count():
                _create_order_item(db, existing.id, shop.id, nm_id, product_name,
                                   sku, barcode, image_url, total_price, nm_card_map)
            if changed:
                existing.updated_at = datetime.now(timezone.utc)
                updated += 1
            continue

        # Create new order
        order = Order(
            wb_order_id=wb_order_id,
            srid=rid,
            shop_id=shop.id,
            order_type=order_type,
            status="pending",
            total_price=total_price,
            price_rub=price_rub,
            currency=currency,
            warehouse_name=str(raw.get("warehouseId", 0)),
            created_at=order_created or datetime.now(timezone.utc),
        )
        db.add(order)
        db.flush()

        db.add(OrderStatusLog(order_id=order.id, status="pending", wb_status="new"))
        _create_order_item(db, order.id, shop.id, nm_id, product_name,
                           sku, barcode, image_url, total_price, nm_card_map)
        created += 1

    print(f"[Sync] FBS: created {created}, updated {updated} for shop {shop.id}")
```

- [ ] **Step 3: 实现共享的 _create_order_item 辅助函数**

在 `_parse_fbs_prices` 之前插入：

```python
def _create_order_item(db: Session, order_id: int, shop_id: int,
                       nm_id: int, product_name: str, sku: str,
                       barcode: str, image_url: str, price: float,
                       nm_card_map: dict):
    """Create OrderItem and auto-create SkuMapping if needed."""
    db.add(OrderItem(
        order_id=order_id,
        wb_product_id=str(nm_id),
        product_name=product_name,
        sku=sku,
        barcode=barcode,
        image_url=image_url,
        quantity=1,
        price=price,
    ))
    if sku:
        existing_mapping = db.query(SkuMapping).filter(
            SkuMapping.shop_id == shop_id, SkuMapping.shop_sku == sku
        ).first()
        if not existing_mapping:
            db.add(SkuMapping(
                shop_id=shop_id, shop_sku=sku,
                wb_nm_id=str(nm_id) if nm_id else None,
                wb_product_name=product_name, wb_image_url=image_url,
                wb_barcode=barcode,
            ))
        else:
            if nm_id and not existing_mapping.wb_nm_id:
                existing_mapping.wb_nm_id = str(nm_id)
            if image_url and not existing_mapping.wb_image_url:
                existing_mapping.wb_image_url = image_url
```

- [ ] **Step 4: 验证编译**

Run: `cd backend && python -c "import py_compile; py_compile.compile('app/services/sync.py', doraise=True); print('OK')"`

预期仍会失败（`_sync_fbw_orders` 未定义），确认仅此一个错误。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sync.py
git commit -m "feat: 实现 _sync_fbs_orders 独立 FBS 同步函数"
```

---

### Task 3: 实现 _sync_fbw_orders

**Files:**
- Modify: `backend/app/services/sync.py` (在 _sync_fbs_orders 之后插入)

- [ ] **Step 1: 实现图片查找辅助函数**

```python
def _build_image_lookup(db: Session) -> tuple[dict, dict]:
    """Build SKU/barcode → image_url lookup from existing data."""
    sku_img = {}
    barcode_img = {}
    for sku_val, bc_val, img_val in db.query(
        OrderItem.sku, OrderItem.barcode, OrderItem.image_url
    ).filter(OrderItem.image_url != "").distinct().all():
        if sku_val and sku_val not in sku_img:
            sku_img[sku_val] = img_val
        if bc_val and bc_val not in barcode_img:
            barcode_img[bc_val] = img_val
    for m in db.query(SkuMapping).filter(SkuMapping.wb_image_url != "").all():
        if m.shop_sku and m.shop_sku not in sku_img:
            sku_img[m.shop_sku] = m.wb_image_url
        if m.wb_barcode and m.wb_barcode not in barcode_img:
            barcode_img[m.wb_barcode] = m.wb_image_url
    return sku_img, barcode_img
```

- [ ] **Step 2: 实现 _sync_fbw_orders 主函数 — 数据收集阶段**

```python
def _sync_fbw_orders(db: Session, shop: Shop, api_token: str, nm_card_map: dict,
                     stat_orders: list[dict], stat_sales: list[dict]):
    """Sync FBW orders from triple data sources.

    Source priority: Statistics Orders > Statistics Sales > Report Detail.
    All merged by srid into a single dict before writing to DB.
    """
    import re
    from collections import defaultdict

    HEX_SRID_RE = re.compile(r"[ri][0-9a-f]{20,}", re.I)

    # Pre-load existing data
    existing_fbo = db.query(Order).filter(
        Order.shop_id == shop.id, Order.wb_order_id.like("fbo_%")
    ).all()
    existing_by_wb_id = {o.wb_order_id: o for o in existing_fbo}
    existing_by_srid = {o.srid: o for o in existing_fbo if o.srid}

    # (nm_id, date) index for numeric→hex srid dedup
    fbo_item_nm = {}
    if existing_fbo:
        for row in db.query(OrderItem.order_id, OrderItem.wb_product_id).filter(
            OrderItem.order_id.in_([o.id for o in existing_fbo])
        ).all():
            fbo_item_nm[row[0]] = row[1]
    existing_by_nm_date = {}
    for o in existing_fbo:
        nm_str = fbo_item_nm.get(o.id, "")
        if nm_str and o.created_at:
            existing_by_nm_date[(nm_str, o.created_at.strftime("%Y-%m-%d"))] = o

    # FBS srids set (to exclude FBS from Report Detail)
    fbs_srids = set(
        r[0] for r in db.query(Order.srid).filter(
            Order.shop_id == shop.id,
            ~Order.wb_order_id.like("fbo_%"),
            Order.srid != "",
        ).all()
    )

    # ── Collect FBW records from all sources into fbw_records[srid] ──

    fbw_records = {}  # srid → record dict

    # Source 1: Statistics Orders (highest priority, clear warehouseType)
    for o in stat_orders:
        if "WB" not in o.get("warehouseType", ""):
            continue
        srid = o.get("srid", "")
        if not srid or srid in fbs_srids:
            continue
        fbw_records[srid] = {
            "srid": srid,
            "order_dt": o.get("date", ""),
            "sale_dt": "",
            "nm_id": o.get("nmId", 0),
            "article": o.get("supplierArticle", ""),
            "barcode": o.get("barcode", ""),
            "product_name": o.get("subject", ""),
            "price": float(o.get("priceWithDisc", 0) or o.get("finishedPrice", 0) or 0),
            "warehouse": o.get("warehouseName", ""),
            "is_cancel": o.get("isCancel", False),
            "source": "statistics",
        }

    # Source 2: Statistics Sales (supplement for srids not in Source 1)
    for s in stat_sales:
        if "WB" not in s.get("warehouseType", ""):
            continue
        srid = s.get("srid", "")
        if not srid or srid in fbs_srids or srid in fbw_records:
            continue
        fbw_records[srid] = {
            "srid": srid,
            "order_dt": s.get("date", ""),
            "sale_dt": s.get("lastChangeDate", s.get("date", "")),
            "nm_id": s.get("nmId", 0),
            "article": s.get("supplierArticle", ""),
            "barcode": s.get("barcode", ""),
            "product_name": s.get("subject", ""),
            "price": float(s.get("priceWithDisc", 0) or s.get("finishedPrice", 0) or 0),
            "warehouse": s.get("warehouseName", ""),
            "is_cancel": str(s.get("saleID", "")).startswith("R"),
            "source": "sales",
        }

    # Source 3: Report Detail (fills 20-90 day gap)
    date_from = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_data = fetch_report_detail(api_token, date_from, date_to)
    print(f"[Sync] Report Detail: {len(report_data)} records for shop {shop.id}")

    # Group by srid
    srid_groups = defaultdict(list)
    for r in report_data:
        srid = r.get("srid", "")
        if srid:
            srid_groups[srid].append(r)

    for srid, records in srid_groups.items():
        if srid in fbs_srids or srid in fbw_records:
            continue

        # Classify via gi_box_type_name
        gi_values = {r.get("gi_box_type_name", "") for r in records} - {""}
        is_fbw_by_gi = any("FBW" in g.upper() or "FBO" in g.upper() for g in gi_values)
        is_fbs_by_gi = (
            not is_fbw_by_gi
            and any("маркетплейс" in g.lower() or "FBS" in g.upper() for g in gi_values)
        )
        if is_fbs_by_gi:
            continue

        # Find best record (prefer sale record with qty>0, price>0)
        best = None
        for r in records:
            if r.get("quantity", 0) > 0 and (r.get("retail_price_withdisc_rub", 0) or 0) > 0:
                best = r
                break

        if not best:
            if is_fbw_by_gi:
                for r in records:
                    if r.get("nm_id", 0) > 0:
                        best = r
                        break
            elif HEX_SRID_RE.search(srid):
                for r in records:
                    if r.get("nm_id", 0) > 0:
                        best = r
                        break
            if not best:
                continue

        # Aggregate product info
        nm_id = best.get("nm_id", 0)
        if not nm_id:
            for r in records:
                if r.get("nm_id", 0) > 0:
                    nm_id = r["nm_id"]
                    break
        article = best.get("sa_name", "")
        if not article:
            for r in records:
                if r.get("sa_name", ""):
                    article = r["sa_name"]
                    break

        fbw_records[srid] = {
            "srid": srid,
            "order_dt": best.get("order_dt", ""),
            "sale_dt": best.get("sale_dt", ""),
            "nm_id": nm_id,
            "article": article,
            "barcode": best.get("barcode", ""),
            "product_name": best.get("subject_name", ""),
            "price": float(best.get("retail_price_withdisc_rub", 0) or 0),
            "warehouse": best.get("office_name", ""),
            "is_cancel": False,
            "source": "report",
        }

    print(f"[Sync] FBW candidates: {len(fbw_records)} for shop {shop.id}")

    if not fbw_records:
        return

    # ── Write to DB ──

    sku_img, barcode_img = _build_image_lookup(db)
    created = 0
    updated_srid = 0

    for srid, rec in fbw_records.items():
        wb_order_id = f"fbo_{srid}"

        # Existing by wb_order_id → update price if needed
        existing = existing_by_wb_id.get(wb_order_id)
        if existing:
            if existing.total_price == 0 and rec["price"] > 0:
                existing.total_price = rec["price"]
                existing.price_rub = rec["price"]
                existing.updated_at = datetime.now(timezone.utc)
            if srid and not existing.srid:
                existing.srid = srid
            continue

        # Existing by srid
        if srid in existing_by_srid:
            continue

        # Hex srid dedup: upgrade numeric-srid order
        if rec["source"] == "report" and rec["nm_id"] and rec["order_dt"] and HEX_SRID_RE.search(srid):
            dup_key = (str(rec["nm_id"]), rec["order_dt"][:10])
            dup_order = existing_by_nm_date.get(dup_key)
            if dup_order and dup_order.srid != srid:
                old_wb_id = dup_order.wb_order_id
                dup_order.srid = srid
                dup_order.wb_order_id = wb_order_id
                if dup_order.total_price == 0 and rec["price"] > 0:
                    dup_order.total_price = rec["price"]
                    dup_order.price_rub = rec["price"]
                dup_order.updated_at = datetime.now(timezone.utc)
                existing_by_wb_id.pop(old_wb_id, None)
                existing_by_wb_id[wb_order_id] = dup_order
                existing_by_srid[srid] = dup_order
                updated_srid += 1
                continue

        # Parse order date
        order_created = None
        if rec["order_dt"]:
            try:
                order_created = datetime.fromisoformat(rec["order_dt"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        status = "cancelled" if rec["is_cancel"] else ("completed" if rec["sale_dt"] else "pending")
        nm_id = rec["nm_id"]
        article = rec["article"]
        barcode = rec["barcode"]
        card_info = nm_card_map.get(nm_id, {})
        product_name = rec["product_name"] or card_info.get("name", article)
        sku = article or card_info.get("vendorCode", "") or barcode
        photos = card_info.get("photos", [])
        image_url = photos[0].get("c246x328", "") if photos else ""
        if not image_url:
            image_url = sku_img.get(sku, "") or barcode_img.get(barcode, "")

        order = Order(
            wb_order_id=wb_order_id,
            srid=srid,
            shop_id=shop.id,
            order_type="FBW",
            status=status,
            total_price=rec["price"],
            price_rub=rec["price"],
            currency="RUB",
            warehouse_name=rec["warehouse"],
            created_at=order_created or datetime.now(timezone.utc),
        )
        db.add(order)
        db.flush()

        existing_by_wb_id[wb_order_id] = order
        existing_by_srid[srid] = order

        db.add(OrderStatusLog(
            order_id=order.id, status=status, wb_status=f"fbo_{rec['source']}",
        ))
        _create_order_item(db, order.id, shop.id, nm_id, product_name,
                           sku, barcode, image_url, rec["price"], nm_card_map)
        created += 1
        if created % 500 == 0:
            db.flush()

    print(f"[Sync] FBW: created {created}, updated srid {updated_srid} for shop {shop.id}")
```

- [ ] **Step 3: 验证编译**

Run: `cd backend && python -c "import py_compile; py_compile.compile('app/services/sync.py', doraise=True); print('OK')"`

预期：OK（所有函数均已定义）

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/sync.py
git commit -m "feat: 实现 _sync_fbw_orders 独立 FBW 三源合并同步"
```

---

### Task 4: 删除旧的回填函数 + 保留 _update_order_statuses

**Files:**
- Modify: `backend/app/services/sync.py` (删除 _backfill_order_prices 和 _update_order_rub_prices)

- [ ] **Step 1: 删除 _backfill_order_prices**

删除 `_backfill_order_prices` 函数（从 `def _backfill_order_prices` 到下一个 `def` 之前）。

- [ ] **Step 2: 删除 _update_order_rub_prices**

删除 `_update_order_rub_prices` 函数（从 `def _update_order_rub_prices` 到下一个 `def` 之前）。

- [ ] **Step 3: 确认 _update_order_statuses 保持不变**

`_update_order_statuses` 函数无需修改，仅验证其仍在文件中：

```python
def _update_order_statuses(db: Session, shop_id: int, api_token: str, wb_order_ids: list[int]):
    """Batch query and update order statuses from WB API."""
    # ... 保持原样 ...
```

- [ ] **Step 4: 删除旧的 _sync_fbo_orders**

删除整个 `_sync_fbo_orders` 函数（已被 `_sync_fbw_orders` 替代）。

- [ ] **Step 5: 验证编译**

Run: `cd backend && python -c "import py_compile; py_compile.compile('app/services/sync.py', doraise=True); print('OK')"`

预期：OK

- [ ] **Step 6: 验证其他 sync 函数未受影响**

确认 `sync_shop_inventory`、`sync_shop_ads`、`sync_shop_products` 仍正常存在：

Run: `cd backend && python -c "from app.services.sync import sync_shop_orders, sync_shop_inventory, sync_shop_ads, sync_shop_products; print('All imports OK')"`

预期：All imports OK

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/sync.py
git commit -m "refactor: 删除旧的回填函数和 _sync_fbo_orders，完成 FBS/FBW 分离重构"
```

---

### Task 5: 全量同步集成测试

**Files:** 无代码修改，纯测试

- [ ] **Step 1: 启动后端**

```bash
cd backend && python -m uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: 触发全量同步**

```bash
TOKEN=$(curl -s http://127.0.0.1:8000/api/auth/login -d "username=caiyiyu&password=caiyiyu123" | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -s -X POST http://127.0.0.1:8000/api/orders/full-sync -H "Authorization: Bearer $TOKEN"
```

预期：`{"status":"running","detail":"全量同步已启动"}`

- [ ] **Step 3: 等待同步完成**

轮询直到 status=done：

```bash
curl -s http://127.0.0.1:8000/api/orders/sync/status -H "Authorization: Bearer $TOKEN"
```

预期：`{"status":"done","detail":"全量同步完成，已同步 2/2 个店铺"}`

- [ ] **Step 4: 验证订单数据**

```bash
cd backend && python -c "
from datetime import datetime, timedelta, timezone
from app.database import SessionLocal
from app.models.order import Order
from sqlalchemy import func

db = SessionLocal()
MSK = timezone(timedelta(hours=3))
now_msk = datetime.now(MSK)
d30 = (now_msk - timedelta(days=30)).replace(hour=0,minute=0,second=0,microsecond=0)
d30_utc = d30.astimezone(timezone.utc).replace(tzinfo=None)

total = db.query(Order).filter(Order.created_at >= d30_utc, Order.shop_id == 1).count()
fbs = db.query(Order).filter(Order.created_at >= d30_utc, Order.shop_id == 1, Order.order_type=='FBS').count()
fbw = db.query(Order).filter(Order.created_at >= d30_utc, Order.shop_id == 1, Order.order_type=='FBW').count()
rub = float(db.query(func.coalesce(func.sum(Order.price_rub),0)).filter(Order.created_at >= d30_utc, Order.shop_id == 1).scalar())
zero = db.query(Order).filter(Order.created_at >= d30_utc, Order.shop_id == 1, Order.price_rub == 0).count()

# Check no FBS price_rub in CNY
wrong = 0
for o in db.query(Order).filter(Order.created_at >= d30_utc, Order.shop_id == 1, Order.order_type=='FBS', Order.price_rub > 0, Order.total_price > 0).all():
    if o.price_rub / o.total_price < 0.1:
        wrong += 1

print(f'30d: {total} (FBS:{fbs}, FBW:{fbw})')
print(f'sum(price_rub): {rub:,.0f}')
print(f'price_rub=0: {zero}')
print(f'FBS price bug: {wrong}')
db.close()
"
```

验收标准：
- FBS price bug = 0
- 30天总订单 >= 3100（接近 WB 后台 3455，允许 API 盲区差异）
- 30天 FBW >= 2000

- [ ] **Step 5: Commit 最终状态**

```bash
git add -A
git commit -m "test: 全量同步验证通过，订单同步重构完成"
```
