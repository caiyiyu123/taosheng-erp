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
    order = Order(wb_order_id="WB-001", shop_id=shop.id, order_type="FBS", status="pending", total_price=2350.0)
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
    assert "today_orders" in card
    assert "today_sales" in card
    assert "last_30d_sales" in card


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
