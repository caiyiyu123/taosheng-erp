from app.models.user import User
from app.models.shop import Shop
from app.models.order import Order, OrderItem
from app.models.inventory import Inventory
from app.utils.security import hash_password, encrypt_token


def _setup(client, db):
    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    shop = Shop(name="店铺A", type="local", api_token=encrypt_token("tok"), is_active=True)
    db.add_all([user, shop])
    db.commit()
    order = Order(wb_order_id="WB-001", shop_id=shop.id, order_type="FBS", status="pending", total_price=2350.0, price_rub=2350.0)
    db.add(order)
    db.commit()
    item = OrderItem(order_id=order.id, product_name="鞋子", sku="WB-SKU-1", quantity=1, price=2350.0, commission=235.0, logistics_cost=150.0)
    low_inv = Inventory(shop_id=shop.id, product_name="低库存品", sku="WB-LOW", stock_fbs=2, stock_fbw=1, low_stock_threshold=10)
    db.add_all([item, low_inv])
    db.commit()
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_stats(client, db):
    token = _setup(client, db)
    resp = client.get("/api/dashboard/stats", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["today_orders"] >= 0
    assert data["today_sales"] >= 0
    assert "pending_shipment" in data
    assert "low_stock_count" in data


def test_dashboard_shops_returns_cards(client, db):
    token = _setup(client, db)
    resp = client.get("/api/dashboard/shops", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "shops" in data
    assert len(data["shops"]) == 1
    card = data["shops"][0]
    assert card["name"] == "店铺A"
    assert card["id"] > 0
    assert card["today_orders"] == 1
    assert card["today_sales"] == 2350.0
    assert card["last_30d_sales"] == 2350.0


def test_dashboard_shops_includes_shops_without_orders(client, db):
    from app.models.shop import Shop
    from app.utils.security import encrypt_token
    token = _setup(client, db)
    empty_shop = Shop(name="空店铺", type="local", api_token=encrypt_token("t2"), is_active=True)
    db.add(empty_shop)
    db.commit()
    resp = client.get("/api/dashboard/shops", headers=_auth(token))
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["shops"]]
    assert "空店铺" in names
    empty = next(s for s in resp.json()["shops"] if s["name"] == "空店铺")
    assert empty["today_orders"] == 0
    assert empty["today_sales"] == 0
    assert empty["last_30d_sales"] == 0


def test_shop_products_ranking(client, db):
    from app.models.shop import Shop
    from app.models.order import Order, OrderItem
    from app.models.user import User
    from app.utils.security import hash_password, encrypt_token

    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    shop = Shop(name="店铺R", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add_all([user, shop])
    db.commit()

    order1 = Order(wb_order_id="O1", shop_id=shop.id, order_type="FBS", status="pending", price_rub=100.0)
    order2 = Order(wb_order_id="O2", shop_id=shop.id, order_type="FBS", status="pending", price_rub=200.0)
    db.add_all([order1, order2])
    db.commit()
    db.add_all([
        OrderItem(order_id=order1.id, wb_product_id="111", product_name="商品甲", sku="SKU1", quantity=1, price=100.0),
        OrderItem(order_id=order2.id, wb_product_id="111", product_name="商品甲", sku="SKU1", quantity=1, price=200.0),
    ])
    db.commit()

    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    tok = resp.json()["access_token"]
    r = client.get(f"/api/dashboard/shops/{shop.id}/products", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert data["shop_id"] == shop.id
    assert data["shop_name"] == "店铺R"
    assert len(data["products"]) == 1
    p = data["products"][0]
    assert p["nm_id"] == "111"
    assert p["product_name"] == "商品甲"
    assert p["today_orders"] == 2
    assert p["yesterday_orders"] == 0
    assert p["last_7d_orders"] == 2
    assert p["last_30d_orders"] == 2


def test_shop_products_forbidden_for_other_shop(client, db):
    from app.models.shop import Shop
    from app.models.user import User
    from app.utils.security import hash_password, encrypt_token

    shop_a = Shop(name="A", type="local", api_token=encrypt_token("ta"), is_active=True)
    shop_b = Shop(name="B", type="local", api_token=encrypt_token("tb"), is_active=True)
    db.add_all([shop_a, shop_b])
    db.commit()
    user = User(username="op", password_hash=hash_password("x"), role="operator", is_active=True)
    user.shops = [shop_a]
    db.add(user)
    db.commit()

    resp = client.post("/api/auth/login", data={"username": "op", "password": "x"})
    tok = resp.json()["access_token"]
    r = client.get(f"/api/dashboard/shops/{shop_b.id}/products", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_product_daily_orders_fills_missing_dates(client, db):
    from datetime import datetime, timezone, timedelta
    from app.models.shop import Shop
    from app.models.order import Order, OrderItem
    from app.models.user import User
    from app.utils.security import hash_password, encrypt_token

    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    shop = Shop(name="SD", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add_all([user, shop])
    db.commit()

    msk = timezone(timedelta(hours=3))
    today_msk = datetime.now(msk).date()
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    order = Order(
        wb_order_id="OD1", shop_id=shop.id, order_type="FBS", status="pending",
        price_rub=50.0, created_at=now_utc_naive,
    )
    db.add(order)
    db.commit()
    db.add(OrderItem(order_id=order.id, wb_product_id="777", product_name="商品日", sku="K", quantity=1, price=50.0))
    db.commit()

    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    tok = resp.json()["access_token"]
    url = f"/api/dashboard/shops/{shop.id}/products/777/daily?end_date={today_msk.isoformat()}&days=7"
    r = client.get(url, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["daily"]) == 7
    assert data["daily"][-1]["date"] == today_msk.isoformat()
    assert data["daily"][-1]["orders"] == 1
    # All 6 days before today must be gap-filled with zeros
    for day in data["daily"][:-1]:
        assert day["orders"] == 0, f"Expected 0 orders on {day['date']}, got {day['orders']}"


def test_product_daily_forbidden_for_other_shop(client, db):
    from app.models.shop import Shop
    from app.models.user import User
    from app.utils.security import hash_password, encrypt_token

    shop_a = Shop(name="A", type="local", api_token=encrypt_token("ta"), is_active=True)
    shop_b = Shop(name="B", type="local", api_token=encrypt_token("tb"), is_active=True)
    db.add_all([shop_a, shop_b])
    db.commit()
    user = User(username="op2", password_hash=hash_password("x"), role="operator", is_active=True)
    user.shops = [shop_a]
    db.add(user)
    db.commit()

    resp = client.post("/api/auth/login", data={"username": "op2", "password": "x"})
    tok = resp.json()["access_token"]
    r = client.get(
        f"/api/dashboard/shops/{shop_b.id}/products/123/daily?end_date=2026-04-20&days=7",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
