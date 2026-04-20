from datetime import date, datetime, timezone
from app.models.user import User
from app.models.shop import Shop
from app.models.order import Order
from app.models.finance import FinanceOrderRecord, FinanceOtherFee
from app.utils.security import hash_password, encrypt_token


def _setup_admin(db):
    u = User(username="a", password_hash=hash_password("pw"), role="admin",
             is_active=True, permissions="finance")
    db.add(u); db.commit()
    return u


def _login(client):
    r = client.post("/api/auth/login", data={"username": "a", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_shop(db, type_="local"):
    s = Shop(name=f"Shop-{type_}", type=type_, api_token=encrypt_token("t"), is_active=True)
    db.add(s); db.commit()
    return s


def _make_record(db, shop, srid, **over):
    defaults = dict(
        shop_id=shop.id, srid=srid, currency="RUB",
        sale_date=date(2026, 4, 13), order_date=date(2026, 4, 8),
        report_period_start=date(2026, 4, 6), report_period_end=date(2026, 4, 12),
        nm_id="1", shop_sku="SKU-1", product_name="P", quantity=1,
        net_to_seller=100.0, delivery_fee=10.0, commission_amount=5.0, commission_rate=9.5,
        purchase_cost=20.0, net_profit=70.0, has_sku_mapping=True,
    )
    defaults.update(over)
    rec = FinanceOrderRecord(**defaults)
    db.add(rec); db.commit()
    return rec


def test_summary_returns_aggregates(client, db):
    _setup_admin(db)
    shop = _make_shop(db, "local")
    _make_record(db, shop, "A", net_to_seller=100, purchase_cost=20, net_profit=70)
    _make_record(db, shop, "B", net_to_seller=200, purchase_cost=40, net_profit=140)
    db.add(FinanceOtherFee(shop_id=shop.id, currency="RUB", sale_date=date(2026, 4, 10),
                           fee_type="fine", amount=50, raw_row={})); db.commit()

    headers = _login(client)
    r = client.get("/api/finance/summary", params={
        "shop_type": "local", "date_from": "2026-04-01", "date_to": "2026-04-30",
    }, headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert d["order_count"] == 2
    assert d["total_net_to_seller"] == 300
    assert d["total_purchase_cost"] == 60
    assert d["total_net_profit"] == 210
    assert d["total_other_fees"] == 50
    assert d["final_profit"] == 160
    assert d["currency"] == "RUB"


def test_summary_currency_from_shop_type(client, db):
    _setup_admin(db)
    shop_cb = _make_shop(db, "cross_border")
    _make_record(db, shop_cb, "C1", currency="CNY", net_to_seller=50, net_profit=30)
    headers = _login(client)
    r = client.get("/api/finance/summary", params={
        "shop_type": "cross_border", "date_from": "2026-04-01", "date_to": "2026-04-30",
    }, headers=headers)
    assert r.json()["currency"] == "CNY"
    assert r.json()["order_count"] == 1


def test_orders_list_pagination_and_filter(client, db):
    _setup_admin(db)
    shop = _make_shop(db, "local")
    for i in range(25):
        _make_record(db, shop, f"S{i}", has_sku_mapping=(i % 2 == 0))
    headers = _login(client)
    r = client.get("/api/finance/orders", params={
        "shop_type": "local", "date_from": "2026-04-01", "date_to": "2026-04-30",
        "page": 2, "page_size": 10,
    }, headers=headers)
    d = r.json()
    assert d["total"] == 25
    assert len(d["items"]) == 10
    # filter unmapped
    r = client.get("/api/finance/orders", params={
        "shop_type": "local", "date_from": "2026-04-01", "date_to": "2026-04-30",
        "has_mapping": "false",
    }, headers=headers)
    assert all(not it["has_sku_mapping"] for it in r.json()["items"])


def test_other_fees_list(client, db):
    _setup_admin(db)
    shop = _make_shop(db, "local")
    db.add_all([
        FinanceOtherFee(shop_id=shop.id, currency="RUB", sale_date=date(2026, 4, 10),
                        fee_type="storage", amount=100, raw_row={}),
        FinanceOtherFee(shop_id=shop.id, currency="RUB", sale_date=date(2026, 4, 11),
                        fee_type="fine", amount=50, raw_row={}),
    ]); db.commit()
    headers = _login(client)
    r = client.get("/api/finance/other-fees", params={
        "shop_type": "local", "date_from": "2026-04-01", "date_to": "2026-04-30",
    }, headers=headers)
    assert r.json()["total"] == 2


def test_reconciliation_missing_in_orders(client, db):
    """财报有 Srid，但 orders 表里找不到对应 srid。"""
    _setup_admin(db)
    shop = _make_shop(db, "local")
    _make_record(db, shop, "ORPHAN", net_to_seller=150)
    headers = _login(client)
    r = client.get("/api/finance/reconciliation", params={
        "shop_type": "local", "date_from": "2026-04-01", "date_to": "2026-04-30",
    }, headers=headers)
    d = r.json()
    assert len(d["missing_in_orders"]) == 1
    assert d["missing_in_orders"][0]["srid"] == "ORPHAN"


def test_reconciliation_missing_in_finance(client, db):
    """Order 存在，srid 非空，但财报里没这个 srid。"""
    _setup_admin(db)
    shop = _make_shop(db, "local")
    order = Order(wb_order_id="O1", srid="MISSING", shop_id=shop.id,
                  order_type="FBS", status="delivered", total_price=100,
                  created_at=datetime(2026, 4, 15, tzinfo=timezone.utc))
    db.add(order); db.commit()
    headers = _login(client)
    r = client.get("/api/finance/reconciliation", params={
        "shop_type": "local", "date_from": "2026-04-01", "date_to": "2026-04-30",
    }, headers=headers)
    d = r.json()
    assert any(x["srid"] == "MISSING" for x in d["missing_in_finance"])


def test_sync_endpoint_requires_admin(client, db):
    from app.models.user import User
    from app.utils.security import hash_password
    op = User(username="op", password_hash=hash_password("pw"), role="operator",
              is_active=True, permissions="finance")
    db.add(op); db.commit()
    r = client.post("/api/auth/login", data={"username": "op", "password": "pw"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    resp = client.post("/api/finance/sync", json={
        "shop_ids": [1], "date_from": "2026-04-01", "date_to": "2026-04-07",
    }, headers=headers)
    assert resp.status_code == 403


def test_sync_endpoint_creates_log(client, db, monkeypatch):
    _setup_admin(db)
    shop = _make_shop(db, "local")
    # make sync_shop a no-op that only updates the log
    def fake_sync(db_, shop_, *, date_from, date_to, triggered_by, user_id):
        from app.models.finance import FinanceSyncLog
        from datetime import datetime, timezone
        log = FinanceSyncLog(shop_id=shop_.id, triggered_by=triggered_by, user_id=user_id,
                             date_from=date_from, date_to=date_to, status="success",
                             rows_fetched=0, orders_merged=0, other_fees_count=0,
                             finished_at=datetime.now(timezone.utc))
        db_.add(log); db_.commit()
        return log
    monkeypatch.setattr("app.routers.finance._sync_shop_blocking", fake_sync)

    headers = _login(client)
    r = client.post("/api/finance/sync", json={
        "shop_ids": [shop.id], "date_from": "2026-04-01", "date_to": "2026-04-07",
    }, headers=headers)
    assert r.status_code == 200
    assert len(r.json()["sync_log_ids"]) == 1


def test_sync_logs_listing(client, db):
    _setup_admin(db)
    shop = _make_shop(db, "local")
    from app.models.finance import FinanceSyncLog
    log = FinanceSyncLog(shop_id=shop.id, triggered_by="manual", user_id=None,
                         date_from=date(2026, 4, 1), date_to=date(2026, 4, 7),
                         status="success", rows_fetched=10, orders_merged=3, other_fees_count=1)
    db.add(log); db.commit()
    headers = _login(client)
    r = client.get("/api/finance/sync-logs", params={"shop_id": shop.id}, headers=headers)
    d = r.json()
    assert len(d) == 1
    assert d[0]["rows_fetched"] == 10


def test_recalc_profit_refreshes_records(client, db):
    from app.models.product import Product, SkuMapping
    _setup_admin(db)
    shop = _make_shop(db, "local")
    _make_record(db, shop, "R1", shop_sku="NEW-SKU", quantity=2,
                 purchase_cost=0, has_sku_mapping=False, net_profit=100,
                 net_to_seller=100, delivery_fee=0, fine=0, storage_fee=0, deduction=0)
    product = Product(sku="P-NEW", purchase_price=15)
    db.add(product); db.commit()
    db.add(SkuMapping(shop_id=shop.id, shop_sku="NEW-SKU", product_id=product.id)); db.commit()

    headers = _login(client)
    r = client.post("/api/finance/recalc-profit", json={"shop_id": shop.id}, headers=headers)
    assert r.status_code == 200

    from app.models.finance import FinanceOrderRecord
    rec = db.query(FinanceOrderRecord).filter_by(srid="R1").first()
    db.refresh(rec)
    assert rec.has_sku_mapping is True
    assert rec.purchase_cost == 30.0
    assert rec.net_profit == 70.0


def test_weekly_finance_sync_function_exists():
    """函数存在且签名正确（scheduler 注册处会引用）。"""
    from app.services.scheduler import weekly_finance_sync
    import inspect
    sig = inspect.signature(weekly_finance_sync)
    assert len(sig.parameters) == 0  # 无参数，cron 直接调


def test_start_scheduler_registers_weekly_job():
    """start_scheduler 后，scheduler 里有 weekly_finance_sync job。"""
    from app.services.scheduler import scheduler
    # main.py 启动时已调 start_scheduler，或者这里主动调
    from app.services.scheduler import start_scheduler
    # 已启动过就跳过
    if not scheduler.running:
        start_scheduler()
    job = scheduler.get_job("weekly_finance_sync")
    assert job is not None
