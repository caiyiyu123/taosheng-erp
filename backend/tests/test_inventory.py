from app.models.user import User
from app.models.shop import Shop
from app.models.inventory import Inventory
from app.utils.security import hash_password, encrypt_token


def _setup(client, db):
    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    shop = Shop(name="店铺A", type="local", api_token=encrypt_token("tok"), is_active=True)
    db.add_all([user, shop])
    db.commit()
    inv = Inventory(shop_id=shop.id, product_name="鞋子", sku="WB-SKU-1", stock_fbs=50, stock_fbw=30, low_stock_threshold=10)
    db.add(inv)
    db.commit()
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"], shop.id


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_inventory(client, db):
    token, _ = _setup(client, db)
    resp = client.get("/api/inventory", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_inventory_filter_by_shop(client, db):
    token, shop_id = _setup(client, db)
    resp = client.get(f"/api/inventory?shop_id={shop_id}", headers=_auth(token))
    assert len(resp.json()) == 1
    resp = client.get("/api/inventory?shop_id=9999", headers=_auth(token))
    assert len(resp.json()) == 0


def test_low_stock_alerts(client, db):
    token, shop_id = _setup(client, db)
    low = Inventory(shop_id=shop_id, product_name="低库存品", sku="WB-LOW", stock_fbs=3, stock_fbw=2, low_stock_threshold=10)
    db.add(low)
    db.commit()
    resp = client.get("/api/inventory/low-stock", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["sku"] == "WB-LOW"
