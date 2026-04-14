import httpx
import time
import threading
from typing import Optional
from datetime import datetime, timezone, timedelta

# WB API base URLs
MARKETPLACE_API = "https://marketplace-api.wildberries.ru"
STATISTICS_API = "https://statistics-api.wildberries.ru"
ADVERT_API = "https://advert-api.wildberries.ru"

# Rate limit: min 200ms between requests
_last_request_time = 0.0
_MIN_INTERVAL = 0.2
_throttle_lock = threading.Lock()


def _throttle():
    """Ensure minimum interval between API requests."""
    global _last_request_time
    with _throttle_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_request_time = time.time()


def _headers(api_token: str) -> dict:
    return {"Authorization": api_token, "Content-Type": "application/json"}


def fetch_new_orders(api_token: str) -> list[dict]:
    """GET /api/v3/orders/new — fetch new FBS orders awaiting processing."""
    url = f"{MARKETPLACE_API}/api/v3/orders/new"
    try:
        _throttle()
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=_headers(api_token))
            resp.raise_for_status()
            data = resp.json()
            return data.get("orders", [])
    except Exception as e:
        print(f"[WB API] Error fetching new orders: {e}")
        return []


def _fetch_orders_window(client, url: str, api_token: str, date_from_ts: int) -> list[dict]:
    """Fetch orders for a single 30-day window starting from date_from_ts."""
    all_orders = []
    next_cursor = 0
    while True:
        params = {"limit": 1000, "next": next_cursor, "dateFrom": date_from_ts}
        _throttle()
        resp = client.get(url, headers=_headers(api_token), params=params)
        resp.raise_for_status()
        data = resp.json()
        orders = data.get("orders", [])
        all_orders.extend(orders)
        next_cursor = data.get("next", 0)
        if not orders or next_cursor == 0:
            break
    return all_orders


def fetch_orders(api_token: str, date_from: Optional[datetime] = None) -> list[dict]:
    """GET /api/v3/orders — fetch historical orders with pagination.

    WB API returns a ~30-day window per call, so we loop in 30-day chunks
    from date_from to now to get the full range.
    """
    from datetime import timedelta

    url = f"{MARKETPLACE_API}/api/v3/orders"
    now = datetime.now(timezone.utc)

    if not date_from:
        date_from = now - timedelta(days=30)

    all_orders = {}  # deduplicate by order id
    try:
        with httpx.Client(timeout=30) as client:
            window_start = date_from
            while window_start < now:
                ts = int(window_start.timestamp())
                orders = _fetch_orders_window(client, url, api_token, ts)
                print(f"[WB API] fetch_orders window: dateFrom={window_start.strftime('%Y-%m-%d')}, got {len(orders)} orders")
                for o in orders:
                    oid = o.get("id")
                    if oid:
                        all_orders[oid] = o
                # Advance window by 30 days
                window_start += timedelta(days=30)
    except Exception as e:
        print(f"[WB API] Error fetching orders: {e}")

    result = list(all_orders.values())
    print(f"[WB API] fetch_orders total: {len(result)} unique orders")
    return result


def fetch_order_statuses(api_token: str, order_ids: list[int]) -> list[dict]:
    """POST /api/v3/orders/status — batch query order statuses.

    Request: {"orders": [id1, id2, ...]}  (max 1000)
    Response: {"orders": [{"id": ..., "supplierStatus": "...", "wbStatus": "..."}]}
    """
    if not order_ids:
        return []

    url = f"{MARKETPLACE_API}/api/v3/orders/status"
    all_statuses = []

    try:
        with httpx.Client(timeout=30) as client:
            # Process in batches of 1000
            for i in range(0, len(order_ids), 1000):
                batch = order_ids[i:i + 1000]
                _throttle()
                resp = client.post(url, headers=_headers(api_token), json={"orders": batch})
                resp.raise_for_status()
                data = resp.json()
                all_statuses.extend(data.get("orders", []))
    except Exception as e:
        print(f"[WB API] Error fetching order statuses: {e}")

    return all_statuses


def fetch_warehouses(api_token: str) -> list[dict]:
    """GET /api/v3/warehouses — get seller's FBS warehouses.

    Response: [{"id": 123, "name": "My Warehouse", ...}]
    """
    url = f"{MARKETPLACE_API}/api/v3/warehouses"
    try:
        _throttle()
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=_headers(api_token))
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[WB API] Error fetching warehouses: {e}")
        return []


def fetch_stocks(api_token: str, warehouse_id: int, skus: list[str]) -> list[dict]:
    """POST /api/v3/stocks/{warehouseId} — query stock for specific SKUs.

    Request: {"skus": ["barcode1", "barcode2"]}
    Response: {"stocks": [{"sku": "...", "amount": 10}]}
    """
    if not skus:
        return []

    url = f"{MARKETPLACE_API}/api/v3/stocks/{warehouse_id}"
    all_stocks = []

    try:
        with httpx.Client(timeout=30) as client:
            # Process in batches of 1000
            for i in range(0, len(skus), 1000):
                batch = skus[i:i + 1000]
                _throttle()
                resp = client.post(url, headers=_headers(api_token), json={"skus": batch})
                resp.raise_for_status()
                data = resp.json()
                for stock in data.get("stocks", []):
                    stock["warehouseId"] = warehouse_id
                all_stocks.extend(data.get("stocks", []))
    except Exception as e:
        print(f"[WB API] Error fetching stocks for warehouse {warehouse_id}: {e}")

    return all_stocks


def fetch_cards(api_token: str) -> list[dict]:
    """POST /content/v2/get/cards/list — fetch product cards for names/photos.

    This uses the content API to get product info (nmID, title, photos, etc.)
    """
    url = "https://content-api.wildberries.ru/content/v2/get/cards/list"
    all_cards = []
    cursor = {"limit": 100}

    try:
        with httpx.Client(timeout=60) as client:
            while True:
                _throttle()
                body = {"settings": {"cursor": cursor, "filter": {"withPhoto": -1}}}
                resp = client.post(url, headers=_headers(api_token), json=body)
                resp.raise_for_status()
                data = resp.json()

                cards = data.get("cards", [])
                all_cards.extend(cards)

                cursor_resp = data.get("cursor", {})
                if not cards or cursor_resp.get("total", 0) < cursor.get("limit", 100):
                    break
                cursor = {
                    "limit": 100,
                    "updatedAt": cursor_resp.get("updatedAt"),
                    "nmID": cursor_resp.get("nmID"),
                }
    except Exception as e:
        print(f"[WB API] Error fetching cards: {e}")

    return all_cards


def fetch_product_prices(api_token: str) -> dict[int, dict]:
    """GET /api/v2/list/goods/filter — fetch product prices.

    Returns dict: {nm_id: {"price": 1500.0, "discount": 10}}
    """
    url = "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter"
    result = {}
    offset = 0
    limit = 1000

    try:
        with httpx.Client(timeout=30) as client:
            while True:
                _throttle()
                resp = client.get(url, headers=_headers(api_token), params={
                    "limit": limit,
                    "offset": offset,
                })
                if resp.status_code != 200:
                    print(f"[WB API] Prices status={resp.status_code}, resp={resp.text[:200]}")
                    break
                data = resp.json()
                goods = data.get("data", {}).get("listGoods", [])
                if not goods:
                    break
                # Debug: print first product's raw data
                if offset == 0 and goods:
                    print(f"[WB API] Prices sample: {goods[0]}")
                for g in goods:
                    nm_id = g.get("nmID", 0)
                    sizes = g.get("sizes", [])
                    discount = g.get("discount", 0)
                    currency_code = g.get("currencyIsoCode4217", "RUB")
                    # Map ISO 4217 codes
                    currency = "CNY" if currency_code == "CNY" else "RUB"
                    # Get price from first size
                    price = 0
                    if sizes:
                        price = sizes[0].get("discountedPrice", 0) or sizes[0].get("price", 0)
                    if nm_id:
                        result[nm_id] = {"price": price, "discount": discount, "currency": currency}
                offset += limit
                if len(goods) < limit:
                    break
    except Exception as e:
        print(f"[WB API] Error fetching product prices: {e}")

    print(f"[WB API] Prices fetched for {len(result)} products")
    return result


def fetch_product_ratings(api_token: str, nm_ids: list[int]) -> dict[int, dict]:
    """Fetch product ratings via WB Feedbacks API.

    For each nmId, fetches feedbacks and calculates average rating.
    Returns dict: {nm_id: {"valuation": 4.5, "feedbacksCount": 42}}
    """
    FEEDBACKS_API = "https://feedbacks-api.wildberries.ru"
    url = f"{FEEDBACKS_API}/api/v1/feedbacks"
    result = {}

    try:
        with httpx.Client(timeout=30) as client:
            for nm_id in nm_ids:
                _throttle()
                try:
                    resp = client.get(url, headers=_headers(api_token), params={
                        "nmId": nm_id,
                        "isAnswered": True,
                        "take": 5000,
                        "skip": 0,
                    })
                    if resp.status_code != 200:
                        print(f"[WB API] Feedbacks for nm={nm_id}: status={resp.status_code}")
                        continue
                    data = resp.json()
                    feedbacks = data.get("data", {}).get("feedbacks", [])
                    if feedbacks:
                        total_rating = sum(f.get("productValuation", 0) for f in feedbacks)
                        count = len(feedbacks)
                        avg_rating = round(total_rating / count, 1) if count > 0 else 0
                        # Also count unanswered feedbacks
                        unanswered = data.get("data", {}).get("countUnanswered", 0)
                        total_count = count + unanswered
                        result[nm_id] = {
                            "valuation": avg_rating,
                            "feedbacksCount": total_count,
                        }
                    else:
                        # Try unanswered feedbacks too
                        resp2 = client.get(url, headers=_headers(api_token), params={
                            "nmId": nm_id,
                            "isAnswered": False,
                            "take": 5000,
                            "skip": 0,
                        })
                        if resp2.status_code == 200:
                            data2 = resp2.json()
                            feedbacks2 = data2.get("data", {}).get("feedbacks", [])
                            if feedbacks2:
                                total_rating = sum(f.get("productValuation", 0) for f in feedbacks2)
                                count = len(feedbacks2)
                                avg_rating = round(total_rating / count, 1) if count > 0 else 0
                                result[nm_id] = {
                                    "valuation": avg_rating,
                                    "feedbacksCount": count,
                                }
                except Exception as e:
                    print(f"[WB API] Error fetching feedbacks for nm={nm_id}: {e}")
    except Exception as e:
        print(f"[WB API] Error in fetch_product_ratings: {e}")

    print(f"[WB API] Ratings fetched for {len(result)}/{len(nm_ids)} products")
    return result


def fetch_statistics_orders(api_token: str, date_from: Optional[datetime] = None) -> list[dict]:
    """GET /api/v1/supplier/orders — fetch orders using BOTH flag modes for maximum coverage.

    flag=0: Paginated by lastChangeDate cursor — catches recently modified orders.
    flag=1: By order creation date — catches orders that flag=0 misses.

    Merges and deduplicates results by srid for the widest possible coverage.
    Returns orders with: totalPrice, priceWithDisc, finishedPrice, spp, warehouseType, srid.
    """
    url = f"{STATISTICS_API}/api/v1/supplier/orders"
    if date_from is None:
        date_from = datetime.now(timezone.utc) - timedelta(days=90)

    all_orders = []
    seen_srids = set()

    # --- Mode 1: flag=0 (lastChangeDate cursor pagination) ---
    cursor_date = date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    try:
        with httpx.Client(timeout=120) as client:
            while True:
                params = {"dateFrom": cursor_date, "flag": 0}
                # Retry with backoff on 429
                resp = None
                for attempt in range(4):
                    _throttle()
                    resp = client.get(url, headers=_headers(api_token), params=params)
                    if resp.status_code == 429:
                        wait = min(60 * (attempt + 1), 180)
                        print(f"[WB API] stat orders flag=0: 429, waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    break
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or not data:
                    break
                all_orders.extend(data)
                for o in data:
                    srid = o.get("srid", "")
                    if srid:
                        seen_srids.add(srid)
                last_change = data[-1].get("lastChangeDate", "")
                if not last_change or last_change == cursor_date:
                    break
                cursor_date = last_change
                print(f"[WB API] stat orders flag=0 page: {len(data)} rows, cursor={cursor_date[:19]}")
                time.sleep(1)  # Pause between pages
    except Exception as e:
        print(f"[WB API] Error fetching statistics orders (flag=0): {e}")

    flag0_count = len(all_orders)

    # --- Mode 2: flag=1 (order creation date) ---
    # Single request from 21 days ago to catch orders that flag=0 might miss.
    # flag=1 returns ALL orders created since dateFrom.
    flag1_new = 0
    try:
        with httpx.Client(timeout=120) as client:
            flag1_date = (datetime.now(timezone.utc) - timedelta(days=21)).strftime("%Y-%m-%dT00:00:00.000Z")
            resp = None
            for attempt in range(4):
                _throttle()
                resp = client.get(url, headers=_headers(api_token),
                                  params={"dateFrom": flag1_date, "flag": 1})
                if resp.status_code == 429:
                    wait = min(60 * (attempt + 1), 180)
                    print(f"[WB API] stat orders flag=1: 429, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                break
            if resp and resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    for o in data:
                        srid = o.get("srid", "")
                        if srid and srid not in seen_srids:
                            all_orders.append(o)
                            seen_srids.add(srid)
                            flag1_new += 1
        if flag1_new:
            print(f"[WB API] stat orders flag=1: {flag1_new} new orders")
    except Exception as e:
        print(f"[WB API] Error fetching statistics orders (flag=1): {e}")

    print(f"[WB API] statistics orders total: {len(all_orders)} (flag0={flag0_count}, flag1_new={flag1_new})")
    return all_orders


def fetch_statistics_sales(api_token: str, date_from: Optional[datetime] = None) -> list[dict]:
    """GET /api/v1/supplier/sales — fetch ALL sales from Statistics API with pagination.

    Same pagination approach as fetch_statistics_orders.
    """
    url = f"{STATISTICS_API}/api/v1/supplier/sales"
    if date_from is None:
        date_from = datetime.now(timezone.utc) - timedelta(days=90)

    all_sales = []
    cursor_date = date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    try:
        with httpx.Client(timeout=120) as client:
            while True:
                params = {"dateFrom": cursor_date, "flag": 0}
                resp = None
                for attempt in range(4):
                    _throttle()
                    resp = client.get(url, headers=_headers(api_token), params=params)
                    if resp.status_code == 429:
                        wait = min(60 * (attempt + 1), 180)
                        print(f"[WB API] stat sales: 429, waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    break
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or not data:
                    break
                all_sales.extend(data)
                last_change = data[-1].get("lastChangeDate", "")
                if not last_change or last_change == cursor_date:
                    break
                cursor_date = last_change
                time.sleep(1)  # Pause between pages
    except Exception as e:
        print(f"[WB API] Error fetching statistics sales: {e}")

    print(f"[WB API] statistics sales total: {len(all_sales)}")
    return all_sales


def fetch_report_detail(api_token: str, date_from: str, date_to: str) -> list[dict]:
    """GET /api/v5/supplier/reportDetailByPeriod — fetch detailed sales report.

    Splits large date ranges into 2-week chunks to avoid connection timeouts.
    Uses cursor-based pagination via rrdid parameter within each chunk.
    """
    from datetime import datetime as _dt, timedelta as _td

    start = _dt.strptime(date_from, "%Y-%m-%d")
    end = _dt.strptime(date_to, "%Y-%m-%d")
    chunk_days = 14
    url = f"{STATISTICS_API}/api/v5/supplier/reportDetailByPeriod"
    all_records = []

    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + _td(days=chunk_days), end)
        cf = chunk_start.strftime("%Y-%m-%d")
        ct = chunk_end.strftime("%Y-%m-%d")
        rrdid = 0

        try:
            with httpx.Client(timeout=120) as client:
                while True:
                    params = {"dateFrom": cf, "dateTo": ct, "rrdid": rrdid}
                    # Retry with exponential backoff on 429
                    resp = None
                    for attempt in range(6):
                        _throttle()
                        resp = client.get(url, headers=_headers(api_token), params=params)
                        if resp.status_code == 429:
                            wait = min(30 * (2 ** attempt), 300)
                            print(f"[WB API] Report detail 429, attempt {attempt+1}/6, waiting {wait}s...")
                            time.sleep(wait)
                            continue
                        break
                    if resp is None or resp.status_code == 429:
                        print(f"[WB API] Report detail: exhausted retries for chunk {cf}~{ct}")
                        break
                    if resp.status_code == 204 or not resp.content:
                        break
                    resp.raise_for_status()
                    data = resp.json()
                    if not isinstance(data, list) or not data:
                        break
                    all_records.extend(data)
                    rrdid = data[-1].get("rrd_id", 0)
                    if not rrdid:
                        break
                    time.sleep(3)  # Extra delay between pagination requests
        except Exception as e:
            print(f"[WB API] Error fetching report detail chunk {cf}~{ct}: {e}")

        time.sleep(5)  # Pause between chunks to avoid rate limits
        chunk_start = chunk_end

    return all_records


def fetch_ad_campaign_ids(api_token: str) -> list[dict]:
    """GET /adv/v1/promotion/count — get all campaign IDs with type/status."""
    url = f"{ADVERT_API}/adv/v1/promotion/count"
    try:
        _throttle()
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=_headers(api_token))
            resp.raise_for_status()
            data = resp.json()
            results = []
            for group in data.get("adverts", []):
                group_type = group.get("type", 0)
                group_status = group.get("status", 0)
                for item in group.get("advert_list", []):
                    advert_id = item.get("advertId")
                    if advert_id:
                        results.append({
                            "advertId": advert_id,
                            "type": group_type,
                            "status": group_status,
                            "changeTime": item.get("changeTime", ""),
                        })
            return results
    except Exception as e:
        print(f"[WB API] Error fetching ad campaign IDs: {e}")
        return []


def fetch_ad_details(api_token: str, advert_ids: list[int]) -> list[dict]:
    """GET /api/advert/v2/adverts — batch fetch campaign details."""
    if not advert_ids:
        return []
    url = f"{ADVERT_API}/api/advert/v2/adverts"
    all_details = []
    try:
        with httpx.Client(timeout=30) as client:
            for i in range(0, len(advert_ids), 50):
                batch = advert_ids[i:i + 50]
                _throttle()
                resp = client.get(url, headers=_headers(api_token),
                                  params={"ids": ",".join(str(x) for x in batch)})
                resp.raise_for_status()
                data = resp.json()
                adverts = data.get("adverts", []) if isinstance(data, dict) else data
                if isinstance(adverts, list):
                    all_details.extend(adverts)
    except Exception as e:
        print(f"[WB API] Error fetching ad details: {e}")
    return all_details


def fetch_ad_fullstats(api_token: str, campaign_ids: list[int], date_from: str, date_to: str) -> list[dict]:
    """GET /adv/v3/fullstats — fetch daily stats per campaign per nmId."""
    if not campaign_ids:
        return []
    url = f"{ADVERT_API}/adv/v3/fullstats"
    all_stats = []
    try:
        with httpx.Client(timeout=60) as client:
            for i in range(0, len(campaign_ids), 100):
                batch = campaign_ids[i:i + 100]
                _throttle()
                resp = client.get(url, headers=_headers(api_token),
                                  params={
                                      "ids": ",".join(str(x) for x in batch),
                                      "beginDate": date_from,
                                      "endDate": date_to,
                                  })
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    all_stats.extend(data)
                elif isinstance(data, dict) and "advertId" in data:
                    all_stats.append(data)
    except Exception as e:
        print(f"[WB API] Error fetching ad fullstats: {e}")
    return all_stats


def fetch_ad_budget(api_token: str, advert_id: int) -> dict:
    """GET /adv/v1/budget — get campaign budget info.

    Returns: {cash, netting, total, currency}
    total > 0 means campaign is funded (active or paused with budget).
    total = 0 means campaign has no budget (likely archived).
    """
    url = f"{ADVERT_API}/adv/v1/budget"
    try:
        _throttle()
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=_headers(api_token), params={"id": advert_id})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[WB API] Error fetching budget for campaign {advert_id}: {e}")
        return {}


def fetch_ad_budgets_batch(api_token: str, advert_ids: list[int]) -> dict[int, dict]:
    """Fetch budgets for multiple campaigns. Returns {advert_id: budget_info}."""
    result = {}
    for aid in advert_ids:
        budget = fetch_ad_budget(api_token, aid)
        if budget:
            result[aid] = budget
    return result


def fetch_ad_campaign_names(api_token: str) -> dict[int, str]:
    """GET /adv/v1/upd — get campaign display names from costs history."""
    url = f"{ADVERT_API}/adv/v1/upd"
    try:
        _throttle()
        with httpx.Client(timeout=30) as client:
            from datetime import datetime, timedelta
            today = datetime.now()
            date_from = (today - timedelta(days=30)).strftime("%Y-%m-%d")
            date_to = today.strftime("%Y-%m-%d")
            resp = client.get(url, headers=_headers(api_token),
                              params={"from": date_from, "to": date_to})
            resp.raise_for_status()
            data = resp.json()
            names = {}
            if isinstance(data, list):
                for item in data:
                    cid = item.get("campId") or item.get("advertId")
                    name = item.get("campName") or item.get("name")
                    if cid and name and cid not in names:
                        names[cid] = name
            return names
    except Exception as e:
        print(f"[WB API] Error fetching ad campaign names: {e}")
        return {}


def fetch_public_rub_prices(nm_ids: list[int]) -> dict[int, float]:
    """Fetch RUB prices from WB public card API (no auth needed).

    Tries multiple approaches: card.wb.ru with session cookies, then search API.
    Returns dict: {nm_id: rub_price}
    """
    result = {}
    batch_size = 50
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    }

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            # Step 1: visit main site to get cookies
            try:
                client.get("https://www.wildberries.ru/", headers=headers)
            except Exception:
                pass

            # Step 2: fetch card details with cookies
            for i in range(0, len(nm_ids), batch_size):
                batch = nm_ids[i:i + batch_size]
                nm_str = ";".join(str(n) for n in batch)
                url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={nm_str}"
                try:
                    time.sleep(0.5)
                    resp = client.get(url, headers={
                        **headers,
                        "Origin": "https://www.wildberries.ru",
                        "Referer": "https://www.wildberries.ru/",
                    })
                    if resp.status_code != 200:
                        print(f"[WB Public] Card v2 status={resp.status_code}, trying v1...")
                        # Try v1 endpoint
                        url_v1 = f"https://card.wb.ru/cards/detail?appType=1&curr=rub&dest=-1257786&nm={nm_str}"
                        resp = client.get(url_v1, headers=headers)
                        if resp.status_code != 200:
                            print(f"[WB Public] Card v1 status={resp.status_code}")
                            continue
                    data = resp.json()
                    products = data.get("data", {}).get("products", [])
                    for p in products:
                        pid = p.get("id")
                        sale_price = p.get("salePriceU", 0)
                        if pid and sale_price > 0:
                            result[pid] = sale_price / 100.0
                except Exception as e:
                    print(f"[WB Public] Error fetching batch: {e}")
    except Exception as e:
        print(f"[WB Public] Error: {e}")

    # Fallback: try search API if card API failed
    if not result:
        print("[WB Public] Card API failed, trying search API...")
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                try:
                    client.get("https://www.wildberries.ru/", headers=headers)
                except Exception:
                    pass
                # Search by nm_id in small batches
                for nm_id in nm_ids:
                    try:
                        time.sleep(0.3)
                        url = f"https://search.wb.ru/exactmatch/ru/common/v7/search?appType=1&curr=rub&dest=-1257786&query={nm_id}&resultset=catalog&suppressSpellcheck=false"
                        resp = client.get(url, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            products = data.get("data", {}).get("products", [])
                            for p in products:
                                pid = p.get("id")
                                sale_price = p.get("salePriceU", 0)
                                if pid == nm_id and sale_price > 0:
                                    result[pid] = sale_price / 100.0
                                    break
                        else:
                            print(f"[WB Public] Search status={resp.status_code}")
                            break  # If search also blocked, stop
                    except Exception as e:
                        print(f"[WB Public] Search error for {nm_id}: {e}")
        except Exception as e:
            print(f"[WB Public] Search error: {e}")

    print(f"[WB Public] RUB prices fetched for {len(result)}/{len(nm_ids)} products")
    return result
