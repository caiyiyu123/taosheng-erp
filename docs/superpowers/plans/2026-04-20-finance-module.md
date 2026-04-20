# 财务统计模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 CYY-ERP 财务统计模块：从 WB 抓取每周详细报告，按 Srid 合并为每订单一行，分流订单行 / 其他费用行，支持汇总、明细、对账、手动 / 定时同步。

**Architecture:** 后端 3 张表（订单财务 / 其他费用 / 同步日志） + 1 个 service（合并 + 落库）+ 1 个 router（7 端点）+ Scheduler 周一定时任务。前端两个 Tab（跨境 CNY / 本土 RUB），每 Tab 内 4 个 section。订单 ↔ 财报通过 `srid` 关联，不修改现有 Order 模型。

**Tech Stack:** FastAPI + SQLAlchemy 2.x + APScheduler + Vue 3 Composition + Element Plus + httpx

**Spec:** `docs/superpowers/specs/2026-04-20-finance-module-design.md`

---

## 文件总览

**新建：**
- `backend/app/models/finance.py`
- `backend/app/services/finance_sync.py`
- `backend/tests/test_finance_sync.py`
- `backend/tests/test_finance_endpoints.py`
- `frontend/src/components/finance/FinanceTabContent.vue`
- `frontend/src/components/finance/FinanceSummaryCards.vue`
- `frontend/src/components/finance/FinanceOrdersTable.vue`
- `frontend/src/components/finance/FinanceOtherFeesTable.vue`
- `frontend/src/components/finance/FinanceReconciliation.vue`
- `frontend/src/components/finance/FinanceSyncDialog.vue`

**修改：**
- `backend/app/models/__init__.py` — 导出新 model
- `backend/app/services/wb_api.py` — 加 `fetch_finance_report`
- `backend/app/services/scheduler.py` — 注册 weekly_finance_sync job
- `backend/app/routers/finance.py` — 重写为 7 端点
- `frontend/src/views/Finance.vue` — 重写为 Tab 外壳

---

## Task 1: Finance 数据模型

**Files:**
- Create: `backend/app/models/finance.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_finance_sync.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_finance_sync.py`:
```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```
cd backend && pytest tests/test_finance_sync.py -v
```
Expected: `ImportError: cannot import name 'FinanceOrderRecord' from 'app.models.finance'`

- [ ] **Step 3: 写 model**

`backend/app/models/finance.py`:
```python
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, Date, DateTime, Text, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class FinanceOrderRecord(Base):
    __tablename__ = "finance_order_records"
    __table_args__ = (
        UniqueConstraint("shop_id", "srid", name="uq_finance_shop_srid"),
        Index("ix_finance_shop_sale_date", "shop_id", "sale_date"),
        Index("ix_finance_shop_mapping", "shop_id", "has_sku_mapping"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"), index=True)
    srid: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(10))
    order_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    sale_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    nm_id: Mapped[str] = mapped_column(String(50), default="")
    shop_sku: Mapped[str] = mapped_column(String(200), default="")
    product_name: Mapped[str] = mapped_column(String(500), default="")
    barcode: Mapped[str] = mapped_column(String(100), default="")
    category: Mapped[str] = mapped_column(String(200), default="")
    size: Mapped[str] = mapped_column(String(50), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    return_quantity: Mapped[int] = mapped_column(Integer, default=0)
    retail_price: Mapped[float] = mapped_column(Float, default=0.0)
    sold_price: Mapped[float] = mapped_column(Float, default=0.0)
    commission_rate: Mapped[float] = mapped_column(Float, default=0.0)
    commission_amount: Mapped[float] = mapped_column(Float, default=0.0)
    net_to_seller: Mapped[float] = mapped_column(Float, default=0.0)
    delivery_fee: Mapped[float] = mapped_column(Float, default=0.0)
    fine: Mapped[float] = mapped_column(Float, default=0.0)
    storage_fee: Mapped[float] = mapped_column(Float, default=0.0)
    deduction: Mapped[float] = mapped_column(Float, default=0.0)
    purchase_cost: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    has_sku_mapping: Mapped[bool] = mapped_column(Boolean, default=False)
    warehouse: Mapped[str] = mapped_column(String(200), default="")
    country: Mapped[str] = mapped_column(String(10), default="")
    sale_type: Mapped[str] = mapped_column(String(50), default="")
    has_return_row: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class FinanceOtherFee(Base):
    __tablename__ = "finance_other_fees"
    __table_args__ = (
        Index("ix_other_fee_shop_date", "shop_id", "sale_date"),
        Index("ix_other_fee_shop_type", "shop_id", "fee_type"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"), index=True)
    currency: Mapped[str] = mapped_column(String(10))
    sale_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fee_type: Mapped[str] = mapped_column(String(50))
    fee_description: Mapped[str] = mapped_column(String(500), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    raw_row: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class FinanceSyncLog(Base):
    __tablename__ = "finance_sync_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("shops.id"), index=True)
    triggered_by: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="running")
    rows_fetched: Mapped[int] = mapped_column(Integer, default=0)
    orders_merged: Mapped[int] = mapped_column(Integer, default=0)
    other_fees_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 4: 注册 model 到 `__init__`**

Edit `backend/app/models/__init__.py`, 在末尾（imports 部分）加一行：
```python
from app.models.finance import FinanceOrderRecord, FinanceOtherFee, FinanceSyncLog
```
并在 `__all__` 列表里加 `"FinanceOrderRecord", "FinanceOtherFee", "FinanceSyncLog"`。

- [ ] **Step 5: 再跑测试**

```
cd backend && pytest tests/test_finance_sync.py -v
```
Expected: 3 tests PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/models/finance.py backend/app/models/__init__.py backend/tests/test_finance_sync.py
git commit -m "feat(finance): 添加 finance 模块 3 个数据模型"
```

---

## Task 2: WB API `fetch_finance_report` 函数

**Files:**
- Modify: `backend/app/services/wb_api.py`
- Test: `backend/tests/test_finance_sync.py` (追加)

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_finance_sync.py` 顶部 import：
```python
from unittest.mock import patch, MagicMock
```
追加测试：
```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```
cd backend && pytest tests/test_finance_sync.py::test_fetch_finance_report_paginates tests/test_finance_sync.py::test_fetch_finance_report_handles_429 -v
```
Expected: `ImportError: cannot import name 'fetch_finance_report'`

- [ ] **Step 3: 实现**

在 `backend/app/services/wb_api.py` 末尾追加：
```python
STATISTICS_API_FINANCE_PATH = "/api/v5/supplier/reportDetailByPeriod"
_FINANCE_BACKOFF_INITIAL = 60   # seconds
_FINANCE_BACKOFF_MAX = 300
_FINANCE_MAX_RETRIES = 3


def fetch_finance_report(api_token: str, date_from: str, date_to: str) -> list[dict]:
    """GET /api/v5/supplier/reportDetailByPeriod — paginated by rrdid.

    Returns all rows in the given date range. Handles 429 with exponential backoff.

    Args:
        api_token: plaintext WB token
        date_from, date_to: "YYYY-MM-DD"
    """
    url = f"{STATISTICS_API}{STATISTICS_API_FINANCE_PATH}"
    rows: list[dict] = []
    rrdid = 0
    while True:
        _throttle()
        backoff = _FINANCE_BACKOFF_INITIAL
        retries = 0
        with httpx.Client(timeout=120) as client:
            while True:
                resp = client.get(
                    url,
                    params={"dateFrom": date_from, "dateTo": date_to, "rrdid": rrdid, "limit": 100000},
                    headers=_headers(api_token),
                    timeout=120,
                )
                if resp.status_code == 429 and retries < _FINANCE_MAX_RETRIES:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, _FINANCE_BACKOFF_MAX)
                    retries += 1
                    continue
                break
        if resp.status_code != 200:
            raise RuntimeError(f"WB finance report failed: {resp.status_code} {resp.text[:200]}")
        page = resp.json() or []
        if not page:
            break
        rows.extend(page)
        rrdid = page[-1].get("rrd_id", 0)
        if not rrdid:
            break
    return rows
```

- [ ] **Step 4: 运行测试确认通过**

```
cd backend && pytest tests/test_finance_sync.py -v
```
Expected: 5 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/wb_api.py backend/tests/test_finance_sync.py
git commit -m "feat(finance): wb_api.fetch_finance_report 分页 + 429 退避"
```

---

## Task 3: Sync service — 按 Srid 合并行

**Files:**
- Create: `backend/app/services/finance_sync.py`
- Test: `backend/tests/test_finance_sync.py` (追加)

- [ ] **Step 1: 追加失败测试**

```python
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
```

- [ ] **Step 2: 运行确认失败**

```
cd backend && pytest tests/test_finance_sync.py::test_merge_rows_by_srid_combines_three_rows -v
```
Expected: `ModuleNotFoundError: No module named 'app.services.finance_sync'`

- [ ] **Step 3: 实现**

`backend/app/services/finance_sync.py` 首版：
```python
"""Finance module sync service — fetch WB reports, merge by srid, persist.

Layers:
- merge_rows_by_srid   : pure function, row list -> dict list (1 per srid)
- extract_other_fees   : pure function, row list -> dict list (1 per fee row)
- fill_purchase_cost_and_profit : (records, db, shop_id) -> None, mutates in place
- sync_shop            : end-to-end pipeline, calls WB API and persists
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Optional


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


SALE_OPS = {"Продажа"}
LOGISTICS_OPS = {"Логистика"}
RETURN_OPS = {"Возврат"}


def merge_rows_by_srid(
    rows: list[dict], *, shop_id: int, currency: str,
    period_start: Optional[date], period_end: Optional[date],
) -> list[dict]:
    """Merge rows sharing the same srid into one record per srid.

    Row semantics:
      - Sale row (Продажа): primary product info + net_to_seller
      - Logistics row (Логистика): delivery_fee accumulates
      - Return row (Возврат): has_return_row, return_quantity
      - Other (Штраф, Хранение, Удержание with srid): accumulate into fine/storage/deduction
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        srid = (r.get("srid") or "").strip()
        if srid:
            groups[srid].append(r)

    result: list[dict] = []
    for srid, group in groups.items():
        sale_row = next((r for r in group if r.get("supplier_oper_name") in SALE_OPS), group[0])
        delivery_fee = sum(_num(r.get("delivery_rub")) for r in group if r.get("supplier_oper_name") in LOGISTICS_OPS)
        fine = sum(_num(r.get("penalty")) for r in group)
        storage = sum(_num(r.get("storage_fee")) for r in group)
        deduction = sum(_num(r.get("deduction")) for r in group)
        returns = [r for r in group if r.get("supplier_oper_name") in RETURN_OPS]
        has_return = bool(returns)
        return_qty = sum(_int(r.get("quantity")) for r in returns)

        # net_to_seller: sales + return negatives (if any)
        net_to_seller = sum(_num(r.get("ppvz_for_pay")) for r in group)

        rec = {
            "shop_id": shop_id,
            "srid": srid,
            "currency": currency,
            "order_date": _parse_date(sale_row.get("order_dt")),
            "sale_date": _parse_date(sale_row.get("sale_dt") or sale_row.get("rr_dt")),
            "report_period_start": period_start,
            "report_period_end": period_end,
            "nm_id": str(sale_row.get("nm_id") or ""),
            "shop_sku": sale_row.get("sa_name") or "",
            "product_name": sale_row.get("sa_name") and "" or "",  # overridden below
            "barcode": sale_row.get("barcode") or "",
            "category": sale_row.get("subject_name") or "",
            "size": sale_row.get("ts_name") or "",
            "quantity": _int(sale_row.get("quantity")),
            "return_quantity": return_qty,
            "retail_price": _num(sale_row.get("retail_price")),
            "sold_price": _num(sale_row.get("retail_amount")),
            "commission_rate": _num(sale_row.get("commission_percent")),
            "commission_amount": _num(sale_row.get("ppvz_vw")) + _num(sale_row.get("ppvz_vw_nds")),
            "net_to_seller": net_to_seller,
            "delivery_fee": delivery_fee,
            "fine": fine,
            "storage_fee": storage,
            "deduction": deduction,
            "purchase_cost": 0.0,
            "net_profit": 0.0,
            "has_sku_mapping": False,
            "warehouse": sale_row.get("office_name") or "",
            "country": sale_row.get("site_country") or "",
            "sale_type": sale_row.get("srv_dbs") or "",
            "has_return_row": has_return,
        }
        # product_name: WB 财报没有单独字段，用 subject_name + sa_name fallback
        rec["product_name"] = sale_row.get("brand_name") or sale_row.get("subject_name") or ""
        result.append(rec)
    return result
```

- [ ] **Step 4: 运行确认通过**

```
cd backend && pytest tests/test_finance_sync.py -v
```
Expected: 7 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/finance_sync.py backend/tests/test_finance_sync.py
git commit -m "feat(finance): merge_rows_by_srid 按订单合并销售/物流/退货行"
```

---

## Task 4: 非订单费用提取

**Files:**
- Modify: `backend/app/services/finance_sync.py`
- Test: `backend/tests/test_finance_sync.py` (追加)

- [ ] **Step 1: 追加失败测试**

```python
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
```

- [ ] **Step 2: 确认失败**

```
cd backend && pytest tests/test_finance_sync.py::test_extract_other_fees_filters_no_srid -v
```
Expected: `ImportError: cannot import name 'extract_other_fees'`

- [ ] **Step 3: 实现 extract_other_fees**

在 `backend/app/services/finance_sync.py` 追加：
```python
FEE_TYPE_MAP = {
    "Хранение": "storage",
    "Штраф": "fine",
    "Удержания": "deduction",
    "Удержание": "deduction",
    "Логистика": "logistics_adjust",
}


def _infer_fee_type(row: dict) -> str:
    op = row.get("supplier_oper_name") or ""
    for key, val in FEE_TYPE_MAP.items():
        if key in op:
            return val
    return "other"


def _fee_amount(row: dict) -> float:
    for field in ("penalty", "storage_fee", "deduction", "delivery_rub", "ppvz_for_pay"):
        v = _num(row.get(field))
        if v:
            return v
    return 0.0


def extract_other_fees(
    rows: list[dict], *, shop_id: int, currency: str,
    period_start: Optional[date], period_end: Optional[date],
) -> list[dict]:
    """Rows without srid → standalone fee records (one per row)."""
    result: list[dict] = []
    for r in rows:
        srid = (r.get("srid") or "").strip() if r.get("srid") else ""
        if srid:
            continue
        result.append({
            "shop_id": shop_id,
            "currency": currency,
            "sale_date": _parse_date(r.get("sale_dt") or r.get("rr_dt")),
            "report_period_start": period_start,
            "report_period_end": period_end,
            "fee_type": _infer_fee_type(r),
            "fee_description": r.get("supplier_oper_name") or "",
            "amount": _fee_amount(r),
            "raw_row": r,
        })
    return result
```

- [ ] **Step 4: 运行确认通过**

```
cd backend && pytest tests/test_finance_sync.py -v
```
Expected: 9 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/finance_sync.py backend/tests/test_finance_sync.py
git commit -m "feat(finance): extract_other_fees 分流非订单费用"
```

---

## Task 5: 采购成本 + 利润填充

**Files:**
- Modify: `backend/app/services/finance_sync.py`
- Test: `backend/tests/test_finance_sync.py` (追加)

- [ ] **Step 1: 追加失败测试**

```python
def test_fill_purchase_cost_with_mapping(db):
    """有 SKU 映射 → purchase_cost = purchase_price × quantity, has_sku_mapping=True。"""
    from app.models.shop import Shop
    from app.models.product import Product, SkuMapping
    from app.utils.security import encrypt_token
    from app.services.finance_sync import fill_purchase_cost_and_profit

    shop = Shop(name="S", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add(shop); db.commit()
    product = Product(sku="P1", name="鞋子", purchase_price=30.0)
    db.add(product); db.commit()
    mapping = SkuMapping(shop_id=shop.id, shop_sku="SKU-1", product_id=product.id)
    db.add(mapping); db.commit()

    records = [{
        "shop_id": shop.id, "shop_sku": "SKU-1", "quantity": 2,
        "net_to_seller": 200.0, "delivery_fee": 20.0,
        "fine": 0.0, "storage_fee": 0.0, "deduction": 0.0,
        "purchase_cost": 0.0, "net_profit": 0.0, "has_sku_mapping": False,
    }]
    fill_purchase_cost_and_profit(records, db, shop_id=shop.id)

    assert records[0]["purchase_cost"] == 60.0
    assert records[0]["has_sku_mapping"] is True
    assert records[0]["net_profit"] == 200.0 - 20.0 - 60.0  # 120.0


def test_fill_purchase_cost_without_mapping(db):
    """无映射 → purchase_cost=0, has_sku_mapping=False, 利润按 0 采购成本算。"""
    from app.models.shop import Shop
    from app.utils.security import encrypt_token
    from app.services.finance_sync import fill_purchase_cost_and_profit

    shop = Shop(name="S", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add(shop); db.commit()
    records = [{
        "shop_id": shop.id, "shop_sku": "UNMAPPED", "quantity": 1,
        "net_to_seller": 100.0, "delivery_fee": 10.0,
        "fine": 0.0, "storage_fee": 0.0, "deduction": 0.0,
        "purchase_cost": 0.0, "net_profit": 0.0, "has_sku_mapping": False,
    }]
    fill_purchase_cost_and_profit(records, db, shop_id=shop.id)
    assert records[0]["purchase_cost"] == 0
    assert records[0]["has_sku_mapping"] is False
    assert records[0]["net_profit"] == 90.0


def test_fill_purchase_cost_mapping_without_product(db):
    """映射存在但 product_id 为 NULL → 视作无映射。"""
    from app.models.shop import Shop
    from app.models.product import SkuMapping
    from app.utils.security import encrypt_token
    from app.services.finance_sync import fill_purchase_cost_and_profit

    shop = Shop(name="S", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add(shop); db.commit()
    mapping = SkuMapping(shop_id=shop.id, shop_sku="UM", product_id=None)
    db.add(mapping); db.commit()

    records = [{
        "shop_id": shop.id, "shop_sku": "UM", "quantity": 1,
        "net_to_seller": 50.0, "delivery_fee": 5.0,
        "fine": 0.0, "storage_fee": 0.0, "deduction": 0.0,
        "purchase_cost": 0.0, "net_profit": 0.0, "has_sku_mapping": False,
    }]
    fill_purchase_cost_and_profit(records, db, shop_id=shop.id)
    assert records[0]["purchase_cost"] == 0
    assert records[0]["has_sku_mapping"] is False
```

- [ ] **Step 2: 确认失败**

```
cd backend && pytest tests/test_finance_sync.py::test_fill_purchase_cost_with_mapping -v
```
Expected: `ImportError: cannot import name 'fill_purchase_cost_and_profit'`

- [ ] **Step 3: 实现**

在 `backend/app/services/finance_sync.py` 追加：
```python
def fill_purchase_cost_and_profit(records: list[dict], db, shop_id: int) -> None:
    """Mutate records in place: set purchase_cost, has_sku_mapping, net_profit.

    Lookup via SkuMapping(shop_id, shop_sku) -> Product.purchase_price.
    Missing mapping or NULL product_id → purchase_cost=0, has_sku_mapping=False.
    """
    from app.models.product import SkuMapping, Product

    skus = {r["shop_sku"] for r in records if r.get("shop_sku")}
    if skus:
        rows = (
            db.query(SkuMapping.shop_sku, Product.purchase_price)
            .outerjoin(Product, Product.id == SkuMapping.product_id)
            .filter(SkuMapping.shop_id == shop_id, SkuMapping.shop_sku.in_(skus))
            .all()
        )
        price_map = {sku: (price or 0) for sku, price in rows if price is not None}
    else:
        price_map = {}

    for r in records:
        sku = r.get("shop_sku") or ""
        qty = r.get("quantity", 0)
        price = price_map.get(sku)
        if price is not None and price > 0:
            r["purchase_cost"] = price * qty
            r["has_sku_mapping"] = True
        else:
            r["purchase_cost"] = 0.0
            r["has_sku_mapping"] = False
        r["net_profit"] = (
            r.get("net_to_seller", 0)
            - r.get("delivery_fee", 0)
            - r.get("fine", 0)
            - r.get("storage_fee", 0)
            - r.get("deduction", 0)
            - r["purchase_cost"]
        )
```

- [ ] **Step 4: 运行确认通过**

```
cd backend && pytest tests/test_finance_sync.py -v
```
Expected: 12 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/finance_sync.py backend/tests/test_finance_sync.py
git commit -m "feat(finance): fill_purchase_cost_and_profit 填充采购成本和净利润"
```

---

## Task 6: `sync_shop` 端到端 pipeline

**Files:**
- Modify: `backend/app/services/finance_sync.py`
- Test: `backend/tests/test_finance_sync.py` (追加)

- [ ] **Step 1: 追加失败测试**

```python
def test_sync_shop_end_to_end(db, monkeypatch):
    """完整链路：mock WB API → 合并 → 存库 → 返回 sync_log。"""
    from datetime import date
    from app.models.shop import Shop
    from app.models.product import Product, SkuMapping
    from app.models.finance import FinanceOrderRecord, FinanceOtherFee, FinanceSyncLog
    from app.utils.security import encrypt_token
    from app.services import finance_sync

    shop = Shop(name="S", type="local", api_token=encrypt_token("tok"), is_active=True)
    db.add(shop); db.commit()
    product = Product(sku="P1", purchase_price=10.0)
    db.add(product); db.commit()
    db.add(SkuMapping(shop_id=shop.id, shop_sku="SKU-A", product_id=product.id)); db.commit()

    fake_rows = [
        {"srid": "X1", "supplier_oper_name": "Продажа",
         "order_dt": "2026-04-08", "sale_dt": "2026-04-13",
         "nm_id": 1, "sa_name": "SKU-A", "quantity": 2,
         "retail_price": 100, "retail_amount": 95, "commission_percent": 10,
         "ppvz_vw": 5, "ppvz_vw_nds": 1, "ppvz_for_pay": 89,
         "delivery_rub": 0, "penalty": 0, "storage_fee": 0, "deduction": 0},
        {"srid": "X1", "supplier_oper_name": "Логистика",
         "sale_dt": "2026-04-13", "delivery_rub": 12,
         "ppvz_for_pay": 0, "penalty": 0, "storage_fee": 0, "deduction": 0, "quantity": 0},
        {"srid": "", "supplier_oper_name": "Хранение", "sale_dt": "2026-04-10",
         "storage_fee": 200, "ppvz_for_pay": 0, "delivery_rub": 0, "penalty": 0, "deduction": 0},
    ]
    monkeypatch.setattr(finance_sync, "fetch_finance_report", lambda token, df, dt: fake_rows)

    log = finance_sync.sync_shop(
        db, shop,
        date_from=date(2026, 4, 6), date_to=date(2026, 4, 12),
        triggered_by="manual", user_id=None,
    )

    db.refresh(log)
    assert log.status == "success"
    assert log.rows_fetched == 3
    assert log.orders_merged == 1
    assert log.other_fees_count == 1

    orders = db.query(FinanceOrderRecord).filter_by(shop_id=shop.id).all()
    assert len(orders) == 1
    o = orders[0]
    assert o.srid == "X1"
    assert o.currency == "RUB"
    assert o.delivery_fee == 12
    assert o.purchase_cost == 20.0      # 10 × 2
    assert o.has_sku_mapping is True
    # 89 - 12 - 20 = 57
    assert abs(o.net_profit - 57.0) < 0.01

    fees = db.query(FinanceOtherFee).filter_by(shop_id=shop.id).all()
    assert len(fees) == 1
    assert fees[0].fee_type == "storage"
    assert fees[0].amount == 200


def test_sync_shop_idempotent(db, monkeypatch):
    """同区间重拉两次 → 记录数不变（delete-then-insert）。"""
    from datetime import date
    from app.models.shop import Shop
    from app.models.finance import FinanceOrderRecord
    from app.utils.security import encrypt_token
    from app.services import finance_sync

    shop = Shop(name="S", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add(shop); db.commit()
    rows = [{
        "srid": "Y1", "supplier_oper_name": "Продажа", "sale_dt": "2026-04-13",
        "ppvz_for_pay": 50, "quantity": 1, "delivery_rub": 0,
        "penalty": 0, "storage_fee": 0, "deduction": 0,
    }]
    monkeypatch.setattr(finance_sync, "fetch_finance_report", lambda *a, **kw: rows)

    finance_sync.sync_shop(db, shop, date_from=date(2026, 4, 6), date_to=date(2026, 4, 12),
                           triggered_by="cron", user_id=None)
    finance_sync.sync_shop(db, shop, date_from=date(2026, 4, 6), date_to=date(2026, 4, 12),
                           triggered_by="cron", user_id=None)
    assert db.query(FinanceOrderRecord).count() == 1


def test_sync_shop_cross_border_currency_cny(db, monkeypatch):
    from datetime import date
    from app.models.shop import Shop
    from app.models.finance import FinanceOrderRecord
    from app.utils.security import encrypt_token
    from app.services import finance_sync

    shop = Shop(name="CB", type="cross_border", api_token=encrypt_token("t"), is_active=True)
    db.add(shop); db.commit()
    rows = [{"srid": "Z1", "supplier_oper_name": "Продажа", "sale_dt": "2026-04-13",
             "ppvz_for_pay": 90, "quantity": 1, "delivery_rub": 0,
             "penalty": 0, "storage_fee": 0, "deduction": 0}]
    monkeypatch.setattr(finance_sync, "fetch_finance_report", lambda *a, **kw: rows)
    finance_sync.sync_shop(db, shop, date_from=date(2026, 4, 6), date_to=date(2026, 4, 12),
                           triggered_by="cron", user_id=None)
    rec = db.query(FinanceOrderRecord).first()
    assert rec.currency == "CNY"
```

- [ ] **Step 2: 确认失败**

```
cd backend && pytest tests/test_finance_sync.py::test_sync_shop_end_to_end -v
```
Expected: `AttributeError: module 'app.services.finance_sync' has no attribute 'sync_shop'`

- [ ] **Step 3: 实现 sync_shop**

在 `backend/app/services/finance_sync.py` 文件顶部的 import 区追加：
```python
from app.services.wb_api import fetch_finance_report
from app.utils.security import decrypt_token
```
在文件末尾追加：
```python
def sync_shop(db, shop, *, date_from: date, date_to: date,
              triggered_by: str, user_id: Optional[int]) -> "FinanceSyncLog":
    """Full pipeline for one shop. Returns the FinanceSyncLog row (detached)."""
    from app.models.finance import FinanceOrderRecord, FinanceOtherFee, FinanceSyncLog

    log = FinanceSyncLog(
        shop_id=shop.id, triggered_by=triggered_by, user_id=user_id,
        date_from=date_from, date_to=date_to, status="running",
    )
    db.add(log); db.commit()

    try:
        token = decrypt_token(shop.api_token)
        rows = fetch_finance_report(
            token, date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d")
        )
        currency = "CNY" if shop.type == "cross_border" else "RUB"

        merged = merge_rows_by_srid(
            rows, shop_id=shop.id, currency=currency,
            period_start=date_from, period_end=date_to,
        )
        fill_purchase_cost_and_profit(merged, db, shop_id=shop.id)

        other_fees = extract_other_fees(
            rows, shop_id=shop.id, currency=currency,
            period_start=date_from, period_end=date_to,
        )

        # Idempotent: delete existing rows within the date window
        db.query(FinanceOrderRecord).filter(
            FinanceOrderRecord.shop_id == shop.id,
            FinanceOrderRecord.sale_date >= date_from,
            FinanceOrderRecord.sale_date <= date_to,
        ).delete(synchronize_session=False)
        db.query(FinanceOtherFee).filter(
            FinanceOtherFee.shop_id == shop.id,
            FinanceOtherFee.sale_date >= date_from,
            FinanceOtherFee.sale_date <= date_to,
        ).delete(synchronize_session=False)

        for rec in merged:
            db.add(FinanceOrderRecord(**rec))
        for fee in other_fees:
            db.add(FinanceOtherFee(**fee))

        log.status = "success"
        log.rows_fetched = len(rows)
        log.orders_merged = len(merged)
        log.other_fees_count = len(other_fees)
        log.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        db.rollback()
        log.status = "failed"
        log.error_message = str(e)[:2000]
        log.finished_at = datetime.now(timezone.utc)
        db.commit()
    return log
```

- [ ] **Step 4: 运行确认通过**

```
cd backend && pytest tests/test_finance_sync.py -v
```
Expected: 15 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/finance_sync.py backend/tests/test_finance_sync.py
git commit -m "feat(finance): sync_shop 端到端同步 pipeline（幂等）"
```

---

## Task 7: Router — 读接口（summary + orders + other-fees + reconciliation）

**Files:**
- Modify: `backend/app/routers/finance.py`
- Test: `backend/tests/test_finance_endpoints.py` (新建)

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_finance_endpoints.py`:
```python
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
```

- [ ] **Step 2: 运行确认失败**

```
cd backend && pytest tests/test_finance_endpoints.py::test_summary_returns_aggregates -v
```
Expected: 404 / AttributeError

- [ ] **Step 3: 实现读接口**

完全重写 `backend/app/routers/finance.py`:
```python
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.shop import Shop
from app.models.order import Order
from app.models.finance import FinanceOrderRecord, FinanceOtherFee, FinanceSyncLog
from app.utils.deps import get_accessible_shop_ids, require_module

router = APIRouter(prefix="/api/finance", tags=["finance"])


def _currency_for(shop_type: str) -> str:
    return "CNY" if shop_type == "cross_border" else "RUB"


def _shop_ids_filter(db: Session, shop_type: str, shop_id: Optional[int],
                     accessible_shops: Optional[list[int]]) -> list[int]:
    q = db.query(Shop.id).filter(Shop.type == shop_type)
    if shop_id:
        q = q.filter(Shop.id == shop_id)
    if accessible_shops is not None:
        q = q.filter(Shop.id.in_(accessible_shops))
    return [row[0] for row in q.all()]


@router.get("/summary")
def finance_summary(
    shop_type: str = Query(...),
    shop_id: Optional[int] = Query(None),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
    accessible_shops: Optional[list[int]] = Depends(get_accessible_shop_ids),
    _=Depends(require_module("finance")),
):
    currency = _currency_for(shop_type)
    sids = _shop_ids_filter(db, shop_type, shop_id, accessible_shops)
    if not sids:
        return {
            "currency": currency, "order_count": 0,
            "total_net_to_seller": 0, "total_commission": 0,
            "total_delivery_fee": 0, "total_fine": 0,
            "total_storage": 0, "total_deduction": 0,
            "total_purchase_cost": 0, "total_net_profit": 0,
            "total_other_fees": 0, "final_profit": 0,
            "missing_mapping_count": 0,
        }

    base = db.query(FinanceOrderRecord).filter(
        FinanceOrderRecord.shop_id.in_(sids),
        FinanceOrderRecord.sale_date.between(date_from, date_to),
    )
    agg = base.with_entities(
        func.count(FinanceOrderRecord.id),
        func.coalesce(func.sum(FinanceOrderRecord.net_to_seller), 0),
        func.coalesce(func.sum(FinanceOrderRecord.commission_amount), 0),
        func.coalesce(func.sum(FinanceOrderRecord.delivery_fee), 0),
        func.coalesce(func.sum(FinanceOrderRecord.fine), 0),
        func.coalesce(func.sum(FinanceOrderRecord.storage_fee), 0),
        func.coalesce(func.sum(FinanceOrderRecord.deduction), 0),
        func.coalesce(func.sum(FinanceOrderRecord.purchase_cost), 0),
        func.coalesce(func.sum(FinanceOrderRecord.net_profit), 0),
    ).one()
    (order_count, net_to_seller, commission, delivery, fine, storage,
     deduction, purchase_cost, net_profit) = agg

    missing = base.filter(FinanceOrderRecord.has_sku_mapping == False).count()

    other_total = db.query(func.coalesce(func.sum(FinanceOtherFee.amount), 0)).filter(
        FinanceOtherFee.shop_id.in_(sids),
        FinanceOtherFee.sale_date.between(date_from, date_to),
    ).scalar() or 0

    return {
        "currency": currency,
        "order_count": int(order_count),
        "total_net_to_seller": float(net_to_seller),
        "total_commission": float(commission),
        "total_delivery_fee": float(delivery),
        "total_fine": float(fine),
        "total_storage": float(storage),
        "total_deduction": float(deduction),
        "total_purchase_cost": float(purchase_cost),
        "total_net_profit": float(net_profit),
        "total_other_fees": float(other_total),
        "final_profit": float(net_profit) - float(other_total),
        "missing_mapping_count": int(missing),
    }


@router.get("/orders")
def finance_orders(
    shop_type: str = Query(...),
    shop_id: Optional[int] = Query(None),
    date_from: date = Query(...),
    date_to: date = Query(...),
    has_return: Optional[bool] = Query(None),
    has_mapping: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = Query("-sale_date"),
    db: Session = Depends(get_db),
    accessible_shops: Optional[list[int]] = Depends(get_accessible_shop_ids),
    _=Depends(require_module("finance")),
):
    sids = _shop_ids_filter(db, shop_type, shop_id, accessible_shops)
    if not sids:
        return {"items": [], "total": 0}
    q = db.query(FinanceOrderRecord).filter(
        FinanceOrderRecord.shop_id.in_(sids),
        FinanceOrderRecord.sale_date.between(date_from, date_to),
    )
    if has_return is not None:
        q = q.filter(FinanceOrderRecord.has_return_row == has_return)
    if has_mapping is not None:
        q = q.filter(FinanceOrderRecord.has_sku_mapping == has_mapping)

    total = q.count()
    sort_col = sort.lstrip("-+")
    order_col = getattr(FinanceOrderRecord, sort_col, FinanceOrderRecord.sale_date)
    if sort.startswith("-"):
        order_col = order_col.desc()
    q = q.order_by(order_col).offset((page - 1) * page_size).limit(page_size)

    # Shop name lookup
    shops = {s.id: s.name for s in db.query(Shop).filter(Shop.id.in_(sids)).all()}
    items = []
    for r in q.all():
        items.append({
            "id": r.id, "srid": r.srid,
            "shop_id": r.shop_id, "shop_name": shops.get(r.shop_id, ""),
            "sale_date": r.sale_date.isoformat() if r.sale_date else None,
            "order_date": r.order_date.isoformat() if r.order_date else None,
            "nm_id": r.nm_id, "shop_sku": r.shop_sku,
            "product_name": r.product_name,
            "quantity": r.quantity, "return_quantity": r.return_quantity,
            "retail_price": r.retail_price, "sold_price": r.sold_price,
            "net_to_seller": r.net_to_seller,
            "commission_rate": r.commission_rate,
            "commission_amount": r.commission_amount,
            "delivery_fee": r.delivery_fee,
            "fine": r.fine, "storage_fee": r.storage_fee, "deduction": r.deduction,
            "purchase_cost": r.purchase_cost, "net_profit": r.net_profit,
            "has_sku_mapping": r.has_sku_mapping, "has_return_row": r.has_return_row,
            "warehouse": r.warehouse, "country": r.country, "sale_type": r.sale_type,
            "barcode": r.barcode, "category": r.category, "size": r.size,
            "currency": r.currency,
        })
    return {"items": items, "total": total}


@router.get("/other-fees")
def finance_other_fees(
    shop_type: str = Query(...),
    shop_id: Optional[int] = Query(None),
    date_from: date = Query(...),
    date_to: date = Query(...),
    fee_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    accessible_shops: Optional[list[int]] = Depends(get_accessible_shop_ids),
    _=Depends(require_module("finance")),
):
    sids = _shop_ids_filter(db, shop_type, shop_id, accessible_shops)
    if not sids:
        return {"items": [], "total": 0}
    q = db.query(FinanceOtherFee).filter(
        FinanceOtherFee.shop_id.in_(sids),
        FinanceOtherFee.sale_date.between(date_from, date_to),
    )
    if fee_type:
        q = q.filter(FinanceOtherFee.fee_type == fee_type)
    total = q.count()
    items = []
    for f in q.order_by(FinanceOtherFee.sale_date.desc()).all():
        items.append({
            "id": f.id, "shop_id": f.shop_id, "currency": f.currency,
            "sale_date": f.sale_date.isoformat() if f.sale_date else None,
            "fee_type": f.fee_type, "fee_description": f.fee_description,
            "amount": f.amount,
        })
    return {"items": items, "total": total}


@router.get("/reconciliation")
def finance_reconciliation(
    shop_type: str = Query(...),
    shop_id: Optional[int] = Query(None),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
    accessible_shops: Optional[list[int]] = Depends(get_accessible_shop_ids),
    _=Depends(require_module("finance")),
):
    sids = _shop_ids_filter(db, shop_type, shop_id, accessible_shops)
    if not sids:
        return {"missing_in_orders": [], "missing_in_finance": []}

    shops = {s.id: s.name for s in db.query(Shop).filter(Shop.id.in_(sids)).all()}

    missing_in_orders_rows = (
        db.query(FinanceOrderRecord)
        .outerjoin(Order, and_(Order.srid == FinanceOrderRecord.srid,
                               Order.shop_id == FinanceOrderRecord.shop_id))
        .filter(
            Order.id.is_(None),
            FinanceOrderRecord.shop_id.in_(sids),
            FinanceOrderRecord.sale_date.between(date_from, date_to),
        ).all()
    )
    missing_in_orders = [
        {"srid": r.srid, "shop_name": shops.get(r.shop_id, ""),
         "sale_date": r.sale_date.isoformat() if r.sale_date else None,
         "net_to_seller": r.net_to_seller, "currency": r.currency}
        for r in missing_in_orders_rows
    ]

    missing_in_finance_rows = (
        db.query(Order)
        .outerjoin(FinanceOrderRecord, and_(
            FinanceOrderRecord.srid == Order.srid,
            FinanceOrderRecord.shop_id == Order.shop_id))
        .filter(
            FinanceOrderRecord.id.is_(None),
            Order.srid != "",
            Order.shop_id.in_(sids),
            Order.created_at.between(date_from, date_to),
        ).all()
    )
    missing_in_finance = [
        {"wb_order_id": o.wb_order_id, "srid": o.srid,
         "shop_name": shops.get(o.shop_id, ""),
         "created_at": o.created_at.isoformat() if o.created_at else None,
         "total_price": o.total_price}
        for o in missing_in_finance_rows
    ]

    return {"missing_in_orders": missing_in_orders, "missing_in_finance": missing_in_finance}
```

- [ ] **Step 4: 运行确认通过**

```
cd backend && pytest tests/test_finance_endpoints.py -v
```
Expected: 6 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/finance.py backend/tests/test_finance_endpoints.py
git commit -m "feat(finance): router 读接口 summary/orders/other-fees/reconciliation"
```

---

## Task 8: Router — 写接口（sync + sync-logs + recalc-profit）

**Files:**
- Modify: `backend/app/routers/finance.py`
- Test: `backend/tests/test_finance_endpoints.py` (追加)

- [ ] **Step 1: 追加失败测试**

```python
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
```

- [ ] **Step 2: 确认失败**

```
cd backend && pytest tests/test_finance_endpoints.py::test_sync_endpoint_creates_log -v
```
Expected: 404 (endpoint not found)

- [ ] **Step 3: 实现写接口**

在 `backend/app/routers/finance.py` 末尾追加：
```python
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from pydantic import BaseModel
from app.database import SessionLocal
from app.models.user import User
from app.services.finance_sync import sync_shop, fill_purchase_cost_and_profit
from app.utils.deps import get_current_user


_sync_pool = ThreadPoolExecutor(max_workers=2)


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def _sync_shop_blocking(db, shop, *, date_from, date_to, triggered_by, user_id):
    """Indirection so tests can monkeypatch without touching the service module."""
    return sync_shop(db, shop, date_from=date_from, date_to=date_to,
                     triggered_by=triggered_by, user_id=user_id)


def _sync_shop_in_background(shop_id: int, date_from: date, date_to: date, user_id: Optional[int]):
    db = SessionLocal()
    try:
        shop = db.query(Shop).get(shop_id)
        if not shop:
            return
        _sync_shop_blocking(db, shop, date_from=date_from, date_to=date_to,
                            triggered_by="manual", user_id=user_id)
    finally:
        db.close()


class SyncBody(BaseModel):
    shop_ids: list[int]
    date_from: date
    date_to: date


@router.post("/sync")
def finance_sync(
    body: SyncBody,
    db: Session = Depends(get_db),
    accessible_shops: Optional[list[int]] = Depends(get_accessible_shop_ids),
    user: User = Depends(_require_admin),
    _=Depends(require_module("finance")),
):
    if accessible_shops is not None:
        body.shop_ids = [s for s in body.shop_ids if s in accessible_shops]
    if not body.shop_ids:
        raise HTTPException(status_code=400, detail="No accessible shops selected")

    log_ids: list[int] = []
    for sid in body.shop_ids:
        log = FinanceSyncLog(
            shop_id=sid, triggered_by="manual", user_id=user.id,
            date_from=body.date_from, date_to=body.date_to, status="running",
        )
        db.add(log); db.commit()
        log_ids.append(log.id)
        _sync_pool.submit(_sync_shop_in_background, sid, body.date_from, body.date_to, user.id)

    return {"sync_log_ids": log_ids}


@router.get("/sync-logs")
def finance_sync_logs(
    ids: Optional[str] = Query(None, description="逗号分隔的 log id"),
    shop_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    accessible_shops: Optional[list[int]] = Depends(get_accessible_shop_ids),
    _=Depends(require_module("finance")),
):
    q = db.query(FinanceSyncLog)
    if accessible_shops is not None:
        q = q.filter(FinanceSyncLog.shop_id.in_(accessible_shops))
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        q = q.filter(FinanceSyncLog.id.in_(id_list))
    if shop_id:
        q = q.filter(FinanceSyncLog.shop_id == shop_id)
    q = q.order_by(FinanceSyncLog.started_at.desc()).limit(limit)

    shops = {s.id: s.name for s in db.query(Shop).all()}
    return [
        {
            "id": l.id, "shop_id": l.shop_id, "shop_name": shops.get(l.shop_id, ""),
            "triggered_by": l.triggered_by, "status": l.status,
            "date_from": l.date_from.isoformat(), "date_to": l.date_to.isoformat(),
            "rows_fetched": l.rows_fetched, "orders_merged": l.orders_merged,
            "other_fees_count": l.other_fees_count, "error_message": l.error_message,
            "started_at": l.started_at.isoformat() if l.started_at else None,
            "finished_at": l.finished_at.isoformat() if l.finished_at else None,
        }
        for l in q.all()
    ]


class RecalcBody(BaseModel):
    shop_id: int


@router.post("/recalc-profit")
def finance_recalc_profit(
    body: RecalcBody,
    db: Session = Depends(get_db),
    accessible_shops: Optional[list[int]] = Depends(get_accessible_shop_ids),
    _user: User = Depends(_require_admin),
    _=Depends(require_module("finance")),
):
    if accessible_shops is not None and body.shop_id not in accessible_shops:
        raise HTTPException(status_code=403, detail="No access to this shop")

    records = db.query(FinanceOrderRecord).filter(
        FinanceOrderRecord.shop_id == body.shop_id
    ).all()
    dicts = [
        {
            "shop_id": r.shop_id, "shop_sku": r.shop_sku, "quantity": r.quantity,
            "net_to_seller": r.net_to_seller, "delivery_fee": r.delivery_fee,
            "fine": r.fine, "storage_fee": r.storage_fee, "deduction": r.deduction,
            "purchase_cost": 0.0, "net_profit": 0.0, "has_sku_mapping": False,
            "_id": r.id,
        }
        for r in records
    ]
    fill_purchase_cost_and_profit(dicts, db, shop_id=body.shop_id)
    for d in dicts:
        rec = db.query(FinanceOrderRecord).get(d["_id"])
        rec.purchase_cost = d["purchase_cost"]
        rec.has_sku_mapping = d["has_sku_mapping"]
        rec.net_profit = d["net_profit"]
    db.commit()
    return {"updated": len(dicts)}
```

- [ ] **Step 4: 运行确认通过**

```
cd backend && pytest tests/test_finance_endpoints.py -v
```
Expected: 10 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/finance.py backend/tests/test_finance_endpoints.py
git commit -m "feat(finance): router 写接口 sync/sync-logs/recalc-profit + admin 限制"
```

---

## Task 9: Scheduler — 周一定时同步

**Files:**
- Modify: `backend/app/services/scheduler.py`
- Test: `backend/tests/test_finance_endpoints.py` (追加)

- [ ] **Step 1: 追加测试**

```python
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
```

- [ ] **Step 2: 运行确认失败**

```
cd backend && pytest tests/test_finance_endpoints.py::test_weekly_finance_sync_function_exists -v
```
Expected: `ImportError: cannot import name 'weekly_finance_sync'`

- [ ] **Step 3: 实现**

修改 `backend/app/services/scheduler.py`：

在文件顶部 imports 下方追加：
```python
from datetime import date, timedelta
```

在 `start_scheduler` 函数**之前**追加：
```python
def weekly_finance_sync():
    """Cron job: every Monday 03:00 Moscow, sync last week (Mon..Sun) for all active shops."""
    from app.services.finance_sync import sync_shop

    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)

    db = SessionLocal()
    try:
        shops = db.query(Shop).filter(Shop.is_active == True).all()
        for shop in shops:
            try:
                sync_shop(db, shop, date_from=last_monday, date_to=last_sunday,
                          triggered_by="cron", user_id=None)
                print(f"[Finance] Weekly sync done: {shop.name}")
            except Exception as e:
                print(f"[Finance] Weekly sync failed for {shop.name}: {e}")
    finally:
        db.close()
```

修改 `start_scheduler` 函数，在 `scheduler.start()` 之前加一行：
```python
    scheduler.add_job(
        weekly_finance_sync,
        "cron",
        day_of_week="mon",
        hour=3,
        minute=0,
        timezone="Europe/Moscow",
        id="weekly_finance_sync",
        replace_existing=True,
    )
```

- [ ] **Step 4: 运行确认通过**

```
cd backend && pytest tests/test_finance_endpoints.py -v
```
Expected: 12 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/scheduler.py backend/tests/test_finance_endpoints.py
git commit -m "feat(finance): scheduler 周一 03:00 Moscow 定时同步"
```

---

## Task 10: 前端 — Finance.vue 外壳 + FinanceTabContent.vue

**Files:**
- Modify: `frontend/src/views/Finance.vue`
- Create: `frontend/src/components/finance/FinanceTabContent.vue`

前端没有单元测试，"测试" 为本地浏览器手动验证。

- [ ] **Step 1: 重写 Finance.vue**

完全重写 `frontend/src/views/Finance.vue`:
```vue
<template>
  <div class="ts-finance">
    <div class="ts-finance-toolbar">
      <el-tabs v-model="activeTab" class="ts-finance-tabs">
        <el-tab-pane label="🌐 跨境店 (CNY)" name="cross_border" />
        <el-tab-pane label="🇷🇺 本土店 (RUB)" name="local" />
      </el-tabs>
      <el-button type="primary" :icon="Refresh" @click="syncDialogVisible = true">
        手动同步
      </el-button>
    </div>

    <FinanceTabContent v-if="activeTab === 'cross_border'" shop-type="cross_border" />
    <FinanceTabContent v-else shop-type="local" />

    <FinanceSyncDialog v-model="syncDialogVisible" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import FinanceTabContent from '../components/finance/FinanceTabContent.vue'
import FinanceSyncDialog from '../components/finance/FinanceSyncDialog.vue'

const activeTab = ref('cross_border')
const syncDialogVisible = ref(false)
</script>

<style scoped>
.ts-finance { padding: 16px; }
.ts-finance-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px;
}
.ts-finance-tabs { flex: 1; }
</style>
```

- [ ] **Step 2: 新建 FinanceTabContent.vue**

创建 `frontend/src/components/finance/FinanceTabContent.vue`:
```vue
<template>
  <div class="ts-tab">
    <div class="ts-filters">
      <el-select v-model="filters.shop_id" placeholder="全部店铺" clearable style="width: 200px">
        <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        :clearable="false"
        value-format="YYYY-MM-DD"
        style="width: 240px"
      />
      <div class="ts-date-shortcuts">
        <el-button size="small" @click="setRange('thisWeek')">本周</el-button>
        <el-button size="small" @click="setRange('lastWeek')">上周</el-button>
        <el-button size="small" @click="setRange('thisMonth')">本月</el-button>
        <el-button size="small" @click="setRange('last4weeks')">最近4周</el-button>
      </div>
    </div>

    <FinanceSummaryCards :summary="summary" :loading="loading.summary" />

    <div v-if="summary.missing_mapping_count > 0" class="ts-missing-banner">
      ⚠ {{ summary.missing_mapping_count }} 条订单采购成本缺失
      <el-link type="primary" @click="goToMappings">去 SKU 映射</el-link>
    </div>

    <el-divider content-position="left">📋 订单明细</el-divider>
    <FinanceOrdersTable
      :shop-type="shopType"
      :shop-id="filters.shop_id"
      :date-from="dateRange[0]"
      :date-to="dateRange[1]"
      :currency="summary.currency"
      @reload="reloadAll"
    />

    <el-divider content-position="left">💰 其他费用</el-divider>
    <FinanceOtherFeesTable
      :shop-type="shopType"
      :shop-id="filters.shop_id"
      :date-from="dateRange[0]"
      :date-to="dateRange[1]"
      :currency="summary.currency"
    />

    <el-divider content-position="left">🔎 对账</el-divider>
    <FinanceReconciliation
      :shop-type="shopType"
      :shop-id="filters.shop_id"
      :date-from="dateRange[0]"
      :date-to="dateRange[1]"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../../api'
import FinanceSummaryCards from './FinanceSummaryCards.vue'
import FinanceOrdersTable from './FinanceOrdersTable.vue'
import FinanceOtherFeesTable from './FinanceOtherFeesTable.vue'
import FinanceReconciliation from './FinanceReconciliation.vue'

const props = defineProps({
  shopType: { type: String, required: true },
})

const router = useRouter()
const shops = ref([])
const filters = reactive({ shop_id: null })
const dateRange = ref(getLast4WeeksRange())
const summary = ref({ currency: 'RUB', order_count: 0, total_net_to_seller: 0, total_commission: 0,
  total_delivery_fee: 0, total_fine: 0, total_storage: 0, total_deduction: 0,
  total_purchase_cost: 0, total_net_profit: 0, total_other_fees: 0, final_profit: 0,
  missing_mapping_count: 0 })
const loading = reactive({ summary: false })

function getLast4WeeksRange() {
  const end = new Date()
  const start = new Date(end.getTime() - 27 * 86400000)
  const fmt = d => d.toISOString().slice(0, 10)
  return [fmt(start), fmt(end)]
}

function setRange(key) {
  const today = new Date()
  const day = today.getDay() || 7
  const fmt = d => d.toISOString().slice(0, 10)
  if (key === 'thisWeek') {
    const monday = new Date(today.getTime() - (day - 1) * 86400000)
    dateRange.value = [fmt(monday), fmt(today)]
  } else if (key === 'lastWeek') {
    const lastMon = new Date(today.getTime() - (day + 6) * 86400000)
    const lastSun = new Date(today.getTime() - day * 86400000)
    dateRange.value = [fmt(lastMon), fmt(lastSun)]
  } else if (key === 'thisMonth') {
    const first = new Date(today.getFullYear(), today.getMonth(), 1)
    dateRange.value = [fmt(first), fmt(today)]
  } else {
    dateRange.value = getLast4WeeksRange()
  }
}

async function fetchShops() {
  try {
    const { data } = await api.get('/api/shops')
    shops.value = (data || []).filter(s => s.type === props.shopType)
  } catch (e) { console.warn('shops error', e) }
}

async function fetchSummary() {
  loading.summary = true
  try {
    const params = {
      shop_type: props.shopType,
      date_from: dateRange.value[0], date_to: dateRange.value[1],
    }
    if (filters.shop_id) params.shop_id = filters.shop_id
    const { data } = await api.get('/api/finance/summary', { params })
    summary.value = data
  } catch (e) { console.warn('summary error', e) }
  finally { loading.summary = false }
}

function reloadAll() {
  fetchSummary()
}

function goToMappings() {
  router.push({ path: '/sku-mappings', query: filters.shop_id ? { shop_id: filters.shop_id } : {} })
}

watch(() => props.shopType, () => {
  filters.shop_id = null
  fetchShops()
  fetchSummary()
})
watch([() => filters.shop_id, dateRange], fetchSummary, { deep: true })

onMounted(() => {
  fetchShops()
  fetchSummary()
})
</script>

<style scoped>
.ts-tab { padding: 8px 0; }
.ts-filters { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.ts-date-shortcuts { display: flex; gap: 6px; }
.ts-missing-banner {
  padding: 10px 14px; margin: 12px 0;
  background: #fffbea; border: 1px solid #fcd34d; border-radius: 6px;
  color: #92400e; font-size: 13px;
}
</style>
```

- [ ] **Step 3: 提交**（SyncDialog 组件后面的 Task 会创建，先建一个占位防止 import 报错）

创建占位 `frontend/src/components/finance/FinanceSyncDialog.vue`:
```vue
<template><div></div></template>
<script setup>defineProps(['modelValue'])</script>
```

占位 `FinanceSummaryCards.vue` / `FinanceOrdersTable.vue` / `FinanceOtherFeesTable.vue` / `FinanceReconciliation.vue` 同理放 stub 内容。

```bash
git add frontend/src/views/Finance.vue frontend/src/components/finance/
git commit -m "feat(finance): 前端 Finance.vue Tab 外壳 + FinanceTabContent"
```

---

## Task 11: 前端 — FinanceSummaryCards.vue

**Files:**
- Modify: `frontend/src/components/finance/FinanceSummaryCards.vue`

- [ ] **Step 1: 实现**

重写 `frontend/src/components/finance/FinanceSummaryCards.vue`:
```vue
<template>
  <el-row :gutter="12" v-loading="loading">
    <el-col :span="6"><el-card class="ts-card">
      <div class="ts-card-title">订单数</div>
      <div class="ts-card-val">{{ summary.order_count }}</div>
    </el-card></el-col>
    <el-col :span="6"><el-card class="ts-card">
      <div class="ts-card-title">应付卖家</div>
      <div class="ts-card-val">{{ fmt(summary.total_net_to_seller) }} {{ symbol }}</div>
    </el-card></el-col>
    <el-col :span="6"><el-card class="ts-card">
      <div class="ts-card-title">佣金</div>
      <div class="ts-card-val">{{ fmt(summary.total_commission) }} {{ symbol }}</div>
    </el-card></el-col>
    <el-col :span="6"><el-card class="ts-card">
      <div class="ts-card-title">配送费</div>
      <div class="ts-card-val">{{ fmt(summary.total_delivery_fee) }} {{ symbol }}</div>
    </el-card></el-col>

    <el-col :span="6" style="margin-top: 12px"><el-card class="ts-card">
      <div class="ts-card-title">采购成本</div>
      <div class="ts-card-val">{{ fmt(summary.total_purchase_cost) }} {{ symbol }}</div>
    </el-card></el-col>
    <el-col :span="6" style="margin-top: 12px"><el-card class="ts-card">
      <div class="ts-card-title">订单利润</div>
      <div class="ts-card-val" :style="{ color: summary.total_net_profit >= 0 ? '#16a34a' : '#dc2626' }">
        {{ fmt(summary.total_net_profit) }} {{ symbol }}
      </div>
    </el-card></el-col>
    <el-col :span="6" style="margin-top: 12px"><el-card class="ts-card">
      <div class="ts-card-title">非订单费用</div>
      <div class="ts-card-val">{{ fmt(summary.total_other_fees) }} {{ symbol }}</div>
    </el-card></el-col>
    <el-col :span="6" style="margin-top: 12px"><el-card class="ts-card">
      <div class="ts-card-title">最终利润</div>
      <div class="ts-card-val" :style="{ color: summary.final_profit >= 0 ? '#16a34a' : '#dc2626', fontWeight: 700 }">
        {{ fmt(summary.final_profit) }} {{ symbol }}
      </div>
    </el-card></el-col>
  </el-row>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  summary: { type: Object, required: true },
  loading: { type: Boolean, default: false },
})
const symbol = computed(() => props.summary.currency === 'CNY' ? '¥' : '₽')
function fmt(v) {
  if (v === null || v === undefined) return '0.00'
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.ts-card { text-align: center; }
.ts-card-title { font-size: 12px; color: #64748b; margin-bottom: 6px; }
.ts-card-val { font-size: 20px; font-weight: 600; color: #1e293b; }
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/finance/FinanceSummaryCards.vue
git commit -m "feat(finance): FinanceSummaryCards 8 张汇总卡片"
```

---

## Task 12: 前端 — FinanceOrdersTable.vue

**Files:**
- Modify: `frontend/src/components/finance/FinanceOrdersTable.vue`

- [ ] **Step 1: 实现**

重写 `frontend/src/components/finance/FinanceOrdersTable.vue`:
```vue
<template>
  <div class="ts-orders">
    <div class="ts-orders-toolbar">
      <el-checkbox v-model="onlyReturn" @change="refresh">仅退货</el-checkbox>
      <el-checkbox v-model="onlyUnmapped" @change="refresh">仅未映射</el-checkbox>
      <span class="ts-count">共 {{ total }} 条</span>
    </div>

    <el-table
      ref="tableRef"
      :data="items"
      stripe
      :fit="false"
      v-loading="loading"
      max-height="640"
      :row-class-name="rowClass"
      @expand-change="onExpand"
      @row-click="toggleExpand"
    >
      <el-table-column type="expand" width="40">
        <template #default="{ row }">
          <div class="ts-expand">
            <div><b>配货任务：</b>{{ row.srid }}</div>
            <div><b>条码：</b>{{ row.barcode }}</div>
            <div><b>品类：</b>{{ row.category }}</div>
            <div><b>尺码：</b>{{ row.size }}</div>
            <div><b>仓库：</b>{{ row.warehouse }}</div>
            <div><b>国家：</b>{{ row.country }}</div>
            <div><b>销售方式：</b>{{ row.sale_type }}</div>
            <div><b>佣金金额：</b>{{ fmt(row.commission_amount) }} {{ symbol }}</div>
            <div><b>退货数：</b>{{ row.return_quantity }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="sale_date" label="销售日期" width="100" />
      <el-table-column prop="shop_sku" label="SKU" width="130" show-overflow-tooltip />
      <el-table-column label="产品名" width="300">
        <template #default="{ row }">
          <div class="ts-name-ru" :title="row.product_name">{{ truncate(row.product_name, 35) }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="quantity" label="数量" width="80" align="center" />
      <el-table-column label="售价" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.sold_price) }}</template>
      </el-table-column>
      <el-table-column label="应付卖家" width="110" align="right">
        <template #default="{ row }">{{ fmt(row.net_to_seller) }}</template>
      </el-table-column>
      <el-table-column prop="commission_rate" label="佣金率%" width="80" align="center" />
      <el-table-column label="配送费" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.delivery_fee) }}</template>
      </el-table-column>
      <el-table-column label="其他费用" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.fine + row.storage_fee + row.deduction) }}</template>
      </el-table-column>
      <el-table-column label="采购成本" width="110" align="right">
        <template #default="{ row }">
          <span v-if="row.has_sku_mapping">{{ fmt(row.purchase_cost) }}</span>
          <span v-else class="ts-missing">—</span>
        </template>
      </el-table-column>
      <el-table-column label="净利润" width="110" align="right">
        <template #default="{ row }">
          <span :style="{ color: row.net_profit >= 0 ? '#16a34a' : '#dc2626', fontWeight: 600 }">
            {{ fmt(row.net_profit) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.has_return_row" type="info" size="small">退货</el-tag>
          <el-tag v-if="!row.has_sku_mapping" type="warning" size="small">未映射</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="ts-pagi"
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      @current-change="refresh"
      @size-change="refresh"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api from '../../api'

const props = defineProps({
  shopType: String, shopId: [Number, null], dateFrom: String, dateTo: String, currency: String,
})
const emit = defineEmits(['reload'])

const items = ref([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const onlyReturn = ref(false)
const onlyUnmapped = ref(false)
const tableRef = ref(null)

const symbol = computed(() => props.currency === 'CNY' ? '¥' : '₽')

async function refresh() {
  loading.value = true
  try {
    const params = {
      shop_type: props.shopType, date_from: props.dateFrom, date_to: props.dateTo,
      page: page.value, page_size: pageSize.value,
    }
    if (props.shopId) params.shop_id = props.shopId
    if (onlyReturn.value) params.has_return = true
    if (onlyUnmapped.value) params.has_mapping = false
    const { data } = await api.get('/api/finance/orders', { params })
    items.value = data.items
    total.value = data.total
  } catch (e) { console.warn('orders error', e) }
  finally { loading.value = false }
}

function rowClass({ row }) {
  return row.has_sku_mapping ? '' : 'ts-row-missing'
}
function toggleExpand(row, col) {
  if (col?.type === 'expand') return
  tableRef.value?.toggleRowExpansion(row)
}
function onExpand() {}
function truncate(t, n) { return !t ? '' : t.length > n ? t.slice(0, n) + '…' : t }
function fmt(v) { return Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

watch(() => [props.shopType, props.shopId, props.dateFrom, props.dateTo], () => { page.value = 1; refresh() })
onMounted(refresh)
defineExpose({ refresh })
</script>

<style scoped>
.ts-orders { margin-top: 12px; }
.ts-orders-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
.ts-count { color: #64748b; font-size: 13px; margin-left: auto; }
.ts-pagi { margin-top: 12px; justify-content: flex-end; }
.ts-name-ru { font-size: 13px; font-weight: 600; color: #1e293b; }
.ts-missing { color: #f59e0b; }
:deep(.ts-row-missing) { background: #fffbeb !important; }
.ts-expand { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px 24px; padding: 8px 16px; color: #475569; font-size: 13px; }
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/finance/FinanceOrdersTable.vue
git commit -m "feat(finance): FinanceOrdersTable 订单明细表 + 行展开"
```

---

## Task 13: 前端 — FinanceOtherFeesTable.vue + FinanceReconciliation.vue

**Files:**
- Modify: `frontend/src/components/finance/FinanceOtherFeesTable.vue`
- Modify: `frontend/src/components/finance/FinanceReconciliation.vue`

- [ ] **Step 1: 实现 FinanceOtherFeesTable.vue**

重写 `frontend/src/components/finance/FinanceOtherFeesTable.vue`:
```vue
<template>
  <el-collapse v-model="open">
    <el-collapse-item name="fees">
      <template #title>
        <span class="ts-title">💰 其他费用 ({{ total }} 条)</span>
      </template>
      <el-table :data="items" stripe :fit="false" v-loading="loading" max-height="400">
        <el-table-column prop="sale_date" label="日期" width="110" />
        <el-table-column label="类型" width="140">
          <template #default="{ row }">
            <el-tag :type="typeColor(row.fee_type)" size="small">{{ typeLabel(row.fee_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.amount) }} {{ symbol }}</template>
        </el-table-column>
        <el-table-column prop="fee_description" label="描述" min-width="300" show-overflow-tooltip />
      </el-table>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api from '../../api'

const props = defineProps({
  shopType: String, shopId: [Number, null], dateFrom: String, dateTo: String, currency: String,
})
const open = ref([])
const items = ref([])
const total = ref(0)
const loading = ref(false)
const symbol = computed(() => props.currency === 'CNY' ? '¥' : '₽')

const TYPE_LABEL = { storage: '仓储', fine: '罚款', deduction: '扣款', logistics_adjust: '物流调整', other: '其他' }
const TYPE_COLOR = { storage: 'info', fine: 'danger', deduction: 'warning', logistics_adjust: '', other: '' }
function typeLabel(t) { return TYPE_LABEL[t] || t }
function typeColor(t) { return TYPE_COLOR[t] || '' }
function fmt(v) { return Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

async function refresh() {
  loading.value = true
  try {
    const params = { shop_type: props.shopType, date_from: props.dateFrom, date_to: props.dateTo }
    if (props.shopId) params.shop_id = props.shopId
    const { data } = await api.get('/api/finance/other-fees', { params })
    items.value = data.items
    total.value = data.total
    if (total.value > 0 && !open.value.includes('fees')) open.value.push('fees')
  } catch (e) { console.warn('other-fees error', e) }
  finally { loading.value = false }
}

watch(() => [props.shopType, props.shopId, props.dateFrom, props.dateTo], refresh)
onMounted(refresh)
</script>

<style scoped>
.ts-title { font-weight: 600; color: #1e293b; }
</style>
```

- [ ] **Step 2: 实现 FinanceReconciliation.vue**

重写 `frontend/src/components/finance/FinanceReconciliation.vue`:
```vue
<template>
  <el-collapse v-model="open">
    <el-collapse-item name="recon">
      <template #title>
        <span class="ts-title">🔎 对账
          <el-tag v-if="totalDiff > 0" type="danger" size="small" effect="dark" style="margin-left: 8px">
            {{ totalDiff }} 条差异
          </el-tag>
          <el-tag v-else type="success" size="small" effect="plain" style="margin-left: 8px">无差异</el-tag>
        </span>
      </template>

      <div class="ts-section-label">财报多（Orders 未同步的订单，共 {{ missingInOrders.length }} 条）</div>
      <el-table :data="missingInOrders" stripe :fit="false" max-height="280" v-loading="loading">
        <el-table-column prop="srid" label="Srid" width="260" show-overflow-tooltip />
        <el-table-column prop="shop_name" label="店铺" width="140" />
        <el-table-column prop="sale_date" label="销售日期" width="120" />
        <el-table-column label="应付卖家" width="130" align="right">
          <template #default="{ row }">{{ fmt(row.net_to_seller) }} {{ row.currency === 'CNY' ? '¥' : '₽' }}</template>
        </el-table-column>
      </el-table>

      <div class="ts-section-label" style="margin-top: 16px">
        Orders 多（财报未结算的订单，共 {{ missingInFinance.length }} 条）
      </div>
      <el-table :data="missingInFinance" stripe :fit="false" max-height="280" v-loading="loading">
        <el-table-column prop="wb_order_id" label="WB 订单 ID" width="180" show-overflow-tooltip />
        <el-table-column prop="srid" label="Srid" width="260" show-overflow-tooltip />
        <el-table-column prop="shop_name" label="店铺" width="140" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column prop="total_price" label="金额" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.total_price) }}</template>
        </el-table-column>
      </el-table>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api from '../../api'

const props = defineProps({
  shopType: String, shopId: [Number, null], dateFrom: String, dateTo: String,
})
const open = ref([])
const missingInOrders = ref([])
const missingInFinance = ref([])
const loading = ref(false)
const totalDiff = computed(() => missingInOrders.value.length + missingInFinance.value.length)

function fmt(v) { return Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

async function refresh() {
  loading.value = true
  try {
    const params = { shop_type: props.shopType, date_from: props.dateFrom, date_to: props.dateTo }
    if (props.shopId) params.shop_id = props.shopId
    const { data } = await api.get('/api/finance/reconciliation', { params })
    missingInOrders.value = data.missing_in_orders
    missingInFinance.value = data.missing_in_finance
    if (totalDiff.value > 0 && !open.value.includes('recon')) open.value.push('recon')
  } catch (e) { console.warn('recon error', e) }
  finally { loading.value = false }
}

watch(() => [props.shopType, props.shopId, props.dateFrom, props.dateTo], refresh)
onMounted(refresh)
</script>

<style scoped>
.ts-title { font-weight: 600; color: #1e293b; }
.ts-section-label { font-size: 13px; color: #475569; margin: 6px 0; }
</style>
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/finance/FinanceOtherFeesTable.vue frontend/src/components/finance/FinanceReconciliation.vue
git commit -m "feat(finance): FinanceOtherFeesTable + FinanceReconciliation"
```

---

## Task 14: 前端 — FinanceSyncDialog.vue + 整体联调

**Files:**
- Modify: `frontend/src/components/finance/FinanceSyncDialog.vue`

- [ ] **Step 1: 实现 FinanceSyncDialog.vue**

重写 `frontend/src/components/finance/FinanceSyncDialog.vue`:
```vue
<template>
  <el-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)"
             title="手动同步财务报告" width="600px" :close-on-click-modal="false">
    <div v-if="!running">
      <el-form label-width="100px">
        <el-form-item label="店铺">
          <el-select v-model="selectedShops" multiple placeholder="选择店铺（可多选）" style="width: 100%">
            <el-option v-for="s in shops" :key="s.id" :label="`${s.name} (${s.type === 'cross_border' ? 'CNY' : 'RUB'})`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期范围">
          <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="快捷">
          <el-button size="small" @click="setRange('lastWeek')">上周</el-button>
          <el-button size="small" @click="setRange('last90d')">近 90 天（全历史）</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div v-else class="ts-progress">
      <div v-for="log in logs" :key="log.id" class="ts-log-row">
        <span class="ts-log-shop">{{ log.shop_name }}</span>
        <el-tag :type="statusType(log.status)" size="small">{{ statusLabel(log.status) }}</el-tag>
        <span v-if="log.status === 'success'" class="ts-log-stats">
          {{ log.rows_fetched }} 行 → {{ log.orders_merged }} 订单 + {{ log.other_fees_count }} 其他
        </span>
        <span v-if="log.status === 'failed'" class="ts-log-err" :title="log.error_message">
          {{ log.error_message || '失败' }}
        </span>
      </div>
    </div>

    <template #footer>
      <el-button @click="close" :disabled="running && !allDone">关闭</el-button>
      <el-button v-if="!running" type="primary" @click="startSync" :disabled="!canSubmit">
        开始同步
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../../api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])

const shops = ref([])
const selectedShops = ref([])
const dateRange = ref(getLast90Range())
const running = ref(false)
const logs = ref([])
const pollTimer = ref(null)
let pollIds = []

function getLast90Range() {
  const end = new Date(); const start = new Date(end.getTime() - 89 * 86400000)
  const fmt = d => d.toISOString().slice(0, 10)
  return [fmt(start), fmt(end)]
}
function setRange(key) {
  const today = new Date(); const day = today.getDay() || 7
  const fmt = d => d.toISOString().slice(0, 10)
  if (key === 'lastWeek') {
    const lastMon = new Date(today.getTime() - (day + 6) * 86400000)
    const lastSun = new Date(today.getTime() - day * 86400000)
    dateRange.value = [fmt(lastMon), fmt(lastSun)]
  } else { dateRange.value = getLast90Range() }
}

const canSubmit = computed(() => selectedShops.value.length > 0 && dateRange.value && dateRange.value[0])
const allDone = computed(() => logs.value.length > 0 && logs.value.every(l => l.status !== 'running'))

async function fetchShops() {
  try {
    const { data } = await api.get('/api/shops')
    shops.value = data || []
  } catch (e) { console.warn('shops error', e) }
}

async function startSync() {
  try {
    const { data } = await api.post('/api/finance/sync', {
      shop_ids: selectedShops.value,
      date_from: dateRange.value[0], date_to: dateRange.value[1],
    })
    pollIds = data.sync_log_ids
    running.value = true
    logs.value = pollIds.map(id => ({ id, status: 'running', shop_name: '...' }))
    startPolling()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '触发同步失败')
  }
}

function startPolling() {
  if (pollTimer.value) clearInterval(pollTimer.value)
  pollTimer.value = setInterval(async () => {
    try {
      const { data } = await api.get('/api/finance/sync-logs', { params: { ids: pollIds.join(',') } })
      logs.value = data
      if (data.every(l => l.status !== 'running')) {
        clearInterval(pollTimer.value); pollTimer.value = null
      }
    } catch (e) { console.warn('poll err', e) }
  }, 3000)
}

function statusType(s) { return s === 'success' ? 'success' : s === 'failed' ? 'danger' : 'info' }
function statusLabel(s) { return { running: '进行中', success: '完成', failed: '失败' }[s] || s }

function close() {
  if (pollTimer.value) { clearInterval(pollTimer.value); pollTimer.value = null }
  emit('update:modelValue', false)
  if (allDone.value) {
    // 让父组件刷新
    window.dispatchEvent(new Event('finance-sync-done'))
  }
  setTimeout(() => { running.value = false; logs.value = [] }, 300)
}

watch(() => props.modelValue, v => { if (v) { fetchShops() } })
onMounted(fetchShops)
onUnmounted(() => { if (pollTimer.value) clearInterval(pollTimer.value) })
</script>

<style scoped>
.ts-progress { max-height: 400px; overflow-y: auto; padding: 8px; }
.ts-log-row { display: flex; gap: 10px; align-items: center; padding: 6px 0; border-bottom: 1px solid #f1f5f9; }
.ts-log-shop { font-weight: 600; min-width: 140px; }
.ts-log-stats { color: #64748b; font-size: 12px; }
.ts-log-err { color: #dc2626; font-size: 12px; }
</style>
```

- [ ] **Step 2: 让 FinanceTabContent 响应同步完成事件**

编辑 `frontend/src/components/finance/FinanceTabContent.vue`，在 `onMounted` 后追加：
```js
window.addEventListener('finance-sync-done', reloadAll)
import { onUnmounted } from 'vue'
onUnmounted(() => window.removeEventListener('finance-sync-done', reloadAll))
```

注意：`onUnmounted` 的 import 要加在文件顶部原有 import 行里，和其他 vue 导入一起。

- [ ] **Step 3: 手动验证**

```bash
# 1. 启动后端
cd backend && uvicorn app.main:app --reload --port 8000

# 2. 启动前端
cd ../frontend && npm run dev

# 3. 浏览器 http://localhost:5173/finance
```

验证清单：
- [ ] 页面加载，能看到两个 Tab（跨境店 CNY / 本土店 RUB）
- [ ] 每个 Tab 顶部有店铺下拉 + 日期范围 + 快捷按钮
- [ ] 汇总卡片 8 张，数字显示正确（初期全 0）
- [ ] 订单明细表能滚动，有分页，行点击展开
- [ ] 其他费用和对账是折叠状态，有差异会自动展开
- [ ] 点击"手动同步"→ 弹窗 → 选店铺 → 开始 → 进度面板每 3 秒刷新
- [ ] 同步完成后汇总和列表自动刷新
- [ ] 未映射订单行是黄底，采购成本显示"—"
- [ ] 切换 Tab 时数据正确区分 CNY 和 RUB

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/finance/FinanceSyncDialog.vue frontend/src/components/finance/FinanceTabContent.vue
git commit -m "feat(finance): FinanceSyncDialog + 同步完成自动刷新"
```

---

## 完成后的总结提交

所有 task 完成后，跑一次全量测试确保没有回归：

```bash
cd backend && pytest -v
```
Expected: 所有 finance 相关测试 + 原有测试全部通过。

---

## Plan 自检记录

**Spec 覆盖检查：**
- ✅ 3 张表模型 → Task 1
- ✅ WB API fetch + 分页 + 429 → Task 2
- ✅ 按 Srid 合并 → Task 3
- ✅ 非订单费用分流 → Task 4
- ✅ 采购成本 + 利润 + 缺映射处理 → Task 5
- ✅ sync_shop 幂等 → Task 6
- ✅ /summary /orders /other-fees /reconciliation → Task 7
- ✅ /sync /sync-logs /recalc-profit → Task 8
- ✅ Scheduler 周一定时 → Task 9
- ✅ 前端 2 Tab + 筛选 → Task 10
- ✅ 汇总卡片 → Task 11
- ✅ 订单明细表 + 行展开 → Task 12
- ✅ 其他费用 + 对账 → Task 13
- ✅ 同步弹窗 + 进度 → Task 14

**类型/命名一致性检查：**
- `merge_rows_by_srid / extract_other_fees / fill_purchase_cost_and_profit / sync_shop` 命名全程一致
- `FinanceOrderRecord / FinanceOtherFee / FinanceSyncLog` 三处 model 名一致
- `shop.type = 'cross_border' / 'local'` 在 sync / router / 前端全程一致
- `currency = 'CNY' / 'RUB'` 一致
- API 参数 `shop_type, shop_id, date_from, date_to` 前后端一致

**Placeholder 扫描：** 无 TBD / TODO / "add validation" 等空壳。每个步骤都有完整代码或完整命令。
