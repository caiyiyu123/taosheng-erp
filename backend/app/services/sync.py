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
    fetch_statistics_orders,
    fetch_ad_campaign_ids, fetch_ad_details, fetch_ad_fullstats,
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
    """Determine system status from WB supplier and platform statuses.

    Priority: wb_status (platform) > supplier_status (seller side).
    """
    if wb_status and wb_status in WB_STATUS_MAP:
        return WB_STATUS_MAP[wb_status]
    if supplier_status and supplier_status in SUPPLIER_STATUS_MAP:
        return SUPPLIER_STATUS_MAP[supplier_status]
    return "pending"


def sync_shop_orders(db: Session, shop: Shop):
    """Sync orders for a shop: fetch new + historical orders, then update statuses."""
    api_token = decrypt_token(shop.api_token)

    # Step 1: Fetch new orders (awaiting processing)
    new_orders = fetch_new_orders(api_token)

    # Step 2: Fetch historical orders (incremental from last sync)
    historical_orders = fetch_orders(api_token, date_from=shop.last_sync_at)

    # Step 2b: If there are zero-price orders, fetch older history to get their data
    zero_price_count = db.query(Order).filter(
        Order.shop_id == shop.id, Order.total_price == 0
    ).count()
    if zero_price_count > 0:
        from datetime import timedelta
        oldest_zero = db.query(Order).filter(
            Order.shop_id == shop.id, Order.total_price == 0
        ).order_by(Order.created_at.asc()).first()
        if oldest_zero and oldest_zero.created_at:
            backfill_from = oldest_zero.created_at - timedelta(hours=1)
            backfill_orders = fetch_orders(api_token, date_from=backfill_from)
            historical_orders.extend(backfill_orders)

    # Merge all orders, deduplicate by id (new orders take priority — they have more price fields)
    all_raw_orders = {}
    for raw in historical_orders:
        order_id = raw.get("id")
        if order_id:
            all_raw_orders[order_id] = raw
    # New orders overwrite historical (they have salePrice, finalPrice etc.)
    for raw in new_orders:
        order_id = raw.get("id")
        if order_id:
            all_raw_orders[order_id] = raw

    # Step 3: Build nmId → card info lookup from product cards
    cards = fetch_cards(api_token)
    nm_card_map = {}
    for card in cards:
        nm_id = card.get("nmID")
        if nm_id:
            nm_card_map[nm_id] = {
                "name": card.get("title", ""),
                "vendorCode": card.get("vendorCode", ""),
                "photos": card.get("photos", []),
            }

    # Step 4: Save/update orders
    wb_order_ids = []
    for wb_id, raw in all_raw_orders.items():
        wb_order_id = str(wb_id)
        wb_order_ids.append(wb_id)

        # Parse price from WB API response
        # WB returns multiple price fields: salePrice (actual sale price),
        # finalPrice/convertedFinalPrice, price/convertedPrice (base price, often 0 for new orders)
        converted_currency = raw.get("convertedCurrencyCode", 0)
        if converted_currency and converted_currency != raw.get("currencyCode", 643):
            # Cross-border: use converted currency fields
            price_minor = (
                raw.get("convertedFinalPrice", 0)
                or raw.get("convertedPrice", 0)
            )
            currency = CURRENCY_MAP.get(converted_currency, "CNY")
        else:
            # Local: use main currency fields
            price_minor = (
                raw.get("salePrice", 0)
                or raw.get("finalPrice", 0)
                or raw.get("price", 0)
            )
            currency = CURRENCY_MAP.get(raw.get("currencyCode", 643), "RUB")
        price = price_minor / 100.0  # Convert minor units to major (kopecks→RUB, fen→CNY)

        nm_id = raw.get("nmId", 0)
        article = raw.get("article", "")  # 卖家商品编码 (seller article)
        skus = raw.get("skus", [])  # 条形码 (barcodes)
        barcode = skus[0] if skus else ""
        card_info = nm_card_map.get(nm_id, {})
        product_name = card_info.get("name", article)
        sku = article or card_info.get("vendorCode", "") or barcode
        # Get product thumbnail from card photos
        photos = card_info.get("photos", [])
        image_url = photos[0].get("c246x328", "") if photos else ""

        # Parse created time from API
        created_at_str = raw.get("createdAt", "")
        order_created = None
        if created_at_str:
            try:
                order_created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        existing = db.query(Order).filter(Order.wb_order_id == wb_order_id).first()
        if existing:
            # Update price if it was 0 and we now have a real price
            if existing.total_price == 0 and price > 0:
                existing.total_price = price
                existing.currency = currency
                existing.updated_at = datetime.now(timezone.utc)

            # Fix created_at if it differs from API time (was stored as sync time)
            if order_created and existing.created_at:
                api_time = order_created.replace(tzinfo=None)
                diff = abs((api_time - existing.created_at).total_seconds())
                if diff > 5:
                    existing.created_at = api_time

            # Backfill missing image_url on existing items
            if image_url:
                existing_item = db.query(OrderItem).filter(
                    OrderItem.order_id == existing.id, OrderItem.image_url == ""
                ).first()
                if existing_item:
                    existing_item.image_url = image_url

            # Backfill missing OrderItems
            has_items = db.query(OrderItem).filter(OrderItem.order_id == existing.id).count()
            if not has_items and nm_id:
                item = OrderItem(
                    order_id=existing.id,
                    wb_product_id=str(nm_id),
                    product_name=product_name,
                    sku=sku,
                    barcode=barcode,
                    image_url=image_url,
                    quantity=1,
                    price=price,
                )
                db.add(item)

                # Auto-create SKU mapping for backfilled items
                if sku:
                    existing_mapping = db.query(SkuMapping).filter(
                        SkuMapping.shop_id == shop.id, SkuMapping.shop_sku == sku
                    ).first()
                    if not existing_mapping:
                        mapping = SkuMapping(
                            shop_id=shop.id, shop_sku=sku,
                            wb_product_name=product_name, wb_barcode=barcode,
                        )
                        db.add(mapping)

            continue  # Status update handled in batch below

        warehouse_id = raw.get("warehouseId", 0)

        # Determine order type from deliveryType field
        delivery_type = raw.get("deliveryType", "fbs")
        order_type = delivery_type.upper() if delivery_type else "FBS"

        order = Order(
            wb_order_id=wb_order_id,
            shop_id=shop.id,
            order_type=order_type,
            status="pending",
            total_price=price,
            currency=currency,
            warehouse_name=str(warehouse_id),
            created_at=order_created or datetime.now(timezone.utc),
        )
        db.add(order)
        db.flush()

        # Initial status log
        log = OrderStatusLog(
            order_id=order.id,
            status="pending",
            wb_status="new",
        )
        db.add(log)

        # Each WB order = one item (one SKU per order)
        item = OrderItem(
            order_id=order.id,
            wb_product_id=str(nm_id),
            product_name=product_name,
            sku=sku,
            barcode=barcode,
            image_url=image_url,
            quantity=1,
            price=price,
        )
        db.add(item)

        # Auto-create SKU mapping if not exists
        if sku:
            existing_mapping = db.query(SkuMapping).filter(
                SkuMapping.shop_id == shop.id, SkuMapping.shop_sku == sku
            ).first()
            if not existing_mapping:
                mapping = SkuMapping(
                    shop_id=shop.id,
                    shop_sku=sku,
                    wb_product_name=product_name,
                    wb_barcode=barcode,
                )
                db.add(mapping)

    # Step 5: Update statuses for all non-terminal orders (not just current batch)
    terminal_statuses = ("completed", "cancelled", "returned", "rejected")
    active_orders = db.query(Order).filter(
        Order.shop_id == shop.id,
        ~Order.status.in_(terminal_statuses),
    ).all()
    active_wb_ids = [int(o.wb_order_id) for o in active_orders if o.wb_order_id.isdigit()]
    if active_wb_ids:
        _update_order_statuses(db, shop.id, api_token, active_wb_ids)

    # Step 6: Backfill prices for orders with price=0 using Statistics API
    _backfill_order_prices(db, shop.id, api_token)

    shop.last_sync_at = datetime.now(timezone.utc)
    db.commit()


def _update_order_statuses(db: Session, shop_id: int, api_token: str, wb_order_ids: list[int]):
    """Batch query and update order statuses from WB API."""
    statuses = fetch_order_statuses(api_token, wb_order_ids)

    for status_info in statuses:
        wb_id = str(status_info.get("id", ""))
        supplier_status = status_info.get("supplierStatus", "")
        wb_status = status_info.get("wbStatus", "")

        order = db.query(Order).filter(
            Order.shop_id == shop_id, Order.wb_order_id == wb_id
        ).first()
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


def _backfill_order_prices(db: Session, shop_id: int, api_token: str):
    """Use Statistics API to fill in prices for orders where total_price=0.

    The Marketplace orders API often returns price=0 for new orders.
    The Statistics API (GET /api/v1/supplier/orders) provides actual prices:
    totalPrice, priceWithDisc, finishedPrice, spp, etc.
    Statistics data is linked via srid (unique order identifier) or nmId+date.
    """
    # Find orders with price=0 for this shop
    zero_price_orders = db.query(Order).filter(
        Order.shop_id == shop_id, Order.total_price == 0
    ).all()

    if not zero_price_orders:
        return

    # Fetch statistics orders (last 90 days max)
    stat_orders = fetch_statistics_orders(api_token)
    if not stat_orders:
        return

    # Build lookup: srid → stats data (srid is the unique order identifier)
    # Also build wb_order_id (mapped from orderType + srid) for matching
    # Statistics API uses "srid" as unique key; Marketplace API uses "id"
    # We match by checking if the srid starts with the order id pattern
    # or by matching nmId + date combination

    # Build lookup by srid (which often contains the marketplace order id)
    srid_map = {}
    for stat in stat_orders:
        srid = stat.get("srid", "")
        if srid:
            srid_map[srid] = stat

    # Also build a lookup by gNumber (group number links related order items)
    gnumber_map = {}
    for stat in stat_orders:
        gn = stat.get("gNumber", "")
        if gn:
            if gn not in gnumber_map:
                gnumber_map[gn] = stat

    updated = 0
    for order in zero_price_orders:
        wb_id = order.wb_order_id
        best_match = None

        # Try to find by srid containing the order id
        for srid, stat in srid_map.items():
            if wb_id in srid or srid.startswith(wb_id):
                best_match = stat
                break

        # Fallback: match by nmId + approximate date via order items
        if not best_match:
            items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
            for item in items:
                nm_id = item.wb_product_id
                for stat in stat_orders:
                    if str(stat.get("nmId", "")) == nm_id:
                        stat_date = stat.get("date", "")
                        if stat_date and order.created_at:
                            try:
                                sd = datetime.fromisoformat(stat_date.replace("Z", "+00:00"))
                                diff = abs((sd - order.created_at).total_seconds())
                                if diff < 86400:  # Within 24 hours
                                    best_match = stat
                                    break
                            except (ValueError, TypeError):
                                continue
                if best_match:
                    break

        if best_match:
            # priceWithDisc is the actual price customer pays (in rubles, not kopecks)
            new_price = best_match.get("priceWithDisc", 0) or best_match.get("finishedPrice", 0) or best_match.get("totalPrice", 0)
            if new_price and new_price > 0:
                order.total_price = float(new_price)
                order.updated_at = datetime.now(timezone.utc)

                # Also update order item price
                item = db.query(OrderItem).filter(OrderItem.order_id == order.id).first()
                if item:
                    item.price = float(new_price)
                    # Fill commission and logistics if available
                    spp = best_match.get("spp", 0)
                    if spp:
                        item.commission = float(abs(spp))

                updated += 1

    if updated:
        print(f"[Sync] Backfilled prices for {updated} orders in shop {shop_id}")


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

            if sku not in sku_stocks:
                sku_stocks[sku] = {"name": name, "fbs": 0, "fbw": 0}

            # FBS warehouses are seller's own warehouses (from /api/v3/warehouses)
            sku_stocks[sku]["fbs"] += amount

    # Step 4: Also try to get FBW stock from WB warehouses (office stock)
    # FBW stock comes from a different source — the seller can check it
    # via the statistics API or supplies API. For now we track FBS stock
    # from the seller's warehouses.

    # Step 5: Update inventory records
    for sku, data in sku_stocks.items():
        inv = db.query(Inventory).filter(
            Inventory.shop_id == shop.id, Inventory.sku == sku
        ).first()
        if inv:
            inv.stock_fbs = data["fbs"]
            inv.updated_at = datetime.now(timezone.utc)
        else:
            inv = Inventory(
                shop_id=shop.id,
                product_name=data["name"],
                sku=sku,
                barcode=sku,
                stock_fbs=data["fbs"],
                stock_fbw=0,
            )
            db.add(inv)

    db.commit()


def sync_shop_ads(db: Session, shop: Shop):
    """Sync advertising campaigns and daily stats from WB Advert API."""
    api_token = decrypt_token(shop.api_token)

    # Step 1: Get all campaign IDs
    all_ids = fetch_ad_campaign_ids(api_token)
    if not all_ids:
        print(f"[Sync] No ad campaigns found for shop {shop.name}")
        return

    # Step 2: Fetch campaign details and upsert
    details = fetch_ad_details(api_token, all_ids)
    campaign_map = {}  # wb_advert_id → db campaign

    for d in details:
        wb_id = d.get("advertId")
        if not wb_id:
            continue

        existing = db.query(AdCampaign).filter(AdCampaign.wb_advert_id == wb_id).first()

        create_time_str = d.get("createTime", "")
        create_time = None
        if create_time_str:
            try:
                create_time = datetime.fromisoformat(create_time_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        if existing:
            existing.name = d.get("name", existing.name)
            existing.type = d.get("type", existing.type)
            existing.status = d.get("status", existing.status)
            existing.daily_budget = d.get("dailyBudget", existing.daily_budget) or 0
            if create_time:
                existing.create_time = create_time
            existing.updated_at = datetime.now(timezone.utc)
            campaign_map[wb_id] = existing
        else:
            campaign = AdCampaign(
                shop_id=shop.id,
                wb_advert_id=wb_id,
                name=d.get("name", ""),
                type=d.get("type", 0),
                status=d.get("status", 0),
                daily_budget=d.get("dailyBudget", 0) or 0,
                create_time=create_time,
            )
            db.add(campaign)
            db.flush()
            campaign_map[wb_id] = campaign

    # Step 3: Fetch daily stats for active campaigns
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

            for app_data in day_data.get("apps", []):
                for nm_data in app_data.get("nm", []):
                    nm_id = nm_data.get("nmId", 0)
                    if not nm_id:
                        continue

                    existing_stat = db.query(AdDailyStat).filter(
                        AdDailyStat.campaign_id == campaign.id,
                        AdDailyStat.nm_id == nm_id,
                        AdDailyStat.date == stat_date,
                    ).first()

                    views = nm_data.get("views", 0)
                    clicks = nm_data.get("clicks", 0)
                    spend = nm_data.get("sum", 0.0)
                    orders_count = nm_data.get("orders", 0)
                    order_amount = nm_data.get("sum_price", 0.0)
                    atbs = nm_data.get("atbs", 0)
                    ctr = nm_data.get("ctr", 0.0)
                    cpc = nm_data.get("cpc", 0.0)
                    cr = nm_data.get("cr", 0.0)

                    if existing_stat:
                        existing_stat.views = views
                        existing_stat.clicks = clicks
                        existing_stat.spend = spend
                        existing_stat.orders = orders_count
                        existing_stat.order_amount = order_amount
                        existing_stat.atbs = atbs
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
                            spend=spend,
                            orders=orders_count,
                            order_amount=order_amount,
                            atbs=atbs,
                            cr=cr,
                        )
                        db.add(stat)

    db.commit()
    print(f"[Sync] Ad sync complete for shop {shop.name}: {len(campaign_map)} campaigns")
