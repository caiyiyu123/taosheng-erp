from app.models.user import User
from app.models.shop import Shop
from app.models.product import Product, SkuMapping
from app.utils.security import hash_password, encrypt_token


def _setup(client, db):
    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    shop = Shop(name="店铺A", type="local", api_token=encrypt_token("tok"), is_active=True)
    product = Product(sku="SYS-001", name="商品A", purchase_price=100)
    db.add_all([user, shop, product])
    db.commit()
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"], shop.id, product.id


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_shop_sku_mappings(client, db):
    token, shop_id, _ = _setup(client, db)
    mapping = SkuMapping(shop_id=shop_id, shop_sku="WB-001", wb_product_name="WB商品", wb_barcode="123")
    db.add(mapping)
    db.commit()
    resp = client.get(f"/api/shops/{shop_id}/sku-mappings", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["shop_sku"] == "WB-001"


def test_update_sku_mapping_link_product(client, db):
    token, shop_id, product_id = _setup(client, db)
    mapping = SkuMapping(shop_id=shop_id, shop_sku="WB-001", wb_product_name="WB商品", wb_barcode="123")
    db.add(mapping)
    db.commit()
    resp = client.put(f"/api/sku-mappings/{mapping.id}", json={"product_sku": "SYS-001"}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["product_id"] == product_id


def test_update_sku_mapping_unlink(client, db):
    token, shop_id, product_id = _setup(client, db)
    mapping = SkuMapping(shop_id=shop_id, shop_sku="WB-001", product_id=product_id, wb_product_name="WB商品", wb_barcode="123")
    db.add(mapping)
    db.commit()
    resp = client.put(f"/api/sku-mappings/{mapping.id}", json={"product_sku": ""}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["product_id"] is None


def test_link_nonexistent_sku_returns_404(client, db):
    token, shop_id, _ = _setup(client, db)
    mapping = SkuMapping(shop_id=shop_id, shop_sku="WB-001", wb_product_name="WB商品", wb_barcode="123")
    db.add(mapping)
    db.commit()
    resp = client.put(f"/api/sku-mappings/{mapping.id}", json={"product_sku": "NONEXISTENT"}, headers=_auth(token))
    assert resp.status_code == 404
