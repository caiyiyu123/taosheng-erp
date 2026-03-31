from datetime import datetime
from app.models.user import User
from app.models.shop import Shop
from app.models.product import Product, SkuMapping
from app.models.order import Order, OrderItem, OrderStatusLog
from app.models.inventory import Inventory


def test_create_user(db):
    user = User(username="admin", password_hash="hashed", role="admin", is_active=True)
    db.add(user)
    db.commit()
    assert user.id is not None
    assert user.username == "admin"
    assert user.role == "admin"


def test_create_shop(db):
    shop = Shop(name="本土店A", type="local", api_token="encrypted_token", is_active=True)
    db.add(shop)
    db.commit()
    assert shop.id is not None
    assert shop.type == "local"


def test_create_product(db):
    product = Product(
        sku="SYS-001", name="测试商品", image="",
        purchase_price=100.0, weight=500, length=30, width=20, height=10,
    )
    db.add(product)
    db.commit()
    assert product.id is not None
    assert product.sku == "SYS-001"


def test_sku_mapping(db):
    shop = Shop(name="店铺A", type="local", api_token="token", is_active=True)
    product = Product(sku="SYS-001", name="商品A", purchase_price=50.0, weight=100, length=10, width=10, height=10)
    db.add_all([shop, product])
    db.commit()
    mapping = SkuMapping(shop_id=shop.id, shop_sku="WB-SKU-001", product_id=product.id, wb_product_name="WB商品A", wb_barcode="123456")
    db.add(mapping)
    db.commit()
    assert mapping.id is not None
    assert mapping.product_id == product.id


def test_create_order_with_items(db):
    shop = Shop(name="店铺A", type="local", api_token="token", is_active=True)
    db.add(shop)
    db.commit()
    order = Order(
        wb_order_id="WB-ORD-001", shop_id=shop.id, order_type="FBS",
        status="pending", total_price=2350.0, currency="RUB",
    )
    db.add(order)
    db.commit()
    item = OrderItem(
        order_id=order.id, wb_product_id="WB-P-001", product_name="鞋子",
        sku="WB-SKU-001", barcode="123", quantity=1, price=2350.0,
        commission=235.0, logistics_cost=150.0,
    )
    db.add(item)
    db.commit()
    assert len(order.items) == 1


def test_create_inventory(db):
    shop = Shop(name="店铺A", type="local", api_token="token", is_active=True)
    db.add(shop)
    db.commit()
    inv = Inventory(
        shop_id=shop.id, wb_product_id="WB-P-001", product_name="鞋子",
        sku="WB-SKU-001", barcode="123", stock_fbs=50, stock_fbw=30,
        low_stock_threshold=10,
    )
    db.add(inv)
    db.commit()
    assert inv.stock_fbs == 50
