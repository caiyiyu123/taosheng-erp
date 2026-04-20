# Dashboard Shop Drilldown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Dashboard 的订单趋势图下方新增"店铺看板"三级下钻（店铺方块 → 商品销量排行 → 商品近N天订单）。

**Architecture:** 后端扩展现有 `/api/dashboard` 路由新增 3 个端点，实时 SQL 聚合（一条 SQL + CASE WHEN）。前端在 `Dashboard.vue` 中以 `viewMode` 状态切换三级视图，面包屑返回。

**Tech Stack:** FastAPI + SQLAlchemy (PostgreSQL prod / SQLite tests) + Vue 3 + Element Plus + ECharts。

---

## 关键适配（相对于 spec）

Spec 中的字段归属需按真实模型调整：
- `nm_id` → `OrderItem.wb_product_id`（字符串）
- `product_name` → `OrderItem.product_name`
- 销售额 → `Order.price_rub`（已归一化为 RUB，无需币种换算；响应不再返回 currency 字段）
- 日期聚合按现有 `DATABASE_URL.startswith("postgresql")` 分支兼容 SQLite

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `backend/app/routers/dashboard.py` | HTTP 端点 + SQL 聚合 | 新增 3 个路由函数 |
| `backend/tests/test_dashboard.py` | 端点测试 | 新增测试用例 |
| `frontend/src/views/Dashboard.vue` | 店铺看板 UI + 交互 | 扩展 template/script/style |

---

## Task 1: 后端店铺方块数据端点

**Files:**
- Modify: `backend/app/routers/dashboard.py`（在文件末尾追加）
- Test: `backend/tests/test_dashboard.py`（在文件末尾追加）

- [ ] **Step 1: 写失败测试 — 店铺方块基础用例**

在 `backend/tests/test_dashboard.py` 末尾追加：

```python
def test_dashboard_shops_returns_cards(client, db):
    token = _setup(client, db)
    resp = client.get("/api/dashboard/shops", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "shops" in data
    assert len(data["shops"]) == 1
    card = data["shops"][0]
    assert card["name"] == "店铺A"
    assert card["id"] > 0
    assert "today_orders" in card
    assert "today_sales" in card
    assert "last_30d_sales" in card


def test_dashboard_shops_includes_shops_without_orders(client, db):
    from app.models.shop import Shop
    from app.utils.security import encrypt_token
    token = _setup(client, db)
    empty_shop = Shop(name="空店铺", type="local", api_token=encrypt_token("t2"), is_active=True)
    db.add(empty_shop)
    db.commit()
    resp = client.get("/api/dashboard/shops", headers=_auth(token))
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["shops"]]
    assert "空店铺" in names
    empty = next(s for s in resp.json()["shops"] if s["name"] == "空店铺")
    assert empty["today_orders"] == 0
    assert empty["today_sales"] == 0
    assert empty["last_30d_sales"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

```
cd backend
pytest tests/test_dashboard.py::test_dashboard_shops_returns_cards -v
```

Expected: FAIL with 404（端点不存在）

- [ ] **Step 3: 实现端点**

在 `backend/app/routers/dashboard.py` 文件末尾追加：

```python
from app.models.shop import Shop


@router.get("/shops")
def dashboard_shops(
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("dashboard")),
):
    """返回当前用户可访问的店铺方块数据：今日订单/销售额、近30天销售额。"""
    from sqlalchemy import cast, Date, text, case
    from app.config import DATABASE_URL

    now_msk = datetime.now(_MSK_TZ)
    today = now_msk.date()
    d30_start = today - timedelta(days=29)

    # Moscow date 表达式（postgres/sqlite 兼容）
    if DATABASE_URL.startswith("postgresql"):
        order_date = cast(Order.created_at + text("interval '3 hours'"), Date)
    else:
        order_date = func.date(Order.created_at, '+3 hours')

    # 按 shop_id 聚合：今日订单/销售额、近30天销售额
    agg_q = db.query(
        Order.shop_id,
        func.sum(case((order_date == today, 1), else_=0)).label("today_orders"),
        func.sum(case((order_date == today, Order.price_rub), else_=0)).label("today_sales"),
        func.sum(case((order_date >= d30_start, Order.price_rub), else_=0)).label("last_30d_sales"),
    ).filter(order_date >= d30_start)
    if accessible_shops is not None:
        agg_q = agg_q.filter(Order.shop_id.in_(accessible_shops))
    agg_rows = agg_q.group_by(Order.shop_id).all()
    agg_map = {r.shop_id: r for r in agg_rows}

    # 拉所有可见店铺（没订单的也要返回）
    shop_q = db.query(Shop)
    if accessible_shops is not None:
        shop_q = shop_q.filter(Shop.id.in_(accessible_shops))
    shops = shop_q.order_by(Shop.id).all()

    result = []
    for s in shops:
        agg = agg_map.get(s.id)
        result.append({
            "id": s.id,
            "name": s.name,
            "today_orders": int(agg.today_orders) if agg else 0,
            "today_sales": float(agg.today_sales) if agg else 0.0,
            "last_30d_sales": float(agg.last_30d_sales) if agg else 0.0,
        })
    return {"shops": result}
```

- [ ] **Step 4: 运行测试确认通过**

```
pytest tests/test_dashboard.py::test_dashboard_shops_returns_cards tests/test_dashboard.py::test_dashboard_shops_includes_shops_without_orders -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```
git add backend/app/routers/dashboard.py backend/tests/test_dashboard.py
git commit -m "feat(dashboard): add /api/dashboard/shops endpoint for shop card data"
```

---

## Task 2: 后端商品销量排行端点

**Files:**
- Modify: `backend/app/routers/dashboard.py`
- Test: `backend/tests/test_dashboard.py`

- [ ] **Step 1: 写失败测试 — 商品排行**

在 `backend/tests/test_dashboard.py` 末尾追加：

```python
def test_shop_products_ranking(client, db):
    from app.models.shop import Shop
    from app.models.order import Order, OrderItem
    from app.models.user import User
    from app.utils.security import hash_password, encrypt_token

    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    shop = Shop(name="店铺R", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add_all([user, shop])
    db.commit()

    order1 = Order(wb_order_id="O1", shop_id=shop.id, order_type="FBS", status="pending", price_rub=100.0)
    order2 = Order(wb_order_id="O2", shop_id=shop.id, order_type="FBS", status="pending", price_rub=200.0)
    db.add_all([order1, order2])
    db.commit()
    db.add_all([
        OrderItem(order_id=order1.id, wb_product_id="111", product_name="商品甲", sku="SKU1", quantity=1, price=100.0),
        OrderItem(order_id=order2.id, wb_product_id="111", product_name="商品甲", sku="SKU1", quantity=1, price=200.0),
    ])
    db.commit()

    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    tok = resp.json()["access_token"]
    r = client.get(f"/api/dashboard/shops/{shop.id}/products", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert data["shop_id"] == shop.id
    assert data["shop_name"] == "店铺R"
    assert len(data["products"]) == 1
    p = data["products"][0]
    assert p["nm_id"] == "111"
    assert p["product_name"] == "商品甲"
    assert p["last_30d_orders"] == 2


def test_shop_products_forbidden_for_other_shop(client, db):
    from app.models.shop import Shop
    from app.models.user import User
    from app.utils.security import hash_password, encrypt_token

    shop_a = Shop(name="A", type="local", api_token=encrypt_token("ta"), is_active=True)
    shop_b = Shop(name="B", type="local", api_token=encrypt_token("tb"), is_active=True)
    db.add_all([shop_a, shop_b])
    db.commit()
    user = User(username="op", password_hash=hash_password("x"), role="operator", is_active=True)
    user.shops = [shop_a]
    db.add(user)
    db.commit()

    resp = client.post("/api/auth/login", data={"username": "op", "password": "x"})
    tok = resp.json()["access_token"]
    r = client.get(f"/api/dashboard/shops/{shop_b.id}/products", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败**

```
pytest tests/test_dashboard.py::test_shop_products_ranking -v
```

Expected: FAIL with 404

- [ ] **Step 3: 实现端点**

在 `backend/app/routers/dashboard.py` 文件末尾追加：

```python
from fastapi import HTTPException
from app.models.order import OrderItem


@router.get("/shops/{shop_id}/products")
def shop_products_ranking(
    shop_id: int,
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("dashboard")),
):
    """返回指定店铺商品销量排行（今日/昨日/近7天/近30天 订单数）。"""
    from sqlalchemy import cast, Date, text, case
    from app.config import DATABASE_URL

    # 权限校验
    if accessible_shops is not None and shop_id not in accessible_shops:
        raise HTTPException(status_code=403, detail="无权访问该店铺")

    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if shop is None:
        raise HTTPException(status_code=404, detail="店铺不存在")

    now_msk = datetime.now(_MSK_TZ)
    today = now_msk.date()
    yesterday = today - timedelta(days=1)
    d7_start = today - timedelta(days=6)
    d30_start = today - timedelta(days=29)

    if DATABASE_URL.startswith("postgresql"):
        order_date = cast(Order.created_at + text("interval '3 hours'"), Date)
    else:
        order_date = func.date(Order.created_at, '+3 hours')

    # 按 wb_product_id 聚合 4 个时间窗口
    q = (
        db.query(
            OrderItem.wb_product_id.label("nm_id"),
            func.max(OrderItem.product_name).label("product_name"),
            func.sum(case((order_date == today, 1), else_=0)).label("today_orders"),
            func.sum(case((order_date == yesterday, 1), else_=0)).label("yesterday_orders"),
            func.sum(case((order_date >= d7_start, 1), else_=0)).label("last_7d_orders"),
            func.count(OrderItem.id).label("last_30d_orders"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.shop_id == shop_id)
        .filter(order_date >= d30_start)
        .filter(OrderItem.wb_product_id.isnot(None))
        .filter(OrderItem.wb_product_id != "")
        .group_by(OrderItem.wb_product_id)
        .order_by(text("today_orders DESC"))
    )
    rows = q.all()

    products = [
        {
            "nm_id": r.nm_id,
            "product_name": r.product_name or "",
            "today_orders": int(r.today_orders),
            "yesterday_orders": int(r.yesterday_orders),
            "last_7d_orders": int(r.last_7d_orders),
            "last_30d_orders": int(r.last_30d_orders),
        }
        for r in rows
    ]

    return {
        "shop_id": shop.id,
        "shop_name": shop.name,
        "products": products,
    }
```

- [ ] **Step 4: 运行测试确认通过**

```
pytest tests/test_dashboard.py::test_shop_products_ranking tests/test_dashboard.py::test_shop_products_forbidden_for_other_shop -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```
git add backend/app/routers/dashboard.py backend/tests/test_dashboard.py
git commit -m "feat(dashboard): add shop products ranking endpoint with 4-window aggregation"
```

---

## Task 3: 后端商品每日订单端点

**Files:**
- Modify: `backend/app/routers/dashboard.py`
- Test: `backend/tests/test_dashboard.py`

- [ ] **Step 1: 写失败测试 — 每日订单**

在 `backend/tests/test_dashboard.py` 末尾追加：

```python
def test_product_daily_orders_fills_missing_dates(client, db):
    from datetime import datetime, timezone, timedelta
    from app.models.shop import Shop
    from app.models.order import Order, OrderItem
    from app.models.user import User
    from app.utils.security import hash_password, encrypt_token

    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    shop = Shop(name="SD", type="local", api_token=encrypt_token("t"), is_active=True)
    db.add_all([user, shop])
    db.commit()

    # Moscow 今日
    msk = timezone(timedelta(hours=3))
    today_msk = datetime.now(msk).date()
    # 做一个"今日"订单（UTC时间 = 莫斯科时间 - 3h）
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    order = Order(
        wb_order_id="OD1", shop_id=shop.id, order_type="FBS", status="pending",
        price_rub=50.0, created_at=now_utc_naive,
    )
    db.add(order)
    db.commit()
    db.add(OrderItem(order_id=order.id, wb_product_id="777", product_name="商品日", sku="K", quantity=1, price=50.0))
    db.commit()

    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    tok = resp.json()["access_token"]
    url = f"/api/dashboard/shops/{shop.id}/products/777/daily?end_date={today_msk.isoformat()}&days=7"
    r = client.get(url, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["daily"]) == 7
    # 日期升序，最后一天是 end_date
    assert data["daily"][-1]["date"] == today_msk.isoformat()
    # 最后一天 orders >= 1（刚插入的订单）
    assert data["daily"][-1]["orders"] >= 1
    # 其余天 orders = 0
    assert data["daily"][0]["orders"] == 0


def test_product_daily_forbidden_for_other_shop(client, db):
    from app.models.shop import Shop
    from app.models.user import User
    from app.utils.security import hash_password, encrypt_token

    shop_a = Shop(name="A", type="local", api_token=encrypt_token("ta"), is_active=True)
    shop_b = Shop(name="B", type="local", api_token=encrypt_token("tb"), is_active=True)
    db.add_all([shop_a, shop_b])
    db.commit()
    user = User(username="op2", password_hash=hash_password("x"), role="operator", is_active=True)
    user.shops = [shop_a]
    db.add(user)
    db.commit()

    resp = client.post("/api/auth/login", data={"username": "op2", "password": "x"})
    tok = resp.json()["access_token"]
    r = client.get(
        f"/api/dashboard/shops/{shop_b.id}/products/123/daily?end_date=2026-04-20&days=7",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败**

```
pytest tests/test_dashboard.py::test_product_daily_orders_fills_missing_dates -v
```

Expected: FAIL with 404

- [ ] **Step 3: 实现端点**

在 `backend/app/routers/dashboard.py` 文件末尾追加：

```python
from datetime import date as _date
from fastapi import Query


@router.get("/shops/{shop_id}/products/{nm_id}/daily")
def product_daily_orders(
    shop_id: int,
    nm_id: str,
    end_date: _date = Query(..., description="结束日期（含），Moscow 日期 YYYY-MM-DD"),
    days: int = Query(7, ge=1, le=31),
    db: Session = Depends(get_db),
    accessible_shops: list[int] | None = Depends(get_accessible_shop_ids),
    _=Depends(require_module("dashboard")),
):
    """返回商品在 [end_date - days + 1, end_date] 区间每日订单数（补零）。"""
    from sqlalchemy import cast, Date, text
    from app.config import DATABASE_URL

    if accessible_shops is not None and shop_id not in accessible_shops:
        raise HTTPException(status_code=403, detail="无权访问该店铺")

    start_date = end_date - timedelta(days=days - 1)

    if DATABASE_URL.startswith("postgresql"):
        order_date = cast(Order.created_at + text("interval '3 hours'"), Date)
    else:
        order_date = func.date(Order.created_at, '+3 hours')

    q = (
        db.query(order_date.label("d"), func.count(OrderItem.id).label("orders"))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.shop_id == shop_id)
        .filter(OrderItem.wb_product_id == nm_id)
        .filter(order_date >= start_date)
        .filter(order_date <= end_date)
        .group_by(order_date)
    )
    rows = q.all()
    daily_map = {str(r.d): int(r.orders) for r in rows}

    daily = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        daily.append({"date": d.isoformat(), "orders": daily_map.get(d.isoformat(), 0)})
    return {"daily": daily}
```

- [ ] **Step 4: 运行测试确认通过**

```
pytest tests/test_dashboard.py::test_product_daily_orders_fills_missing_dates tests/test_dashboard.py::test_product_daily_forbidden_for_other_shop -v
```

Expected: PASS

- [ ] **Step 5: 运行整个 dashboard 测试文件确认无回归**

```
pytest tests/test_dashboard.py -v
```

Expected: 所有测试 PASS

- [ ] **Step 6: 提交**

```
git add backend/app/routers/dashboard.py backend/tests/test_dashboard.py
git commit -m "feat(dashboard): add per-product daily orders endpoint with date backfill"
```

---

## Task 4: 前端 — 店铺方块视图

**Files:**
- Modify: `frontend/src/views/Dashboard.vue`

- [ ] **Step 1: 添加店铺方块状态和样式**

在 `<script setup>` 内 `stats` 定义之后追加：

```js
const viewMode = ref('shops')         // 'shops' | 'products' | 'detail'
const currentShop = ref(null)         // { id, name }
const currentProduct = ref(null)      // { nm_id, name }

const shopCards = ref([])
const productList = ref([])
const dailyData = ref([])             // [{ date, orders }]
const dailyEndDate = ref(null)        // 下次查看更多的 end_date
const loading = ref({ shops: false, products: false, daily: false })

async function fetchShopCards() {
  loading.value.shops = true
  try {
    const { data } = await api.get('/api/dashboard/shops')
    shopCards.value = data.shops
  } catch (e) {
    console.error('shops error', e)
    ElMessage.error('店铺数据加载失败')
  } finally {
    loading.value.shops = false
  }
}
```

- [ ] **Step 2: 在 onMounted 中调用 fetchShopCards**

找到现有 `onMounted(async () => { ... })`，在 `stats.value = data` 这行后追加：

```js
    await fetchShopCards()
```

修改后的 onMounted 完整样子：

```js
onMounted(async () => {
  try {
    const { data } = await api.get('/api/dashboard/stats')
    stats.value = data
    await fetchShopCards()
  } catch (e) {
    console.error('Dashboard stats error:', e)
    ElMessage.error('数据加载失败')
  }
})
```

- [ ] **Step 3: 在 template 末尾新增店铺看板区块（仅方块视图）**

找到 `<el-card class="ts-chart-card">...</el-card>` 这一块（近30天趋势图），在其结束标签 `</el-card>` 后面追加：

```html
    <!-- 店铺看板 -->
    <div class="ts-section-label" style="margin-top: 24px">店铺看板</div>

    <!-- 面包屑 -->
    <el-breadcrumb separator="/" class="ts-shop-breadcrumb">
      <el-breadcrumb-item>
        <a @click.prevent="goToShops" href="#">店铺总览</a>
      </el-breadcrumb-item>
      <el-breadcrumb-item v-if="viewMode !== 'shops' && currentShop">
        <a @click.prevent="goToProducts" href="#">{{ currentShop.name }}</a>
      </el-breadcrumb-item>
      <el-breadcrumb-item v-if="viewMode === 'detail' && currentProduct">
        {{ currentProduct.name }}
      </el-breadcrumb-item>
    </el-breadcrumb>

    <!-- 店铺方块 -->
    <el-row v-if="viewMode === 'shops'" :gutter="16" v-loading="loading.shops">
      <el-col :span="6" v-for="shop in shopCards" :key="shop.id">
        <div class="ts-stat-card ts-shop-card" @click="openShop(shop)">
          <div class="ts-shop-name">{{ shop.name }}</div>
          <div class="ts-shop-metric">
            <span class="ts-shop-metric-label">今日订单</span>
            <span class="ts-shop-metric-value">{{ shop.today_orders }}</span>
          </div>
          <div class="ts-shop-metric">
            <span class="ts-shop-metric-label">今日销售额</span>
            <span class="ts-shop-metric-value">₽{{ Math.round(shop.today_sales).toLocaleString() }}</span>
          </div>
          <div class="ts-shop-metric">
            <span class="ts-shop-metric-label">近30天销售额</span>
            <span class="ts-shop-metric-value">₽{{ Math.round(shop.last_30d_sales).toLocaleString() }}</span>
          </div>
          <div class="ts-stat-indicator ts-stat-blue"></div>
        </div>
      </el-col>
      <el-col v-if="!loading.shops && shopCards.length === 0" :span="24">
        <el-empty description="暂无店铺数据" />
      </el-col>
    </el-row>
```

- [ ] **Step 4: 添加 openShop/goToShops/goToProducts 导航函数**

在 `<script setup>` 中，`fetchShopCards` 函数之后追加：

```js
function goToShops() {
  viewMode.value = 'shops'
}

function goToProducts() {
  viewMode.value = 'products'
}

async function openShop(shop) {
  currentShop.value = { id: shop.id, name: shop.name }
  productList.value = []
  viewMode.value = 'products'
  // 下一步 Task 5 会实现 fetchProducts
}
```

- [ ] **Step 5: 添加样式**

在 `<style scoped>` 块末尾（`</style>` 前）追加：

```css
.ts-shop-breadcrumb {
  margin-bottom: 16px;
}
.ts-shop-breadcrumb a {
  color: var(--ts-text-muted);
  text-decoration: none;
}
.ts-shop-breadcrumb a:hover {
  color: var(--ts-text-heading);
}

.ts-shop-card {
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ts-shop-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--ts-text-heading);
  margin-bottom: 6px;
}
.ts-shop-metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}
.ts-shop-metric-label {
  color: var(--ts-text-muted);
}
.ts-shop-metric-value {
  font-weight: 600;
  color: var(--ts-text-heading);
}
```

- [ ] **Step 6: 手动验证前端**

启动前端 `cd frontend && npm run dev`，登录进 Dashboard，确认：
- 在订单趋势图下方看到"店铺看板"标题和面包屑
- 店铺方块显示：店铺名、今日订单、今日销售额、近30天销售额
- 鼠标悬停方块有 hover 效果
- 点击方块面包屑切到第二级（但商品表格尚未实现，这是 Task 5 的内容）

- [ ] **Step 7: 提交**

```
git add frontend/src/views/Dashboard.vue
git commit -m "feat(dashboard): add shop card grid with breadcrumb navigation"
```

---

## Task 5: 前端 — 商品销量排行视图

**Files:**
- Modify: `frontend/src/views/Dashboard.vue`

- [ ] **Step 1: 添加 fetchProducts 并在 openShop 中调用**

替换 Task 4 中定义的 `openShop` 函数为：

```js
async function openShop(shop) {
  currentShop.value = { id: shop.id, name: shop.name }
  productList.value = []
  viewMode.value = 'products'
  loading.value.products = true
  try {
    const { data } = await api.get(`/api/dashboard/shops/${shop.id}/products`)
    productList.value = data.products
  } catch (e) {
    const msg = e?.response?.status === 403 ? '无权访问该店铺' : '商品数据加载失败'
    ElMessage.error(msg)
    viewMode.value = 'shops'
  } finally {
    loading.value.products = false
  }
}
```

- [ ] **Step 2: 添加商品排行表格到 template**

在 Task 4 步骤 3 添加的店铺方块 `<el-row v-if="viewMode === 'shops'">...</el-row>` 块后面追加：

```html
    <!-- 商品销量排行 -->
    <div v-if="viewMode === 'products'" v-loading="loading.products">
      <el-table
        :data="productList"
        stripe
        max-height="560"
        default-sort="{ prop: 'today_orders', order: 'descending' }"
        @row-click="openProduct"
        style="cursor: pointer"
      >
        <el-table-column prop="product_name" label="商品名" min-width="260" show-overflow-tooltip />
        <el-table-column prop="today_orders" label="今日订单数" width="130" sortable align="right" />
        <el-table-column prop="yesterday_orders" label="昨日订单数" width="130" sortable align="right" />
        <el-table-column prop="last_7d_orders" label="近7天订单数" width="140" sortable align="right" />
        <el-table-column prop="last_30d_orders" label="近30天订单数" width="140" sortable align="right" />
      </el-table>
      <el-empty v-if="!loading.products && productList.length === 0" description="该店铺暂无商品订单数据" />
    </div>
```

- [ ] **Step 3: 添加 openProduct 占位（Task 6 实现完整逻辑）**

在 `<script setup>` 中，其他函数之后追加：

```js
function openProduct(row) {
  currentProduct.value = { nm_id: row.nm_id, name: row.product_name }
  viewMode.value = 'detail'
  // 下一步 Task 6 会实现每日数据加载
}
```

- [ ] **Step 4: 手动验证**

刷新前端，点击店铺方块 → 应看到商品排行表，默认按今日订单降序，点列头切换排序。点击商品行 → 切到 detail 视图（内容空白，下一任务实现）。
- 验证非管理员账号访问无权店铺时提示"无权访问"

- [ ] **Step 5: 提交**

```
git add frontend/src/views/Dashboard.vue
git commit -m "feat(dashboard): add shop products ranking table with sortable columns"
```

---

## Task 6: 前端 — 商品每日订单详情视图

**Files:**
- Modify: `frontend/src/views/Dashboard.vue`

- [ ] **Step 1: 引入 BarChart 到 ECharts 注册**

找到文件顶部：

```js
import { LineChart } from 'echarts/charts'
```

改为：

```js
import { LineChart, BarChart } from 'echarts/charts'
```

并更新 `use([...])` 调用：

```js
use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent])
```

- [ ] **Step 2: 替换 openProduct 为完整逻辑**

替换 Task 5 步骤 3 添加的 `openProduct` 为：

```js
async function openProduct(row) {
  currentProduct.value = { nm_id: row.nm_id, name: row.product_name }
  viewMode.value = 'detail'
  dailyData.value = []
  // Moscow 今日作为首次 end_date
  const mskNow = new Date(Date.now() + 3 * 60 * 60 * 1000 - new Date().getTimezoneOffset() * 60 * 1000)
  const today = mskNow.toISOString().slice(0, 10)
  dailyEndDate.value = today
  await loadDaily(row.nm_id, today, 7, false)
}

async function loadDaily(nmId, endDate, days, prepend) {
  loading.value.daily = true
  try {
    const { data } = await api.get(
      `/api/dashboard/shops/${currentShop.value.id}/products/${nmId}/daily`,
      { params: { end_date: endDate, days } },
    )
    // 竞态保护：响应回来时确认当前商品没变
    if (!currentProduct.value || currentProduct.value.nm_id !== nmId) return
    if (prepend) {
      dailyData.value = [...data.daily, ...dailyData.value]
    } else {
      dailyData.value = data.daily
    }
  } catch (e) {
    const msg = e?.response?.status === 403 ? '无权访问该店铺' : '每日数据加载失败'
    ElMessage.error(msg)
  } finally {
    loading.value.daily = false
  }
}

async function loadMore() {
  if (!dailyData.value.length) return
  // 往前再加 7 天：新 end_date = 当前最早日期 - 1 天
  const earliest = dailyData.value[0].date
  const d = new Date(earliest + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() - 1)
  const newEndDate = d.toISOString().slice(0, 10)
  dailyEndDate.value = newEndDate
  await loadDaily(currentProduct.value.nm_id, newEndDate, 7, true)
}

const dailyChartOption = computed(() => {
  const dates = dailyData.value.map(d => d.date.slice(5))
  const orders = dailyData.value.map(d => d.orders)
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 30, bottom: 40, top: 20 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
      axisLabel: { color: '#94a3b8' },
    },
    series: [{
      name: '订单数',
      type: 'bar',
      data: orders,
      itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 32,
    }],
  }
})
```

- [ ] **Step 3: 添加商品详情视图到 template**

在 Task 5 步骤 2 追加的商品排行块后面继续追加：

```html
    <!-- 商品每日详情 -->
    <div v-if="viewMode === 'detail'" v-loading="loading.daily">
      <el-card class="ts-chart-card">
        <template #header>
          <span class="ts-chart-title">{{ currentProduct?.name }} · 每日订单数</span>
        </template>
        <v-chart :option="dailyChartOption" style="height: 280px" autoresize />
      </el-card>

      <el-table :data="[...dailyData].reverse()" stripe style="margin-top: 16px" max-height="320">
        <el-table-column prop="date" label="日期" width="180" />
        <el-table-column prop="orders" label="订单数" align="right" />
      </el-table>

      <div style="text-align: center; margin-top: 16px">
        <el-button type="primary" plain @click="loadMore" :loading="loading.daily">
          查看更多（+7天）
        </el-button>
      </div>
    </div>
```

- [ ] **Step 4: 手动验证完整流程**

刷新前端：
1. Dashboard → 店铺方块可见
2. 点击店铺 → 商品排行表显示
3. 点击商品 → 柱状图 + 表格显示近7天数据
4. 点"查看更多" → 柱状图变宽，表格增加7行（日期连续不重复），面包屑可以回到上级
5. 反复点击"查看更多"直至加载完所有历史数据（应无重复）
6. 面包屑"店铺总览"/店铺名 返回上级视图后数据保留（不重新请求）

- [ ] **Step 5: 提交**

```
git add frontend/src/views/Dashboard.vue
git commit -m "feat(dashboard): add product daily orders chart + table with load-more"
```

---

## Task 7: 集成验证

**Files:** 无改动，仅验证

- [ ] **Step 1: 运行全量后端测试**

```
cd backend
pytest -v
```

Expected: 所有测试 PASS（不应有回归）

- [ ] **Step 2: 启动生产式环境测试**

```
cd backend && uvicorn app.main:app --reload
```

另一终端：

```
cd frontend && npm run dev
```

在浏览器中走完：
- 管理员视角：三级下钻流程
- 非管理员（只授权部分店铺）：确认看不到未授权店铺；强行访问 URL 接口返回 403

- [ ] **Step 3: 验证权限边界**

使用 curl 测试：

```
# 以 operator 角色的 token（仅授权 shop_id=1）访问 shop_id=2：
curl -H "Authorization: Bearer <OP_TOKEN>" http://localhost:8000/api/dashboard/shops/2/products
```

Expected: 403 `{"detail":"无权访问该店铺"}`

- [ ] **Step 4: 可选 — 最终统合提交（如前面未逐任务提交或有微调）**

若前面 6 个任务已按步骤提交，本步跳过。否则：

```
git status
git diff
git add -A
git commit -m "feat(dashboard): integrate shop drilldown three-level view"
```

---

## Self-Review 结果

**1. Spec 覆盖检查：**
- ✅ 店铺方块端点（spec 1.1）→ Task 1
- ✅ 商品排行端点（spec 1.2）→ Task 2
- ✅ 每日订单端点（spec 1.3）→ Task 3
- ✅ 视图状态 viewMode（spec 2.1）→ Task 4 步骤 1
- ✅ 布局 + 面包屑（spec 2.2）→ Task 4 步骤 3
- ✅ 交互流程 1-7（spec 2.3）→ Task 4/5/6
- ✅ 核心 SQL（spec 3.1）→ Task 2/3 的实现步骤
- ✅ 边界情况表（spec 3.2）→ 测试用例覆盖 + 实现中处理
- ✅ 权限 403（spec 边界）→ Task 2 步骤 1 `test_shop_products_forbidden_for_other_shop`
- ✅ 每日补零（spec 3.2）→ Task 3 步骤 1 `test_product_daily_orders_fills_missing_dates`
- ✅ 竞态保护（spec 2.4）→ Task 6 步骤 2 `loadDaily` 内 nm_id 校验
- ✅ 手动测试（spec 验证方案）→ Task 7

**2. 占位符扫描：** 无 TBD/TODO。所有代码步骤都有完整代码块。

**3. 类型一致性：**
- `nm_id` 全程为字符串（`OrderItem.wb_product_id` 是 String）— 后端/前端/URL 都按字符串处理 ✅
- `loading.value.shops / products / daily` — Task 4 步骤 1 定义后 Task 5/6 复用 ✅
- `currentShop = { id, name }`、`currentProduct = { nm_id, name }` — Task 4/5/6 字段名一致 ✅
- `dailyData: [{ date, orders }]`、`dailyEndDate: string` — Task 4 声明 Task 6 使用 ✅
- `shopCards: [{ id, name, today_orders, today_sales, last_30d_sales }]` — 与 Task 1 后端响应一致 ✅
- `productList: [{ nm_id, product_name, today_orders, yesterday_orders, last_7d_orders, last_30d_orders }]` — 与 Task 2 后端响应一致 ✅

检查通过，可执行。
