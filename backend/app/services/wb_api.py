import httpx
import time
import threading
from typing import Optional
from datetime import datetime

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


def fetch_orders(api_token: str, date_from: Optional[datetime] = None) -> list[dict]:
    """GET /api/v3/orders — fetch historical orders with pagination.

    Each order has: id, createdAt, warehouseId, nmId, chrtId, price,
    convertedPrice, currencyCode, cargoType, skus[], article, etc.
    """
    url = f"{MARKETPLACE_API}/api/v3/orders"
    all_orders = []
    next_cursor = 0

    try:
        with httpx.Client(timeout=30) as client:
            while True:
                params = {"limit": 1000, "next": next_cursor}
                if date_from:
                    params["dateFrom"] = int(date_from.timestamp())

                _throttle()
                resp = client.get(url, headers=_headers(api_token), params=params)
                resp.raise_for_status()
                data = resp.json()

                orders = data.get("orders", [])
                all_orders.extend(orders)

                # Pagination: if next is 0 or no more orders, stop
                next_cursor = data.get("next", 0)
                if not orders or next_cursor == 0:
                    break

    except Exception as e:
        print(f"[WB API] Error fetching orders: {e}")

    return all_orders


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


def fetch_statistics_orders(api_token: str, date_from: Optional[datetime] = None) -> list[dict]:
    """GET /api/v1/supplier/orders — fetch orders from Statistics API.

    Returns orders with actual prices: totalPrice, priceWithDisc, finishedPrice, spp.
    Data updates every 30 min, max 90 days history.

    Args:
        date_from: Fetch orders updated since this date. If None, defaults to 30 days ago.
    """
    url = f"{STATISTICS_API}/api/v1/supplier/orders"
    if date_from is None:
        from datetime import timedelta, timezone
        date_from = datetime.now(timezone.utc) - timedelta(days=30)

    params = {"dateFrom": date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")}

    try:
        _throttle()
        with httpx.Client(timeout=60) as client:
            resp = client.get(url, headers=_headers(api_token), params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[WB API] Error fetching statistics orders: {e}")
        return []


def fetch_statistics_sales(api_token: str, date_from: Optional[datetime] = None) -> list[dict]:
    """GET /api/v1/supplier/sales — fetch sales data from Statistics API.

    Returns sales with: forPay, finishedPrice, priceWithDisc, saleID, spp.
    Data updates every 30 min, max 90 days history.
    """
    url = f"{STATISTICS_API}/api/v1/supplier/sales"
    if date_from is None:
        from datetime import timedelta, timezone
        date_from = datetime.now(timezone.utc) - timedelta(days=30)

    params = {"dateFrom": date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")}

    try:
        _throttle()
        with httpx.Client(timeout=60) as client:
            resp = client.get(url, headers=_headers(api_token), params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[WB API] Error fetching statistics sales: {e}")
        return []


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
