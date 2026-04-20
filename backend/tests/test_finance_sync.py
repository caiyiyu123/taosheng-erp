from datetime import date, datetime
from unittest.mock import patch, MagicMock
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


def test_fetch_finance_report_paginates():
    """fetch_finance_report 按 rrdid 分页直到返回空。"""
    from app.services.wb_api import fetch_finance_report

    pages = [
        [{"rrd_id": 1, "srid": "s1", "supplier_oper_name": "Продажа"},
         {"rrd_id": 2, "srid": "s2", "supplier_oper_name": "Логистика"}],
        [{"rrd_id": 3, "srid": "s3", "supplier_oper_name": "Продажа"}],
        [],
    ]
    call_log = []

    class FakeResp:
        def __init__(self, data):
            self.status_code = 200
            self._data = data
        def json(self):
            return self._data

    def fake_get(url, params=None, headers=None, timeout=None):
        call_log.append(params.get("rrdid"))
        idx = len(call_log) - 1
        return FakeResp(pages[idx])

    with patch("app.services.wb_api.httpx.Client") as mock_client:
        ctx = mock_client.return_value.__enter__.return_value
        ctx.get.side_effect = fake_get
        rows = fetch_finance_report("fake_token", "2026-04-01", "2026-04-07")

    assert len(rows) == 3
    assert call_log == [0, 2, 3]   # 首页 0，下一页用上一页最后 rrd_id


def test_fetch_finance_report_handles_429():
    """遇 429 指数退避重试，最终成功。"""
    from app.services.wb_api import fetch_finance_report

    class FakeResp:
        def __init__(self, status, data=None):
            self.status_code = status
            self._data = data or []
        def json(self):
            return self._data

    responses = [FakeResp(429), FakeResp(200, [])]

    with patch("app.services.wb_api.httpx.Client") as mock_client, \
         patch("app.services.wb_api.time.sleep") as mock_sleep:
        ctx = mock_client.return_value.__enter__.return_value
        ctx.get.side_effect = responses
        rows = fetch_finance_report("fake_token", "2026-04-01", "2026-04-07")

    assert rows == []
    assert mock_sleep.called


def test_merge_rows_by_srid_combines_three_rows():
    """同一 Srid 的 销售行/物流行/退货行 合并成 1 条订单记录。"""
    from app.services.finance_sync import merge_rows_by_srid

    rows = [
        {
            "srid": "S1", "supplier_oper_name": "Продажа",
            "order_dt": "2026-04-08T10:00:00", "sale_dt": "2026-04-13T10:00:00",
            "nm_id": 507336942, "sa_name": "SKU-1",
            "subject_name": "其他", "brand_name": "", "ts_name": "0", "barcode": "BC1",
            "quantity": 1, "retail_price": 100.0, "retail_amount": 96.47,
            "commission_percent": 9.5, "ppvz_vw": 5.3, "ppvz_vw_nds": 1.16,
            "ppvz_for_pay": 90.01, "delivery_rub": 0,
            "office_name": "Маркетплейс", "site_country": "RU", "srv_dbs": "FBS",
            "penalty": 0, "storage_fee": 0, "deduction": 0,
            "rr_dt": "2026-04-14",
        },
        {
            "srid": "S1", "supplier_oper_name": "Логистика",
            "order_dt": "2026-04-08T10:00:00", "sale_dt": "2026-04-13T10:00:00",
            "nm_id": 507336942, "sa_name": "SKU-1",
            "quantity": 0, "delivery_rub": 13.04, "ppvz_for_pay": 0,
            "penalty": 0, "storage_fee": 0, "deduction": 0,
            "rr_dt": "2026-04-14",
        },
        {
            "srid": "S1", "supplier_oper_name": "Возврат",
            "order_dt": "2026-04-08T10:00:00", "sale_dt": "2026-04-13T10:00:00",
            "quantity": 1, "retail_price": 100.0, "ppvz_for_pay": 0,
            "penalty": 0, "storage_fee": 0, "deduction": 0,
            "rr_dt": "2026-04-14",
        },
    ]
    merged = merge_rows_by_srid(rows, shop_id=1, currency="CNY",
                                period_start=None, period_end=None)
    assert len(merged) == 1
    rec = merged[0]
    assert rec["srid"] == "S1"
    assert rec["shop_id"] == 1
    assert rec["currency"] == "CNY"
    assert rec["quantity"] == 1
    assert rec["sold_price"] == 96.47
    assert rec["net_to_seller"] == 90.01
    assert rec["delivery_fee"] == 13.04
    assert rec["commission_amount"] == 5.3 + 1.16
    assert rec["has_return_row"] is True
    assert rec["return_quantity"] == 1


def test_merge_accumulates_fees_across_rows():
    """多行费用（多条物流、罚款）累加。"""
    from app.services.finance_sync import merge_rows_by_srid

    rows = [
        {"srid": "S2", "supplier_oper_name": "Продажа", "ppvz_for_pay": 50, "quantity": 1,
         "penalty": 0, "storage_fee": 0, "deduction": 0, "delivery_rub": 0, "sale_dt": "2026-04-13"},
        {"srid": "S2", "supplier_oper_name": "Логистика", "delivery_rub": 10,
         "penalty": 0, "storage_fee": 0, "deduction": 0, "ppvz_for_pay": 0, "quantity": 0, "sale_dt": "2026-04-13"},
        {"srid": "S2", "supplier_oper_name": "Логистика", "delivery_rub": 5,
         "penalty": 0, "storage_fee": 0, "deduction": 0, "ppvz_for_pay": 0, "quantity": 0, "sale_dt": "2026-04-13"},
        {"srid": "S2", "supplier_oper_name": "Штраф", "penalty": 20,
         "storage_fee": 0, "deduction": 0, "delivery_rub": 0, "ppvz_for_pay": 0, "quantity": 0, "sale_dt": "2026-04-13"},
    ]
    merged = merge_rows_by_srid(rows, shop_id=1, currency="RUB",
                                period_start=None, period_end=None)
    assert len(merged) == 1
    assert merged[0]["delivery_fee"] == 15
    assert merged[0]["fine"] == 20


def test_extract_other_fees_filters_no_srid():
    """没有 srid 的行进入 other_fees，有 srid 的行忽略。"""
    from app.services.finance_sync import extract_other_fees
    from datetime import date

    rows = [
        {"srid": "S1", "supplier_oper_name": "Продажа", "ppvz_for_pay": 50, "sale_dt": "2026-04-13"},
        {"srid": "", "supplier_oper_name": "Хранение", "storage_fee": 150.0,
         "delivery_rub": 0, "penalty": 0, "deduction": 0, "ppvz_for_pay": 0,
         "sale_dt": "2026-04-13", "rr_dt": "2026-04-14"},
        {"srid": None, "supplier_oper_name": "Штраф", "penalty": 500.0,
         "delivery_rub": 0, "storage_fee": 0, "deduction": 0, "ppvz_for_pay": 0,
         "sale_dt": "2026-04-13"},
    ]
    fees = extract_other_fees(rows, shop_id=2, currency="RUB",
                              period_start=date(2026, 4, 6), period_end=date(2026, 4, 12))
    assert len(fees) == 2
    storage = next(f for f in fees if f["fee_type"] == "storage")
    assert storage["amount"] == 150.0
    assert storage["currency"] == "RUB"
    assert storage["raw_row"]["supplier_oper_name"] == "Хранение"
    fine = next(f for f in fees if f["fee_type"] == "fine")
    assert fine["amount"] == 500.0


def test_extract_other_fees_amount_picks_first_nonzero():
    """amount 从多个候选字段里选非零的第一个。"""
    from app.services.finance_sync import extract_other_fees

    rows = [
        {"srid": "", "supplier_oper_name": "Удержания", "deduction": 33,
         "penalty": 0, "storage_fee": 0, "delivery_rub": 0, "ppvz_for_pay": 0, "sale_dt": "2026-04-10"},
    ]
    fees = extract_other_fees(rows, shop_id=1, currency="CNY", period_start=None, period_end=None)
    assert fees[0]["fee_type"] == "deduction"
    assert fees[0]["amount"] == 33
