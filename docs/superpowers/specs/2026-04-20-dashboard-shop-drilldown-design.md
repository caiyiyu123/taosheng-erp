# Dashboard 店铺下钻模块设计

## Context

在数据看板（Dashboard）的近30天订单趋势图下方新增"店铺看板"模块，支持从"店铺方块 → 商品销量排行 → 商品每日趋势"三级下钻，帮助运营在同一页面快速对比各店铺的当日动态与商品热销情况。

## 设计决策

- **展示形式**：原地展开，在 Dashboard 内通过视图切换（`viewMode`）呈现三级视图，面包屑返回
- **数据聚合**：实时 SQL 聚合，不做预聚合表；方案 A（扩展现有 dashboard 路由）
- **时区**：全部按 Moscow 时区（UTC+3），与现有 `/api/dashboard/stats` 保持一致
- **权限**：沿用 `get_accessible_shop_ids`，店铺越权返回 403

## 后端实现

### 文件变更

| 文件 | 操作 |
|------|------|
| `backend/app/routers/dashboard.py` | 新增 3 个端点 |
| `backend/app/schemas/dashboard.py`（如存在则扩展，否则在路由内定义 Pydantic 模型） | 新增响应模型 |

### 新增端点

#### 1. `GET /api/dashboard/shops`

返回当前用户可访问的所有店铺方块数据。

**Query params:** 无

**Response:**
```json
{
  "shops": [
    {
      "id": 1,
      "name": "店铺A",
      "today_orders": 12,
      "today_sales": 45000.00,
      "last_30d_sales": 850000.00,
      "currency": "RUB"
    }
  ]
}
```

**实现要点:**
- 使用 `get_accessible_shop_ids` 过滤可见店铺
- 一条 SQL 按 `shop_id` GROUP BY，用 `CASE WHEN order_date = today` 聚合今日订单数/销售额，`CASE WHEN order_date >= d30_start` 聚合近30天销售额
- 金额按店铺 `currency` 原币返回（不做币种换算，与现有 Dashboard 一致）
- 店铺无订单也要返回（订单字段为 0）

#### 2. `GET /api/dashboard/shops/{shop_id}/products`

返回指定店铺的商品销量排行（4 个时间窗口）。

**Query params:** 无

**Response:**
```json
{
  "shop_id": 1,
  "shop_name": "店铺A",
  "products": [
    {
      "nm_id": 123456,
      "product_name": "商品名",
      "today_orders": 5,
      "yesterday_orders": 3,
      "last_7d_orders": 28,
      "last_30d_orders": 120
    }
  ]
}
```

**实现要点:**
- 权限校验：`shop_id` 不在 `get_accessible_shop_ids` 内返回 403
- 一条 SQL 按 `nm_id` GROUP BY，4 个窗口用 `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` 同时聚合
- 过滤条件：`WHERE shop_id = :shop_id AND order_date >= d30_start AND nm_id IS NOT NULL`
- `product_name` 取 `MAX(product_name)`（订单表内最新名称）
- 不分页，一次返回（受 WHERE 条件约束，结果最多为该店铺近30天出现过订单的 SKU 数）
- 默认按 `today_orders DESC` 排序（前端也可以再排）

#### 3. `GET /api/dashboard/shops/{shop_id}/products/{nm_id}/daily`

返回指定商品在指定日期之前 N 天的每日订单数。

**Query params:**
- `end_date`（必填，格式 YYYY-MM-DD，Moscow 日期）
- `days`（可选，默认 7，范围 1–31）

**Response:**
```json
{
  "daily": [
    {"date": "2026-04-14", "orders": 3},
    {"date": "2026-04-15", "orders": 5},
    {"date": "2026-04-16", "orders": 0}
  ]
}
```

**实现要点:**
- 权限校验：`shop_id` 不在 `get_accessible_shop_ids` 内返回 403
- 日期范围：`[end_date - days + 1, end_date]`（含两端）
- SQL：`GROUP BY order_date`，查出有订单的日期及订单数
- 对无订单的日期也要返回 `orders: 0`（Python 侧用完整日期序列补齐）
- 按日期升序返回

### 核心 SQL 表达式

```python
from sqlalchemy import func, case, cast, Date, text
from datetime import datetime, timezone, timedelta

_MSK_TZ = timezone(timedelta(hours=3))

# 订单日期（Moscow 时区）
order_date = cast(Order.created_at + text("interval '3 hours'"), Date)

# 时间窗口
msk_now = datetime.now(_MSK_TZ)
today = msk_now.date()
yesterday = today - timedelta(days=1)
d7_start = today - timedelta(days=6)   # 含今日共7天
d30_start = today - timedelta(days=29) # 含今日共30天

# 商品排行 SQL（示意）
query = (
    select(
        Order.nm_id,
        func.max(Order.product_name).label("product_name"),
        func.sum(case((order_date == today, 1), else_=0)).label("today_orders"),
        func.sum(case((order_date == yesterday, 1), else_=0)).label("yesterday_orders"),
        func.sum(case((order_date >= d7_start, 1), else_=0)).label("last_7d_orders"),
        func.count().label("last_30d_orders"),
    )
    .where(Order.shop_id == shop_id)
    .where(order_date >= d30_start)
    .where(Order.nm_id.isnot(None))
    .group_by(Order.nm_id)
    .order_by(text("today_orders DESC"))
)
```

## 前端实现

### 文件变更

| 文件 | 操作 |
|------|------|
| `frontend/src/views/Dashboard.vue` | 扩展：新增三级视图状态、店铺方块、商品排行表、商品每日详情 |

**不新增子组件**，因为当前 Dashboard.vue 规模可控，保持单文件便于整体维护。

### 视图状态

```js
const viewMode = ref('shops')        // 'shops' | 'products' | 'detail'
const currentShop = ref(null)        // { id, name }
const currentProduct = ref(null)     // { nm_id, name }

const shopCards = ref([])            // 店铺方块数据
const productList = ref([])          // 商品排行
const dailyData = ref([])            // 商品每日订单（累积，按日期升序）
const dailyEndDate = ref(null)       // 下次"查看更多"的 end_date（YYYY-MM-DD）
```

### 布局结构

```
原有: 统计卡片 + 近30天订单趋势图
─────────────────────────────────
【店铺看板】 + 面包屑

viewMode === 'shops':
  4 列网格的店铺方块（复用 ts-stat-card 样式）
  每块显示：店铺名 / 今日订单数 / 今日销售额 / 近30天销售额

viewMode === 'products':
  [← 返回]  店铺A · 商品销量排行
  el-table（20 条显示后滚动，列头 sortable，默认今日订单数降序）
  列：商品名 · 今日订单数 · 昨日订单数 · 近7天订单数 · 近30天订单数

viewMode === 'detail':
  [← 返回]  商品B · 近7天订单趋势
  ECharts 柱状图（日期轴 + 订单数）
  表格（两列：日期、订单数）
  [查看更多] 按钮
```

### 交互流程

1. **onMounted** → 调 `/api/dashboard/shops` → `shopCards = data.shops`
2. **点击店铺方块** → 设 `currentShop`，调 products 接口 → `viewMode = 'products'`
3. **点击面包屑/返回** → `viewMode = 'shops'`（不清空 shopCards，避免重复请求）
4. **点击商品行** → 设 `currentProduct`，`dailyEndDate = 今日`，调 daily 接口（days=7）→ 初始化 `dailyData`，`viewMode = 'detail'`
5. **点击"查看更多"** → `newEndDate = dailyData[0].date - 1 天`，调 daily 接口（end_date=newEndDate, days=7）→ 新数据 prepend 到 `dailyData`，更新 `dailyEndDate = newEndDate`
6. **详情内返回** → `viewMode = 'products'`（保留 productList，不重复请求）
7. **切换店铺/商品时**：清空 `dailyData`、`productList` 避免污染

### 竞态与错误处理

- 发 daily 请求前记录当前 `nm_id`，响应时校验 `currentProduct.nm_id` 仍等于该值才合并数据
- 接口 403 → ElMessage 提示"无权访问该店铺"，退回上一级
- 接口 500 → ElMessage 提示"加载失败，请重试"，保留当前视图

### 样式

- 店铺方块：复用 Dashboard 已有的 `ts-stat-card`（渐变背景卡片），每行 4 个，`el-row :gutter="16"`
- 面包屑：`el-breadcrumb` + `el-breadcrumb-item`
- 表格：`el-table` + `sortable="custom"` 或 `sortable=true`（前端排序，数据量小）
- 柱状图：复用 ECharts，沿用现有 theme

## 路由与菜单

无变更。Dashboard 主路由 `/dashboard` 保持不变，三级视图在页面内切换。

## 边界情况

| 场景 | 处理 |
|------|------|
| 店铺无订单数据 | 方块订单/销售额均为 0；点进去后 `products: []`，表格显示"暂无数据" |
| 商品某天无订单 | daily 接口用完整日期序列补 `orders: 0` |
| 用户快速切换商品导致竞态 | 响应合并前校验 `nm_id` |
| 越权访问店铺 | 后端返回 403，前端提示并返回上级 |
| `nm_id` 为 NULL | SQL 过滤掉 |
| 商品名称变动 | 用 `MAX(product_name)` 取最新 |
| `end_date` 超过今天 | 后端允许（会返回未来空数据），不强制校验 |

## 性能约束与后续演进

- 当前规模（店铺 ≤20、单店铺近30天订单 SKU ≤500）下实时聚合够用
- 若单店铺商品排行 SQL 耗时 >1s，可加索引 `idx_orders_shop_date (shop_id, created_at)` 或 `(shop_id, nm_id, created_at)`
- 若再不够用，下一步升级到预聚合表（方案 B），但本次不做

## 测试要点

**后端（pytest）:**
- 今日边界跨零点（Moscow 时区）
- 权限拒绝（非 accessible shop）
- 空数据店铺 / 空数据商品
- 跨月的近30天统计
- daily 接口日期补零

**前端（手动）:**
- 三级视图切换 + 面包屑返回
- "查看更多"累积不重复、日期连续
- 快速切换商品不污染数据
- 切换店铺不残留上一家的商品数据

## 验证方案

1. 后端语法检查：`python -c "import py_compile; py_compile.compile('backend/app/routers/dashboard.py')"`
2. 后端启动测试：`cd backend && uvicorn app.main:app --reload`
3. 手动验证：登录 ERP → Dashboard → 验证店铺方块数据 → 点击 → 验证排行 → 点击商品 → 验证每日图 → 点查看更多 → 验证追加
4. 权限验证：非管理员账号登录，确认只能看到自己被授权的店铺
