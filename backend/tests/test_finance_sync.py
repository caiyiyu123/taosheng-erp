from datetime import date, datetime
from app.models.finance import FinanceOrderRecord, FinanceOtherFee, FinanceSyncLog
from app.models.shop import Shop
from app.utils.security import encrypt_token


def test_finance_order_record_model(db):
    shop = Shop(name="S", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add(shop); db.commit()
    rec = FinanceOrderRecord(
        shop_id=shop.id, srid="abc123", currency="RUB",
        sale_date=date(2026, 4, 13), order_date=date(2026, 4, 8),
        report_period_start=date(2026, 4, 6), report_period_end=date(2026, 4, 12),
        nm_id="507336942", shop_sku="SKU-1",
        quantity=1, net_to_seller=90.01, delivery_fee=13.04,
        purchase_cost=30.0, net_profit=46.97, has_sku_mapping=True,
    )
    db.add(rec); db.commit()
    assert rec.id > 0
    assert rec.currency == "RUB"


def test_finance_other_fee_model(db):
    shop = Shop(name="S", type="cross_border", api_token=encrypt_token("t"), is_active=True)
    db.add(shop); db.commit()
    fee = FinanceOtherFee(
        shop_id=shop.id, currency="CNY",
        sale_date=date(2026, 4, 10),
        report_period_start=date(2026, 4, 6), report_period_end=date(2026, 4, 12),
        fee_type="storage", fee_description="Хранение", amount=100.0,
        raw_row={"foo": "bar"},
    )
    db.add(fee); db.commit()
    assert fee.raw_row == {"foo": "bar"}


def test_finance_sync_log_model(db):
    shop = Shop(name="S", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add(shop); db.commit()
    log = FinanceSyncLog(
        shop_id=shop.id, triggered_by="cron",
        date_from=date(2026, 4, 6), date_to=date(2026, 4, 12),
        status="running",
    )
    db.add(log); db.commit()
    assert log.status == "running"
    assert log.started_at is not None
