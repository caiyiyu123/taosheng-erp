from app.models.user import User
from app.models.shop import Shop
from app.models.order import Order, OrderItem, OrderStatusLog
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
    log = OrderStatusLog(order_id=order.id, status="pending", wb_status="waiting")
    db.add_all([item, log])
    db.commit()
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"], shop.id, order.id


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_orders(client, db):
    token, shop_id, _ = _setup(client, db)
    resp = client.get("/api/orders", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_list_orders_filter_by_type(client, db):
    token, shop_id, _ = _setup(client, db)
    resp = client.get("/api/orders?order_type=FBS", headers=_auth(token))
    assert len(resp.json()["items"]) == 1
    resp = client.get("/api/orders?order_type=FBW", headers=_auth(token))
    assert len(resp.json()["items"]) == 0


def test_list_orders_filter_by_shop(client, db):
    token, shop_id, _ = _setup(client, db)
    resp = client.get(f"/api/orders?shop_id={shop_id}", headers=_auth(token))
    assert len(resp.json()["items"]) == 1
    resp = client.get("/api/orders?shop_id=9999", headers=_auth(token))
    assert len(resp.json()["items"]) == 0


def test_get_order_detail(client, db):
    token, _, order_id = _setup(client, db)
    resp = client.get(f"/api/orders/{order_id}", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["wb_order_id"] == "WB-001"
    assert len(data["items"]) == 1
    assert len(data["status_logs"]) == 1
