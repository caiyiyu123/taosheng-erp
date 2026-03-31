from app.models.user import User
from app.utils.security import hash_password


def _get_admin_token(client, db):
    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    db.add(user)
    db.commit()
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_product(client, db):
    token = _get_admin_token(client, db)
    resp = client.post("/api/products", json={
        "sku": "SYS-001", "name": "运动鞋", "purchase_price": 150.0,
        "weight": 800, "length": 35, "width": 25, "height": 15,
    }, headers=_auth(token))
    assert resp.status_code == 201
    assert resp.json()["sku"] == "SYS-001"


def test_list_products(client, db):
    token = _get_admin_token(client, db)
    client.post("/api/products", json={"sku": "SYS-001", "name": "商品A", "purchase_price": 100}, headers=_auth(token))
    client.post("/api/products", json={"sku": "SYS-002", "name": "商品B", "purchase_price": 200}, headers=_auth(token))
    resp = client.get("/api/products", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_update_product(client, db):
    token = _get_admin_token(client, db)
    create = client.post("/api/products", json={"sku": "SYS-001", "name": "商品A", "purchase_price": 100}, headers=_auth(token))
    pid = create.json()["id"]
    resp = client.put(f"/api/products/{pid}", json={"purchase_price": 180.0}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["purchase_price"] == 180.0


def test_delete_product(client, db):
    token = _get_admin_token(client, db)
    create = client.post("/api/products", json={"sku": "SYS-001", "name": "商品A", "purchase_price": 100}, headers=_auth(token))
    pid = create.json()["id"]
    resp = client.delete(f"/api/products/{pid}", headers=_auth(token))
    assert resp.status_code == 200


def test_duplicate_sku_rejected(client, db):
    token = _get_admin_token(client, db)
    client.post("/api/products", json={"sku": "SYS-001", "name": "A", "purchase_price": 100}, headers=_auth(token))
    resp = client.post("/api/products", json={"sku": "SYS-001", "name": "B", "purchase_price": 200}, headers=_auth(token))
    assert resp.status_code == 400
