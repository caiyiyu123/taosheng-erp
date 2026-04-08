# 订单同步重构设计

## 背景

当前订单同步代码经过多轮补丁，FBS 和 FBW 逻辑混杂，价格回填散布在三个函数中，导致数据缺失且难以维护。本次重构从零设计，目标是获取完整的 FBS + FBW 订单数据。

## WB API 数据源总结

| API | 端点 | 覆盖 | FBS | FBW | 价格单位 | 类型标识 |
|-----|------|------|-----|-----|----------|----------|
| Marketplace | `/api/v3/orders` | 90天 | ✅ | ❌ | 戈比(÷100) | deliveryType |
| Marketplace | `/api/v3/orders/new` | 当前待处理 | ✅ | ❌ | 戈比(÷100) | — |
| Statistics Orders | `/api/v1/supplier/orders` | ~20天 | ✅ | ✅ | 卢布 | warehouseType |
| Statistics Sales | `/api/v1/supplier/sales` | ~20天 | ✅ | ✅ | 卢布 | warehouseType |
| Report Detail | `/api/v5/supplier/reportDetailByPeriod` | 90天(仅已结算) | ✅ | ✅ | 卢布 | gi_box_type_name |

### Statistics Orders 双模式

- `flag=0`: 按 lastChangeDate 分页，适合抓最近修改的订单
- `flag=1`: 按订单创建日期返回，适合按时间范围查询
- 两种模式合并去重（按 srid），最大化覆盖

### 已知 API 限制

- WB 没有 FBW 专用订单 API
- Statistics API 实际只保留 ~20 天数据（文档称 90 天但实测不符）
- Report Detail 仅包含已结算订单（下单到结算约 14-21 天）
- FBW 存在 ~5-10 天盲区：超出 Statistics 保留期但未在 Report Detail 结算的订单。此盲区会随下次同步自动补全。

## 架构设计

### 方案：FBS/FBW 分离独立同步

FBS 和 FBW 由各自独立的函数处理，互不干扰。

```
sync_shop_orders(db, shop)
  │
  ├─ 1. 获取共享数据
  │     cards = fetch_cards()
  │     stat_orders = fetch_statistics_orders()  # flag=0+1 合并
  │     stat_sales = fetch_statistics_sales()
  │
  ├─ 2. _sync_fbs_orders(db, shop, api_token, cards, stat_orders)
  │
  ├─ 3. _sync_fbw_orders(db, shop, api_token, cards, stat_orders, stat_sales)
  │
  ├─ 4. _update_order_statuses(db, shop, api_token)
  │
  └─ 5. commit + 更新 last_sync_at
```

### FBS 订单同步

数据源：Marketplace API `/api/v3/orders`（90天）+ `/api/v3/orders/new`

```
Marketplace API (90天历史 + 当前待处理)
  ↓ 按 id 去重（new 优先，有更完整的价格字段）
  ↓
价格处理：
  ├─ currencyCode=643(RUB) → salePrice÷100 = price_rub
  ├─ currencyCode≠643, convertedCurrencyCode=643 → convertedFinalPrice÷100 = price_rub
  └─ price_rub 仍为 0 → 从 stat_orders 按 srid 匹配取 finishedPrice/priceWithDisc
  ↓
total_price 处理（用于跨境店 CNY 显示）：
  ├─ 有 convertedCurrency 且不同于 orderCurrency → converted 价格
  └─ 单一货币 → 同 price_rub
  ↓
写入 Order:
  wb_order_id = str(marketplace_id)
  srid = rid（保持原样）
  order_type = "FBS"
  price_rub = 卢布价格
```

### FBW 订单同步

三数据源按优先级合并：

```
第1步：构建已知 FBS srid 集合
  fbs_srids = 数据库中所有 FBS 订单的 srid

第2步：从三个源收集 FBW 候选，统一到 fbw_records[srid]

  源① Statistics Orders（优先级最高）
    筛选：warehouseType 含 "WB"
    排除：srid 在 fbs_srids 中
    价格：priceWithDisc 或 finishedPrice（卢布，直接用）

  源② Statistics Sales（补充①未覆盖的）
    筛选：warehouseType 含 "WB"
    排除：srid 已在 fbw_records 中 或 在 fbs_srids 中
    价格：priceWithDisc 或 finishedPrice（卢布）
    注意：saleID 以 "R" 开头表示退货

  源③ Report Detail（补充①②都未覆盖的，填充 20-90 天历史）
    按 srid 分组，对每组：
      排除：srid 已在 fbw_records 中 或 在 fbs_srids 中
      分类（三级判定）：
        a. gi_box_type_name 含 "FBW"/"FBO" → 确认 FBW
        b. gi_box_type_name 含 "Маркетплейс"/"FBS" → 确认 FBS，跳过
        c. 无 gi_box_type_name：
           - 有销售记录(quantity>0, retail_price_withdisc_rub>0) → 包含
           - hex 格式 srid 且有 nm_id → 包含
           - 其余 → 跳过（手续费/物流记录）
      选择最佳记录：优先有 qty>0 且 price>0 的
      价格：retail_price_withdisc_rub（卢布）

第3步：写入数据库
  wb_order_id = "fbo_{srid}"
  srid = 原样保留
  order_type = "FBW"
  price_rub = 卢布价格（从对应源直接取）
```

### 状态更新

仅针对 FBS 订单（FBW 无状态查询 API）：

- 查询数据库中所有非终态 FBS 订单
- 通过 Marketplace API 批量查询状态
- 映射 WB 状态到系统状态（pending/in_transit/completed/cancelled/rejected/returned）

### 已有订单更新规则

增量同步时对已存在订单的处理：

- `price_rub == 0` 且新数据有价格 → 更新
- `srid` 为空且新数据有 srid → 补填
- `total_price == 0` 且新数据有价格 → 更新
- 其余字段不覆盖（避免好数据被差数据覆盖）

## 删除的旧逻辑

- `_backfill_order_prices()` — 删除，价格在创建时确定
- `_update_order_rub_prices()` — 删除，price_rub 在创建时确定
- FBS 零价格订单的额外历史拉取（Step 2b）— 删除，改用 Statistics 回填

## 文件影响

- `backend/app/services/sync.py` — 重写 `sync_shop_orders`、`_sync_fbs_orders`(新)、`_sync_fbw_orders`(新)，删除旧的回填函数
- `backend/app/services/wb_api.py` — `fetch_statistics_orders` 保持 flag=0+1 双模式（已实现）
- 其余文件不受影响（模型、路由、前端不变）
