from app.models.user import User
from app.models.shop import Shop
from app.models.product import Product, SkuMapping
from app.models.order import Order, OrderItem
from app.utils.security import hash_password, encrypt_token


def _setup(client, db):
    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    shop = Shop(name="店铺A", type="local", api_token=encrypt_token("tok"), is_active=True)
    product = Product(sku="SYS-001", name="鞋子", purchase_price=100.0)
    db.add_all([user, shop, product])
    db.commit()
    mapping = SkuMapping(shop_id=shop.id, shop_sku="WB-SKU-1", product_id=product.id, wb_product_name="鞋子")
    db.add(mapping)
    db.commit()
    order = Order(wb_order_id="WB-001", shop_id=shop.id, order_type="FBS", status="completed", total_price=2350.0)
    db.add(order)
    db.commit()
    item = OrderItem(order_id=order.id, product_name="鞋子", sku="WB-SKU-1", quantity=2, price=1175.0, commission=235.0, logistics_cost=150.0)
    db.add(item)
    db.commit()
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"], shop.id


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_finance_summary(client, db):
    token, _ = _setup(client, db)
    resp = client.get("/api/finance/summary", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sales"] == 2350.0
    assert data["total_commission"] == 235.0
    assert data["total_logistics"] == 150.0
    assert data["total_purchase_cost"] == 200.0
    assert data["total_profit"] == 1965.0


def test_finance_summary_filter_by_shop(client, db):
    token, shop_id = _setup(client, db)
    resp = client.get(f"/api/finance/summary?shop_id={shop_id}", headers=_auth(token))
    assert resp.json()["total_sales"] == 2350.0
    resp = client.get("/api/finance/summary?shop_id=9999", headers=_auth(token))
    assert resp.json()["total_sales"] == 0
