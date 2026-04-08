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
    """Determine system status from WB supplier and platform statuses."""
    if wb_status and wb_status in WB_STATUS_MAP:
        return WB_STATUS_MAP[wb_status]
    if supplier_status and supplier_status in SUPPLIER_STATUS_MAP:
        return SUPPLIER_STATUS_MAP[supplier_status]
    return "pending"


# ── Helper functions ──────────────────────────────────────────────────────────


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


def _parse_fbs_prices(raw: dict) -> tuple[float, float, str]:
    """Parse price_rub, total_price, currency from a Marketplace API order.

    WB returns prices in minor units (kopecks/fen).
    Handles multi-currency: if order currency is not RUB but converted is RUB,
    use converted price for price_rub.

    Returns: (price_rub, total_price, currency)
    """
    # Prefer salePrice > finalPrice; avoid 'price' (undiscounted retail, can be wildly high)
    sale_minor = raw.get("salePrice", 0) or 0
    final_minor = raw.get("finalPrice", 0) or 0
    original_minor = sale_minor or final_minor
    converted_minor = (
        raw.get("convertedFinalPrice", 0)
        or raw.get("convertedPrice", 0)
    )
    order_currency = raw.get("currencyCode", 643)
    converted_currency = raw.get("convertedCurrencyCode", 0)

    if converted_currency and converted_currency != order_currency:
        if converted_currency == 643:
            # Order in foreign currency (e.g. CNY), converted to RUB
            price_rub = converted_minor / 100.0
            total_price = converted_minor / 100.0
            currency = "RUB"
        else:
            # Order in RUB, converted to foreign (e.g. CNY for cross-border)
            price_rub = original_minor / 100.0
            total_price = converted_minor / 100.0
            currency = CURRENCY_MAP.get(converted_currency, "CNY")
            # Sanity check: RUB/CNY rate is ~12-14. If ratio > 20, price is unreliable
            if total_price > 0 and price_rub > total_price * 20:
                price_rub = 0  # let Statistics fallback handle it
    else:
        # Single currency
        price_rub = original_minor / 100.0
        total_price = original_minor / 100.0
        currency = CURRENCY_MAP.get(order_currency, "RUB")

    return price_rub, total_price, currency


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


# ── Entry point ───────────────────────────────────────────────────────────────


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
        active_lookup = {o.wb_order_id: o for o in active_orders}
        _update_order_statuses(db, active_lookup, api_token, active_wb_ids)

    shop.last_sync_at = datetime.now(timezone.utc)
    db.commit()
    return cards


# ── FBS sync ──────────────────────────────────────────────────────────────────


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
                price_rub = float(stat.get("priceWithDisc", 0) or stat.get("finishedPrice", 0) or 0)
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

        # Check if exists
        existing = db.query(Order).filter(
            Order.shop_id == shop.id, Order.wb_order_id == wb_order_id
        ).first()
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
            order_type="FBS",
            status="pending",
            total_price=total_price,
            price_rub=price_rub,
            currency=currency,
            warehouse_name=str(raw.get("warehouseId", 0)),
            created_at=(order_created.replace(tzinfo=None) if order_created else None)
                      or datetime.utcnow(),
        )
        db.add(order)
        db.flush()

        db.add(OrderStatusLog(order_id=order.id, status="pending", wb_status="new"))
        _create_order_item(db, order.id, shop.id, nm_id, product_name,
                           sku, barcode, image_url, total_price, nm_card_map)
        created += 1
        if created % 500 == 0:
            db.flush()

    print(f"[Sync] FBS: created {created}, updated {updated} for shop {shop.id}")


# ── FBW sync ──────────────────────────────────────────────────────────────────


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

    # FBS srids set (to exclude FBS from FBW sources)
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

    # Source 2: Statistics Sales — price supplement ONLY.
    # Sales API `date` is delivery date, NOT order date.
    # We do NOT create new orders from Sales (no real order date available).
    # Only update price on orders already found in Statistics Orders.
    sales_price_updates = 0
    for s in stat_sales:
        if "WB" not in s.get("warehouseType", ""):
            continue
        srid = s.get("srid", "")
        if not srid or srid in fbs_srids:
            continue
        price = float(s.get("priceWithDisc", 0) or s.get("finishedPrice", 0) or 0)
        if srid in fbw_records and fbw_records[srid]["price"] == 0 and price > 0:
            fbw_records[srid]["price"] = price
            sales_price_updates += 1
    print(f"[Sync] Sales: {sales_price_updates} FBW price updates for shop {shop.id}")

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

        # Classify FBS vs FBW:
        # 1. delivery_method (explicit FBS/FBW label)
        # 2. assembly_id (FBS has non-zero assembly_id)
        # 3. FBS fingerprint: (nm_id, order_date) matching existing FBS orders
        dm_values = {r.get("delivery_method", "") for r in records} - {""}
        is_fbs = any("FBS" in d.upper() for d in dm_values)
        if not is_fbs:
            has_assembly = any(r.get("assembly_id", 0) not in (0, None) for r in records)
            if has_assembly:
                is_fbs = True
        if is_fbs:
            continue

        # Find best record: qty > 0 AND price > 0 (real sale, not logistics fee)
        best = None
        for r in records:
            if r.get("quantity", 0) > 0 and (r.get("retail_price_withdisc_rub", 0) or 0) > 0:
                best = r
                break

        if not best:
            # Accept if delivery_method explicitly says FBW (even without price)
            if any("FBW" in d.upper() or "FBO" in d.upper() for d in dm_values):
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

        # Extract best price across all records for this srid
        price = float(best.get("retail_price_withdisc_rub", 0) or 0)
        if price == 0:
            for r in records:
                p = float(r.get("retail_price_withdisc_rub", 0) or 0)
                if p > 0:
                    price = p
                    break

        fbw_records[srid] = {
            "srid": srid,
            "order_dt": best.get("order_dt", ""),
            "sale_dt": best.get("sale_dt", ""),
            "nm_id": nm_id,
            "article": article,
            "barcode": best.get("barcode", ""),
            "product_name": best.get("subject_name", ""),
            "price": price,
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

        # Dedup by (nm_id, order_date) — catches matches across different srid formats
        # (Report Detail srids differ from Statistics srids for the same order)
        if rec["source"] == "report" and rec["nm_id"] and rec["order_dt"]:
            dup_key = (str(rec["nm_id"]), rec["order_dt"][:10])
            dup_order = existing_by_nm_date.get(dup_key)
            if dup_order:
                # Update price on existing order if needed
                if dup_order.total_price == 0 and rec["price"] > 0:
                    dup_order.total_price = rec["price"]
                    dup_order.price_rub = rec["price"]
                    dup_order.updated_at = datetime.now(timezone.utc)
                updated_srid += 1
                continue

        # Parse order date — Statistics/Report Detail return Moscow time (UTC+3)
        order_created = None
        if rec["order_dt"]:
            try:
                MSK = timezone(timedelta(hours=3))
                dt = datetime.fromisoformat(rec["order_dt"].replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    # Bare datetime from Statistics API = Moscow time
                    dt = dt.replace(tzinfo=MSK)
                order_created = dt.astimezone(timezone.utc).replace(tzinfo=None)
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
            created_at=order_created or datetime.utcnow(),
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


# ── Status update ─────────────────────────────────────────────────────────────


def _update_order_statuses(db: Session, active_lookup: dict, api_token: str, wb_order_ids: list[int]):
    """Batch query and update order statuses from WB API."""
    statuses = fetch_order_statuses(api_token, wb_order_ids)

    for status_info in statuses:
        wb_id = str(status_info.get("id", ""))
        supplier_status = status_info.get("supplierStatus", "")
        wb_status = status_info.get("wbStatus", "")

        order = active_lookup.get(wb_id)
        if not order:
            continue

        new_status = _resolve_status(supplier_status, wb_status)
        if order.status != new_status:
            order.status = new_status
            order.updated_at = datetime.now(timezone.utc)
            log = OrderStatusLog(
                order_id=order.id,
                status=new_status,
                wb_status=f"{supplier_status}/{wb_status}",
            )
            db.add(log)


# ── Inventory sync ────────────────────────────────────────────────────────────


def sync_shop_inventory(db: Session, shop: Shop):
    """Sync inventory: fetch warehouses, then query stock per warehouse."""
    api_token = decrypt_token(shop.api_token)

    # Step 1: Get all seller warehouses
    warehouses = fetch_warehouses(api_token)
    if not warehouses:
        print(f"[Sync] No warehouses found for shop {shop.name}")
        return

    # Step 2: Collect barcodes from SKU mappings (WB stocks API uses barcodes)
    mappings = db.query(SkuMapping).filter(SkuMapping.shop_id == shop.id).all()
    all_barcodes = [m.wb_barcode for m in mappings if m.wb_barcode]

    if not all_barcodes:
        print(f"[Sync] No barcodes to query for shop {shop.name}")
        return

    # Build barcode → mapping lookup
    barcode_to_mapping = {m.wb_barcode: m for m in mappings if m.wb_barcode}

    # Step 3: Query stock for each warehouse
    sku_stocks: dict[str, dict] = {}
    for wh in warehouses:
        wh_id = wh.get("id")
        wh_name = wh.get("name", "")
        if not wh_id:
            continue

        stocks = fetch_stocks(api_token, wh_id, all_barcodes)
        for s in stocks:
            barcode = s.get("sku", "")
            amount = s.get("amount", 0)
            if not barcode:
                continue

            # Map barcode back to seller article (shop_sku)
            mapping = barcode_to_mapping.get(barcode)
            sku = mapping.shop_sku if mapping else barcode
            name = mapping.wb_product_name if mapping else ""
            nm_id = mapping.wb_nm_id if mapping else ""

            if sku not in sku_stocks:
                sku_stocks[sku] = {"name": name, "fbs": 0, "fbw": 0, "nm_id": nm_id}

            # FBS warehouses are seller's own warehouses (from /api/v3/warehouses)
            sku_stocks[sku]["fbs"] += amount

    # Step 4: Update inventory records
    for sku, data in sku_stocks.items():
        inv = db.query(Inventory).filter(
            Inventory.shop_id == shop.id, Inventory.sku == sku
        ).first()
        if inv:
            inv.stock_fbs = data["fbs"]
            if data.get("nm_id"):
                inv.wb_product_id = data["nm_id"]
            inv.updated_at = datetime.now(timezone.utc)
        else:
            inv = Inventory(
                shop_id=shop.id,
                wb_product_id=data.get("nm_id", ""),
                product_name=data["name"],
                sku=sku,
                barcode=sku,
                stock_fbs=data["fbs"],
                stock_fbw=0,
            )
            db.add(inv)

    db.commit()


def sync_shop_ads(db: Session, shop: Shop, cards: list[dict] | None = None):
    """Sync advertising campaigns and daily stats from WB Advert API."""
    api_token = decrypt_token(shop.api_token)

    # Step 1: Get all campaign IDs with type/status from count endpoint
    count_items = fetch_ad_campaign_ids(api_token)
    if not count_items:
        print(f"[Sync] No ad campaigns found for shop {shop.name}")
        return

    all_ids = [item["advertId"] for item in count_items]
    # Build type/status lookup from count endpoint
    count_lookup = {item["advertId"]: item for item in count_items}

    # Step 2: Fetch campaign details, display names, and budgets
    details = fetch_ad_details(api_token, all_ids)
    display_names = fetch_ad_campaign_names(api_token)
    # Build details lookup by id
    detail_lookup = {}
    for d in details:
        did = d.get("id")
        if did:
            detail_lookup[did] = d

    # Fetch budgets for campaigns that claim to be active/paused (status 7 or 9)
    # Budget > 0 is the most reliable signal for "actually active"
    ambiguous_ids = [
        item["advertId"] for item in count_items
        if item.get("status") in (7, 9)
    ]
    budgets = fetch_ad_budgets_batch(api_token, ambiguous_ids) if ambiguous_ids else {}

    campaign_map = {}  # wb_advert_id → db campaign

    for wb_id in all_ids:
        count_info = count_lookup.get(wb_id, {})
        detail_info = detail_lookup.get(wb_id, {})

        existing = db.query(AdCampaign).filter(AdCampaign.wb_advert_id == wb_id).first()

        # Name: prefer display name from /upd, fallback to settings.name
        name = display_names.get(wb_id, "")
        if not name:
            settings = detail_info.get("settings", {})
            name = settings.get("name", "") if settings else ""

        # Type/status from count endpoint (grouped by type+status, sometimes inaccurate)
        ad_type = count_info.get("type", 0)
        ad_status = count_info.get("status", 0)

        # Prefer type/status from detail endpoint (per-campaign, more accurate)
        detail_type = detail_info.get("type", 0)
        detail_status = detail_info.get("status", 0)
        if detail_type and detail_type != ad_type:
            print(f"[Sync] Campaign {wb_id}: count type={ad_type} → detail type={detail_type}")
            ad_type = detail_type
        if detail_status and detail_status != ad_status:
            print(f"[Sync] Campaign {wb_id}: count status={ad_status} → detail status={detail_status}")
            ad_status = detail_status

        # Timestamps from detail endpoint
        timestamps = detail_info.get("timestamps", {})
        create_time = None
        create_time_str = timestamps.get("created", "")
        if create_time_str:
            try:
                create_time = datetime.fromisoformat(create_time_str)
            except (ValueError, AttributeError):
                pass

        # Status correction using budget (most reliable signal).
        budget_info = budgets.get(wb_id, {})
        budget_total = budget_info.get("total", 0) or 0
        if budget_total > 0 and ad_status != 7:
            print(f"[Sync] Campaign {wb_id}: status={ad_status} but budget={budget_total}, marking as active (7)")
            ad_status = 7
        elif ad_status in (7, 11) and budget_total == 0:
            if ad_status == 7:
                print(f"[Sync] Campaign {wb_id}: status=7 but budget=0, marking as paused (9)")
            ad_status = 9

        # Daily budget from detail endpoint
        daily_budget = detail_info.get("dailyBudget", 0) or 0

        if existing:
            if name:
                existing.name = name
            existing.type = ad_type
            existing.status = ad_status
            existing.daily_budget = daily_budget
            if create_time:
                existing.create_time = create_time
            existing.updated_at = datetime.now(timezone.utc)
            campaign_map[wb_id] = existing
        else:
            campaign = AdCampaign(
                shop_id=shop.id,
                wb_advert_id=wb_id,
                name=name,
                type=ad_type,
                status=ad_status,
                daily_budget=daily_budget,
                create_time=create_time,
            )
            db.add(campaign)
            db.flush()
            campaign_map[wb_id] = campaign

    # Step 3: Fetch daily stats for active/paused/ended campaigns
    stat_campaign_ids = [
        wb_id for wb_id, c in campaign_map.items()
        if c.status in (7, 9, 11)
    ]

    if not stat_campaign_ids:
        db.commit()
        return

    has_any_stats = db.query(AdDailyStat).join(AdCampaign).filter(
        AdCampaign.shop_id == shop.id
    ).first()
    days_back = 7 if has_any_stats else 30

    today = date.today()
    date_from = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to = today.strftime("%Y-%m-%d")

    raw_stats = fetch_ad_fullstats(api_token, stat_campaign_ids, date_from, date_to)

    # Step 4: Parse and upsert daily stats
    for entry in raw_stats:
        wb_advert_id = entry.get("advertId")
        campaign = campaign_map.get(wb_advert_id)
        if not campaign:
            continue

        for day_data in entry.get("days", []):
            day_date_str = day_data.get("date", "")[:10]
            if not day_date_str:
                continue
            try:
                stat_date = date.fromisoformat(day_date_str)
            except ValueError:
                continue

            # Aggregate across all app types per nm_id per day
            nm_agg = {}
            for app_data in day_data.get("apps", []):
                for nm_data in app_data.get("nms", []):
                    nm_id = nm_data.get("nmId", 0)
                    if not nm_id:
                        continue
                    if nm_id not in nm_agg:
                        nm_agg[nm_id] = {
                            "views": 0, "clicks": 0, "spend": 0.0,
                            "orders": 0, "order_amount": 0.0, "atbs": 0,
                        }
                    agg = nm_agg[nm_id]
                    agg["views"] += nm_data.get("views", 0)
                    agg["clicks"] += nm_data.get("clicks", 0)
                    agg["spend"] += nm_data.get("sum", 0.0)
                    agg["orders"] += nm_data.get("orders", 0)
                    agg["order_amount"] += nm_data.get("sum_price", 0.0)
                    agg["atbs"] += nm_data.get("atbs", 0)

            for nm_id, agg in nm_agg.items():
                views = agg["views"]
                clicks = agg["clicks"]
                ctr = (clicks / views * 100) if views > 0 else 0.0
                cpc = (agg["spend"] / clicks) if clicks > 0 else 0.0
                cr = (agg["orders"] / clicks * 100) if clicks > 0 else 0.0

                existing_stat = db.query(AdDailyStat).filter(
                    AdDailyStat.campaign_id == campaign.id,
                    AdDailyStat.nm_id == nm_id,
                    AdDailyStat.date == stat_date,
                ).first()

                if existing_stat:
                    existing_stat.views = views
                    existing_stat.clicks = clicks
                    existing_stat.spend = agg["spend"]
                    existing_stat.orders = agg["orders"]
                    existing_stat.order_amount = agg["order_amount"]
                    existing_stat.atbs = agg["atbs"]
                    existing_stat.ctr = ctr
                    existing_stat.cpc = cpc
                    existing_stat.cr = cr
                else:
                    stat = AdDailyStat(
                        campaign_id=campaign.id,
                        nm_id=nm_id,
                        date=stat_date,
                        views=views,
                        clicks=clicks,
                        ctr=ctr,
                        cpc=cpc,
                        spend=agg["spend"],
                        orders=agg["orders"],
                        order_amount=agg["order_amount"],
                        atbs=agg["atbs"],
                        cr=cr,
                    )
                    db.add(stat)

    db.commit()

    # Step 5: Backfill wb_nm_id in SkuMapping using product cards (best-effort)
    if cards:
        try:
            all_ad_nm_ids = set()
            for entry in raw_stats:
                for day_data in entry.get("days", []):
                    for app_data in day_data.get("apps", []):
                        for nm_data in app_data.get("nms", []):
                            nm_id = nm_data.get("nmId", 0)
                            if nm_id:
                                all_ad_nm_ids.add(nm_id)

            if all_ad_nm_ids:
                existing_nm_ids = {
                    r[0] for r in db.query(SkuMapping.wb_nm_id).filter(
                        SkuMapping.wb_nm_id.in_([str(n) for n in all_ad_nm_ids]),
                        SkuMapping.shop_id == shop.id,
                    ).all() if r[0]
                }
                missing_nm_ids = all_ad_nm_ids - {int(n) for n in existing_nm_ids}

                if missing_nm_ids:
                    nm_card_map = {}
                    for card in cards:
                        c_nm_id = card.get("nmID")
                        if c_nm_id and c_nm_id in missing_nm_ids:
                            nm_card_map[c_nm_id] = card

                    for nm_id, card in nm_card_map.items():
                        vendor_code = card.get("vendorCode", "")
                        if not vendor_code:
                            continue
                        existing_mapping = db.query(SkuMapping).filter(
                            SkuMapping.shop_id == shop.id,
                            SkuMapping.shop_sku == vendor_code,
                        ).first()
                        photos = card.get("photos", [])
                        image_url = photos[0].get("c246x328", "") if photos else ""
                        if existing_mapping:
                            if not existing_mapping.wb_nm_id:
                                existing_mapping.wb_nm_id = str(nm_id)
                            if not existing_mapping.wb_product_name:
                                existing_mapping.wb_product_name = card.get("title", "")
                            if not existing_mapping.wb_image_url and image_url:
                                existing_mapping.wb_image_url = image_url
                        else:
                            mapping = SkuMapping(
                                shop_id=shop.id,
                                shop_sku=vendor_code,
                                wb_nm_id=str(nm_id),
                                wb_product_name=card.get("title", ""),
                                wb_image_url=image_url,
                            )
                            db.add(mapping)
                    db.commit()
        except Exception as e:
            print(f"[Sync] Ad card backfill skipped (non-fatal): {e}")
    print(f"[Sync] Ad sync complete for shop {shop.name}: {len(campaign_map)} campaigns")


def sync_shop_products(db: Session, shop: Shop, cards: list[dict] | None = None):
    """Sync WB products for a shop: fetch cards + ratings, upsert into ShopProduct."""
    from app.models.product import ShopProduct

    api_token = decrypt_token(shop.api_token)
    if cards is None:
        cards = fetch_cards(api_token)

    if not cards:
        print(f"[Sync] No product cards for shop {shop.name}")
        return

    # Build nm_id list and fetch ratings + prices
    nm_ids = [c.get("nmID") for c in cards if c.get("nmID")]
    ratings = fetch_product_ratings(api_token, nm_ids) if nm_ids else {}
    prices = fetch_product_prices(api_token)

    for card in cards:
        nm_id = card.get("nmID")
        if not nm_id:
            continue

        title = card.get("title", "")
        vendor_code = card.get("vendorCode", "")
        photos = card.get("photos", [])
        image_url = photos[0].get("c246x328", "") if photos else ""

        rating_info = ratings.get(nm_id, {})
        rating = float(rating_info.get("valuation", 0))
        feedbacks_count = int(rating_info.get("feedbacksCount", 0))

        price_info = prices.get(nm_id, {})
        price = float(price_info.get("price", 0))
        currency = price_info.get("currency", "RUB")
        discount = int(price_info.get("discount", 0))
        existing = db.query(ShopProduct).filter(
            ShopProduct.shop_id == shop.id,
            ShopProduct.nm_id == nm_id,
        ).first()

        if existing:
            existing.title = title
            existing.vendor_code = vendor_code
            if image_url:
                existing.image_url = image_url
            existing.price = price
            existing.currency = currency
            existing.discount = discount
            existing.rating = rating
            existing.feedbacks_count = feedbacks_count
        else:
            product = ShopProduct(
                shop_id=shop.id,
                nm_id=nm_id,
                title=title,
                vendor_code=vendor_code,
                image_url=image_url,
                price=price,
                currency=currency,
                discount=discount,
                rating=rating,
                feedbacks_count=feedbacks_count,
            )
            db.add(product)

    db.commit()
    print(f"[Sync] Product sync complete for shop {shop.name}: {len(cards)} products")
