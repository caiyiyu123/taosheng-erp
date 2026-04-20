# 财务统计模块设计

**日期：** 2026-04-20
**作者：** @caiyi + Claude (brainstorming)
**状态：** Draft，待实现

## 目标

自动抓取 WB 后台每周详细财务报告，以"每订单一行"为核心口径存储，支持：
1. 按店铺 / 日期范围查看销售、佣金、物流、罚款、净利润汇总
2. 订单明细列表（合并同一 Srid 的 销售 / 物流 / 退货 行）
3. 非订单费用（仓储、全店罚款、扣款等）单独一块
4. 订单覆盖对账：财报有但 Orders 模块没同步到 / Orders 有但财报未结算

## 架构总览

```
前端 Finance.vue（2 Tab：跨境店 CNY / 本土店 RUB）
   ↓ REST
Backend router/finance.py
   ↓
Service finance_sync.py  ── 调 WB API → 合并 → 落库
   ↓
3 张表：finance_order_records / finance_other_fees / finance_sync_log
   ↑
Scheduler：每周一 03:00 Moscow 自动同步上周所有活跃店铺
```

- 数据模型 3 张表，不改 `Order` 模型
- 订单 ↔ 财报通过 `srid` 关联（Order 表已存在该字段）
- 手动同步走后台任务 + 前端轮询
- 币种是数据属性，入库时按 `shop.type` 自动填 `CNY` 或 `RUB`

## 核心决策（含理由）

| 决策 | 选择 | 理由 |
|---|---|---|
| 模块用途 | 汇总 + 明细 + 非订单费用 + 订单覆盖对账 | 一站式财务视图 |
| 合并键 | `Srid`（和 Order.srid 同源） | WB 内部发货唯一 ID，3 行（销售/物流/退货）共用 |
| 非订单费用 | 单独表 `finance_other_fees`，Srid 为空的行 | 仓储/罚款等不属于任何订单，强行分摊会污染订单利润 |
| 同步触发 | 定时（每周一 3:00 Moscow）+ 手动补拉 | 官方结算周期一周；手动用于初次导入历史和重拉 |
| 历史深度 | 全部可拉（WB API 约近 3 个月） | 用户要求 |
| 对账范围 | 仅"订单覆盖"对账，不做金额/状态 | 金额易受四舍五入/佣金调整扰动，覆盖核对最稳定且最有价值 |
| 利润公式 | `净利润 = 应付卖家(C34) − 配送费(C37) − 罚款 − 仓储 − 扣款 − 采购成本` | 应付卖家已减过佣金和平台扣费，不用再减佣金 |
| 缺 SKU 映射 | 采购成本记 0，前端黄色标记"未映射"，汇总下方提示 "N 条缺映射" 跳转映射页 | 保证数字可用，同时醒目提醒用户补映射 |
| 币种处理 | 按店铺类型分 Tab（跨境 CNY / 本土 RUB），数据库存 currency 字段 | 跨境店账单本来就是 CNY，本土店是 RUB，不能混算 |
| 主筛选日期 | 销售日期 `sale_date` (C13) | 财务口径最干净；下单日期 + 结算周期也全部存下来备用 |

## 数据模型

### `finance_order_records`（每 Srid 一行）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| shop_id | FK→shops | |
| srid | str(200) | **唯一键 (shop_id, srid)** |
| currency | 'CNY' / 'RUB' | 入库时根据 `shop.type` 自动填 |
| order_date | date | C12 买家下单日期 |
| sale_date | date | C13 销售日期（**主筛选字段**） |
| report_period_start | date | 报告结算周期起始 |
| report_period_end | date | 报告结算周期结束 |
| nm_id | str(50) | C4 WB 商品编号 |
| shop_sku | str(200) | C6 供应商 SKU |
| product_name | str(500) | C7 |
| barcode | str(100) | C9 |
| category | str(200) | C3 商品品类 |
| size | str(50) | C8 尺码 |
| quantity | int | C35 交付数量 |
| return_quantity | int | C36 退货数量 |
| retail_price | float | C15 零售价 |
| sold_price | float | C16 WB 实际售价 |
| commission_rate | float | C24 佣金率 % |
| commission_amount | float | C32 + C33 佣金含税 |
| net_to_seller | float | C34 应付卖家 |
| delivery_fee | float | 该 Srid 所有物流行 C37 合计 |
| fine | float | 该 Srid C41 合计 |
| storage_fee | float | 该 Srid C61 合计 |
| deduction | float | 该 Srid C62 合计 |
| purchase_cost | float | `SkuMapping → Product.purchase_price × quantity` |
| net_profit | float | `net_to_seller − delivery_fee − fine − storage_fee − deduction − purchase_cost` |
| has_sku_mapping | bool | false 时前端黄色高亮 |
| warehouse | str(200) | C50 仓库 |
| country | str(10) | C51 国家 |
| sale_type | str(50) | C75 销售方式（FBW/FBS） |
| has_return_row | bool | 是否存在退货行 |
| created_at | datetime | |
| updated_at | datetime | |

**索引：**
- `(shop_id, srid)` unique
- `(shop_id, sale_date)` 查询
- `(shop_id, has_sku_mapping)` 快速找未映射

### `finance_other_fees`（Srid 为空的非订单费用）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| shop_id | FK | |
| currency | 'CNY' / 'RUB' | |
| sale_date | date | C13 |
| report_period_start | date | |
| report_period_end | date | |
| fee_type | enum('storage','fine','logistics_adjust','deduction','other') | 按 C11 付款依据 + C43 类型推断 |
| fee_description | str(500) | 从 C43 或 C44 原样保留 |
| amount | float | |
| raw_row | json | 整行原始数据，防字段遗漏 |
| created_at | datetime | |

**索引：** `(shop_id, sale_date)`，`(shop_id, fee_type)`

### `finance_sync_log`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| shop_id | FK | |
| triggered_by | 'cron' / 'manual' | |
| user_id | FK→users, nullable | |
| date_from | date | |
| date_to | date | |
| status | 'running' / 'success' / 'failed' | |
| rows_fetched | int | WB 原始行数 |
| orders_merged | int | 合并后订单行数 |
| other_fees_count | int | 非订单费用条数 |
| error_message | text | |
| started_at | datetime | |
| finished_at | datetime, nullable | |

## WB API 对接

**接口：** `GET /api/v5/supplier/reportDetailByPeriod`

- 参数：`dateFrom` (YYYY-MM-DD, 必)、`dateTo` (必)、`rrdid` (游标，首页 0)、`limit` (默认 100000)
- 返回：`[{row1}, {row2}, ...]`，每行约等于 xlsx 一行
- 分页：取末行 `rrd_id` 作下次 `rrdid`，返回空数组结束
- 限流：**1 请求 / 分钟 / token**，429 时指数退避（60s → 120s → 300s，最多 3 次）

**关键字段名（俄文源，跨境店机翻中文列头不可依赖）：**

| 代码 | 俄文字段 | 说明 |
|---|---|---|
| srid | `srid` | 订单唯一键 |
| supplier_oper_name | `supplier_oper_name` | 对应 C11 付款依据：`Продажа` / `Логистика` / `Возврат` / `Штраф` 等 |
| doc_type_name | `doc_type_name` | 对应 C10 文档类型 |
| order_dt | `order_dt` | C12 下单日期 |
| sale_dt | `sale_dt` | C13 销售日期 |
| rr_dt | `rr_dt` | 报告日期 |
| nm_id | `nm_id` | C4 |
| sa_name | `sa_name` | C6 供应商 SKU |
| subject_name | `subject_name` | C3 品类 |
| brand_name | `brand_name` | C5 |
| ts_name | `ts_name` | C8 尺码 |
| barcode | `barcode` | C9 |
| retail_price | `retail_price` | C15 |
| retail_amount | `retail_amount` | C16 实际售出金额 |
| ppvz_for_pay | `ppvz_for_pay` | **C34 应付卖家** |
| commission_percent | `commission_percent` | C24 |
| ppvz_vw | `ppvz_vw` | C32 佣金不含税 |
| ppvz_vw_nds | `ppvz_vw_nds` | C33 佣金增值税 |
| delivery_rub | `delivery_rub` | C37 配送服务费 |
| penalty | `penalty` | C41 罚款 |
| storage_fee | `storage_fee` | C61 仓储 |
| deduction | `deduction` | C62 扣款 |
| quantity | `quantity` | C14 数量 |
| office_name | `office_name` | C47 |
| site_country | `site_country` | C51 国家 |
| gi_box_type_name | `gi_box_type_name` | C52 箱型 |
| supplier_reward | `supplier_reward` | 卖家佣金字段 |
| srv_dbs | `srv_dbs` | 销售方式 |

## 同步流程

对每个店铺：

1. 建 `finance_sync_log` 记录，`status='running'`
2. 分页拉取原始行 → `rows`
3. 分流：`rows_with_srid` 和 `rows_without_srid`（srid 为空或 None）
4. 按 srid 分组合并 → `merged_records`：
   - 销售行（`supplier_oper_name='Продажа'`）：取 retail_price / sold_price / commission / net_to_seller / quantity / 产品信息
   - 物流行（`supplier_oper_name='Логистика'`）：累加 `delivery_fee`
   - 退货行（`supplier_oper_name='Возврат'`）：`has_return_row=True`，累加 `return_quantity`、负的 `net_to_seller`（退款）
   - 其他带 srid 的行（罚款/仓储针对单订单）：累加到 `fine / storage_fee / deduction`
5. 填充采购成本和利润：
   ```python
   mapping = SkuMapping.query(shop_id, shop_sku=rec.shop_sku).first()
   if mapping:
       rec.purchase_cost = mapping.product.purchase_price * rec.quantity
       rec.has_sku_mapping = True
   else:
       rec.purchase_cost = 0
       rec.has_sku_mapping = False
   rec.net_profit = rec.net_to_seller - rec.delivery_fee - rec.fine \
                    - rec.storage_fee - rec.deduction - rec.purchase_cost
   ```
6. 非订单费用：逐行塞入 `finance_other_fees`
   - `fee_type` 推断：`Логистика/Штраф/Хранение/Удержание` → `logistics_adjust/fine/storage/deduction`，其他 `other`
7. **事务内幂等落库：**
   - 删除 `finance_order_records WHERE shop_id=X AND sale_date BETWEEN date_from AND date_to`
   - 删除 `finance_other_fees` 同条件
   - 批量 insert 新记录
8. 更新 `finance_sync_log`：status、各计数、`finished_at`
9. 异常：`status='failed'`, 写 `error_message`

## Backend 接口

### `GET /api/finance/summary`
Query: `shop_type`, `shop_id?`, `date_from`, `date_to`
Resp:
```json
{
  "currency": "CNY",
  "order_count": 123,
  "total_net_to_seller": 15000.50,
  "total_commission": 1200.00,
  "total_delivery_fee": 850.00,
  "total_fine": 50.00,
  "total_storage": 100.00,
  "total_deduction": 0,
  "total_purchase_cost": 6000.00,
  "total_net_profit": 8000.50,
  "total_other_fees": 300.00,
  "final_profit": 7700.50,
  "missing_mapping_count": 5
}
```

### `GET /api/finance/orders`
Query: `shop_type`, `shop_id?`, `date_from`, `date_to`, `has_return?`, `has_mapping?`, `page=1`, `page_size=20`, `sort=-sale_date`
Resp:
```json
{
  "items": [
    {
      "id": 42,
      "srid": "ebC.r31d5...",
      "shop_id": 1,
      "shop_name": "店铺A",
      "sale_date": "2026-04-13",
      "order_date": "2026-04-08",
      "nm_id": "507336942",
      "shop_sku": "CYY008-1",
      "product_name": "Подголовник...",
      "image_url": "...",
      "quantity": 1,
      "return_quantity": 0,
      "sold_price": 96.47,
      "net_to_seller": 90.01,
      "commission_rate": 9.5,
      "commission_amount": 6.46,
      "delivery_fee": 13.04,
      "fine": 0,
      "storage_fee": 0,
      "deduction": 0,
      "purchase_cost": 30.00,
      "net_profit": 46.97,
      "has_sku_mapping": true,
      "has_return_row": false,
      "currency": "CNY"
    }
  ],
  "total": 123
}
```

### `GET /api/finance/other-fees`
Query: `shop_type`, `shop_id?`, `date_from`, `date_to`, `fee_type?`
Resp: `{"items": [...], "total": N}`

### `GET /api/finance/reconciliation`
Query: `shop_type`, `shop_id?`, `date_from`, `date_to`
Resp:
```json
{
  "missing_in_orders": [
    {"srid": "ebC.r...", "sale_date": "2026-04-10", "net_to_seller": 150.00, "shop_name": "店铺A"}
  ],
  "missing_in_finance": [
    {"wb_order_id": "WB-001", "srid": "ebY...", "shop_name": "店铺A", "created_at": "2026-04-15", "total_price": 2350}
  ]
}
```

**SQL：**
```sql
-- missing_in_orders
SELECT f.* FROM finance_order_records f
LEFT JOIN orders o ON o.srid = f.srid AND o.shop_id = f.shop_id
WHERE o.id IS NULL
  AND f.shop_id IN (:accessible_shops)
  AND f.sale_date BETWEEN :from AND :to

-- missing_in_finance
SELECT o.* FROM orders o
LEFT JOIN finance_order_records f ON f.srid = o.srid AND f.shop_id = o.shop_id
WHERE f.id IS NULL
  AND o.srid <> ''
  AND o.shop_id IN (:accessible_shops)
  AND o.created_at BETWEEN :from AND :to
```

**边界处理：**
- `orders.srid = ''` 的老数据排除（否则永远报差异）
- 默认对账区间 = 当前日期 − 7 天（避开本周未结算的正常情况）
- 只展示，不自动修复 Order 表

### `POST /api/finance/sync`
Body: `{"shop_ids": [1, 2], "date_from": "2026-04-01", "date_to": "2026-04-07"}`
Resp: `{"sync_log_ids": [101, 102]}`
- 后端 `ThreadPoolExecutor(max_workers=2)` 启动任务，立即返回
- 仅 `admin` 角色可调（系统只有 admin / operator 两种角色，写类敏感接口限 admin）

### `GET /api/finance/sync-logs`
Query: `ids?` (查指定), `shop_id?`, `limit=20`
Resp: `[{id, shop_id, shop_name, status, rows_fetched, orders_merged, other_fees_count, started_at, finished_at, error_message}, ...]`
- 前端每 3s 轮询，全部 `status in ('success','failed')` 后停止并刷新数据

### `POST /api/finance/recalc-profit`
Body: `{"shop_id": 1}`
- 只重算该 shop 所有 records 的 `purchase_cost / has_sku_mapping / net_profit`，不调 WB API
- 仅 `admin` 角色可调

### 通用规则

- 全部接口 `Depends(require_module("finance"))`
- `accessible_shops` 自动过滤
- 响应金额保留 2 位小数，不做币种换算

## 定时任务

扩展 `app/services/scheduler.py`：

```python
scheduler.add_job(
    weekly_finance_sync,
    'cron',
    day_of_week='mon',
    hour=3,
    minute=0,
    timezone='Europe/Moscow',
    id='weekly_finance_sync',
)

def weekly_finance_sync():
    # 所有 is_active=True 的 shop
    # 区间 = 上周一 00:00 ~ 上周日 23:59 (Moscow 时区)
    # 并发 max_workers=2，逐店铺调 finance_sync_service.sync_shop()
```

手动触发不走 scheduler，独立 `ThreadPoolExecutor`，不抢 scheduler 线程。

## 前端

### 文件拆分

```
frontend/src/views/Finance.vue                    # Tab 外壳 + 全局工具栏
frontend/src/components/finance/
  ├─ FinanceTabContent.vue       # 单 Tab 完整内容，prop: shop_type
  ├─ FinanceSummaryCards.vue     # 汇总卡片行
  ├─ FinanceOrdersTable.vue      # 订单明细表
  ├─ FinanceOtherFeesTable.vue   # 其他费用表
  ├─ FinanceReconciliation.vue   # 对账两张子表
  └─ FinanceSyncDialog.vue       # 手动同步 + 进度
```

### 布局（每个 Tab 内）

```
[店铺下拉: 全部 ▼] [日期: 最近4周 ▼] [快捷: 本周/上周/本月]
──────────────────────────────────────────────────────────
[9 张汇总卡片: 订单数 / 应付卖家 / 佣金 / 配送 / 其他费用 /
 采购成本 / 订单利润 / 非订单费用合计 / 最终利润]
⚠ N 条订单采购成本缺失 [去 SKU 映射]
──────────────────────────────────────────────────────────
📋 订单明细   筛选: ☐仅退货 ☐仅未映射
[el-table，点击行展开查看全部字段]
──────────────────────────────────────────────────────────
💰 其他费用 (N 条)                            [展开 ▾]
──────────────────────────────────────────────────────────
🔎 对账 (N 条差异)                            [展开 ▾]
  · 财报多（Orders 未同步）
  · Orders 多（财报未结算）
```

### 订单明细表列

固定 `:fit="false"` + 每列固定 width，遵循项目规约：

| 列 | width | 说明 |
|---|---|---|
| 销售日期 | 100 | |
| 图片 | 76 | |
| SKU | 130 | |
| 产品名 | 300 | 俄语 13px bold / 中文 11.5px gray 两行；`truncate(name, 35)` |
| 数量 | 80 | |
| 售价 | 100 | 带币种后缀 |
| 应付卖家 | 110 | |
| 佣金率 | 80 | 百分比 |
| 配送费 | 100 | |
| 其他费用 | 100 | 罚款+仓储+扣款合计 |
| 采购成本 | 110 | 未映射显示 "—" + 黄底 |
| 净利润 | 110 | 正绿负红 |
| 状态 | 120 | 退货 / 未映射 徽章 |

### 交互要点

- **Tab 切换** → currency 变，所有 section 刷新
- **店铺 / 日期切换** → 统一 `fetchAll()` 刷新 4 section
- **点击行** → 行展开区显示剩余字段（仓库、配货任务号、条码、报告周期、佣金金额等）
- **产品名翻译** → 复用 Dashboard 的 `POST /api/dashboard/translate-batch` 批量拉取
- **手动同步弹窗** → 多选店铺 + 日期范围，提交后变进度面板，每 3s 轮询 `/sync-logs`
- **对账分级展示** → 0 条差异时折叠且隐藏，有差异时顶部红点提示

## 测试策略

### `backend/tests/test_finance_sync.py`
- `test_merge_by_srid`：3 行（销售/物流/退货）同 srid → 1 条 record，字段各项正确
- `test_non_order_fees`：srid 为空的行 → 进 `other_fees`，不进 `order_records`
- `test_idempotent_resync`：同区间重拉 2 次 → 最终记录数不变
- `test_purchase_cost`：有映射 → `purchase_cost > 0, has_sku_mapping=True`；无映射 → `0 / False`
- `test_profit_formula`：手造数据验证 `net_profit` 公式
- `test_currency_by_shop_type`：跨境店 → `CNY`；本土店 → `RUB`

### `backend/tests/test_finance_endpoints.py`
- `test_summary`：汇总数字正确，按 shop_type 过滤
- `test_orders_list`：分页、筛选、排序
- `test_reconciliation`：手造 1 财报多 + 1 Orders 多，接口正确返回
- `test_sync_trigger`：POST `/sync` 返回 log ids，DB 里有 running 记录
- `test_recalc_profit`：补映射后调接口，records 的 `purchase_cost` 刷新
- `test_permissions`：非 admin 用户被权限过滤，看不到无权限店铺的数据
- `test_currency_tab_filter`：Tab 传入 `shop_type='cross_border'` 只返 CNY 数据

Mock WB API 的 `fetch_finance_report` 返回固定 JSON fixture，不发真实请求。

## 文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/app/models/finance.py` | **新建** | `FinanceOrderRecord` / `FinanceOtherFee` / `FinanceSyncLog` |
| `backend/app/services/finance_sync.py` | **新建** | 合并 / 计算 / 落库 |
| `backend/app/services/wb_api.py` | 修改 | 加 `fetch_finance_report(token, date_from, date_to)` |
| `backend/app/services/scheduler.py` | 修改 | 注册 `weekly_finance_sync` |
| `backend/app/routers/finance.py` | **重写** | 7 个端点 |
| `backend/app/main.py` | 可能修改 | `main.py:13` 有 `Base.metadata.create_all`，确保新 model 被 import（通过 `finance` router 间接 import `finance` model 即可） |
| `backend/tests/test_finance_sync.py` | **新建** | |
| `backend/tests/test_finance_endpoints.py` | **新建** | |
| `frontend/src/views/Finance.vue` | **重写** | Tab 外壳 |
| `frontend/src/components/finance/*.vue` | **新建** × 6 | 见前端拆分 |

`router/index.js` 和 `Layout.vue` 的 `/finance` 路由和菜单项已存在，无需改。

## 未覆盖 / 未来考虑

- **金额对账**（财报 vs Orders.total_price）：本期不做，易产生误报
- **状态对账**：同上
- **导出 xlsx**：后续可加
- **币种换算视图**：后续可加（需维护历史汇率表）
- **自动创建 Order**：对账发现"财报多"时，暂不自动创建 Order 记录，只展示
- **历史汇率 / 历史采购价**：采购成本用当前 `Product.purchase_price`，不做时点快照
