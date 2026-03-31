# Wildberries ERP 订单管理系统 — 设计文档

## 概述

本地运行的 Wildberries 订单管理 ERP 系统，支持多店铺（跨境+本土）、多用户权限管理，通过 WB 官方 API 自动抓取订单数据，提供订单管理、商品管理、财务统计、库存管理等功能。

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue 3 + Element Plus | SPA，中文友好 UI 组件库 |
| 状态管理 | Pinia | Vue 3 官方推荐 |
| 图表 | ECharts | 数据可视化 |
| 后端 | FastAPI (Python) | 异步高性能 REST API |
| 数据库 | SQLite | 本地零配置，后续可迁移 PostgreSQL |
| 认证 | JWT (24h 过期) | 无状态认证 |
| 定时任务 | APScheduler | 定时抓取 WB API 数据 |
| 加密 | Fernet | API Token 对称加密存储 |
| 密码 | bcrypt | 密码哈希 |

## 用户角色与权限

| 角色 | 权限 |
|------|------|
| 管理员 (admin) | 全部权限：管理用户、店铺、商品，查看所有数据 |
| 操作员 (operator) | 查看订单、处理发货、管理库存、SKU关联 |
| 查看者 (viewer) | 只读权限：查看订单、财务、库存数据 |

## 页面清单

1. **登录页** — JWT 认证登录
2. **数据看板** — 首页，关键指标卡片（今日订单、销售额、待发货、低库存预警）+ 销售趋势图 + 最近订单
3. **订单列表** — FBS/FBW 标签切换，支持按店铺、状态、日期筛选搜索
4. **订单详情** — 商品信息、物流状态时间线
5. **商品管理** — 系统商品 CRUD，含图片、SKU、采购价、尺寸重量
6. **财务统计** — 销售额、佣金、物流费、利润报表，按店铺/时间段聚合
7. **库存管理** — FBS/FBW 库存分开展示，低库存预警
8. **店铺管理** — 添加/编辑/删除店铺，配置 API Token，入口进入 SKU 关联页
9. **SKU 关联页** — 查看某店铺所有 WB 商品，每行输入框关联系统商品 SKU
10. **用户管理** — 用户增删改、角色分配（仅管理员）
11. **系统设置** — 同步频率等配置

## 页面布局

- **顶部栏**：系统名称、全局店铺筛选下拉、当前用户信息
- **左侧边栏**：深色背景导航菜单，包含所有页面入口，订单管理下有 FBS/FBW 子菜单
- **主内容区**：浅灰背景，承载各页面内容

## 数据模型

### User（用户）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| username | VARCHAR UNIQUE | 用户名 |
| password_hash | VARCHAR | bcrypt 哈希密码 |
| role | VARCHAR | admin / operator / viewer |
| is_active | BOOLEAN | 是否启用 |
| created_at | DATETIME | 创建时间 |

### Shop（店铺）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | VARCHAR | 店铺名称 |
| type | VARCHAR | cross_border（跨境）/ local（本土） |
| api_token | VARCHAR | Fernet 加密存储的 WB API Token |
| is_active | BOOLEAN | 是否启用 |
| last_sync_at | DATETIME | 最后同步时间 |
| created_at | DATETIME | 创建时间 |

### Product（系统商品）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| sku | VARCHAR UNIQUE | 系统 SKU，唯一标识 |
| name | VARCHAR | 商品名称 |
| image | VARCHAR | 商品图片路径 |
| purchase_price | DECIMAL | 采购价 |
| weight | DECIMAL | 重量 (g) |
| length | DECIMAL | 长 (cm) |
| width | DECIMAL | 宽 (cm) |
| height | DECIMAL | 高 (cm) |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

用户手动添加管理。同一商品可通过 SkuMapping 关联到多个店铺。

### SkuMapping（SKU 关联）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| shop_id | INTEGER FK → Shop | 所属店铺 |
| shop_sku | VARCHAR | 店铺产品 SKU（WB 侧） |
| product_id | INTEGER FK → Product | 关联的系统商品（可为空，未关联状态） |
| wb_product_name | VARCHAR | WB 商品名称 |
| wb_barcode | VARCHAR | WB 条码 |
| created_at | DATETIME | 创建时间 |

唯一约束：(shop_id, shop_sku)。一个系统商品可对应多个店铺 SKU。

### Order（订单）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| wb_order_id | VARCHAR UNIQUE | WB 原始订单 ID |
| shop_id | INTEGER FK → Shop | 所属店铺 |
| order_type | VARCHAR | FBS / FBW |
| status | VARCHAR | 系统统一状态 |
| total_price | DECIMAL | 订单总金额 |
| currency | VARCHAR | 货币（默认 RUB） |
| customer_name | VARCHAR | 客户名称 |
| delivery_address | TEXT | 配送地址 |
| warehouse_name | VARCHAR | 仓库名称 |
| created_at | DATETIME | 订单创建时间 |
| updated_at | DATETIME | 更新时间 |

订单统一状态映射：待发货、已发货、配送中、已完成、已取消、已退货。WB 原始状态保留在 OrderStatusLog 中。

### OrderItem（订单商品）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| order_id | INTEGER FK → Order | 所属订单 |
| wb_product_id | VARCHAR | WB 商品 ID |
| product_name | VARCHAR | 商品名称 |
| sku | VARCHAR | 店铺 SKU |
| barcode | VARCHAR | 条码 |
| quantity | INTEGER | 数量 |
| price | DECIMAL | 售价 |
| commission | DECIMAL | WB 佣金 |
| logistics_cost | DECIMAL | 物流费用 |

### OrderStatusLog（订单状态日志）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| order_id | INTEGER FK → Order | 所属订单 |
| status | VARCHAR | 系统统一状态 |
| wb_status | VARCHAR | WB 原始状态 |
| changed_at | DATETIME | 状态变更时间 |
| note | TEXT | 备注 |

### Inventory（库存）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| shop_id | INTEGER FK → Shop | 所属店铺 |
| wb_product_id | VARCHAR | WB 商品 ID |
| product_name | VARCHAR | 商品名称 |
| sku | VARCHAR | 店铺 SKU |
| barcode | VARCHAR | 条码 |
| stock_fbs | INTEGER | FBS 自有仓库存 |
| stock_fbw | INTEGER | FBW WB 仓库存 |
| low_stock_threshold | INTEGER | 低库存预警阈值 |
| updated_at | DATETIME | 更新时间 |

## API 同步策略

- **自动同步**：APScheduler 每 30 分钟执行一次，遍历所有启用的店铺，增量拉取上次同步后的新订单和库存数据
- **手动同步**：店铺管理页支持手动触发单店铺同步
- **增量策略**：以 last_sync_at 为基准，只拉取新增/变更数据
- **错误处理**：API 调用失败时记录日志，不影响其他店铺同步

## 财务计算逻辑

- **销售额**：SUM(OrderItem.price * OrderItem.quantity)
- **佣金**：SUM(OrderItem.commission)
- **物流费**：SUM(OrderItem.logistics_cost)
- **利润**：销售额 - 采购成本 - 佣金 - 物流费
- **采购成本**：通过 SKU 关联查找 Product.purchase_price，乘以数量
- 支持按店铺、时间段、订单类型（FBS/FBW）聚合统计

## 安全设计

- API Token 使用 Fernet 对称加密存储于数据库
- 用户密码使用 bcrypt 哈希
- JWT Token 过期时间 24 小时
- RBAC 权限控制：API 层面校验用户角色

## 项目结构

```
wb-erp/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置
│   │   ├── database.py          # SQLite 连接
│   │   ├── models/              # SQLAlchemy 模型
│   │   ├── schemas/             # Pydantic 请求/响应模型
│   │   ├── routers/             # API 路由
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── shops.py
│   │   │   ├── products.py
│   │   │   ├── orders.py
│   │   │   ├── inventory.py
│   │   │   ├── finance.py
│   │   │   └── dashboard.py
│   │   ├── services/            # 业务逻辑
│   │   │   ├── wb_api.py        # WB API 对接
│   │   │   ├── sync.py          # 数据同步
│   │   │   └── scheduler.py     # 定时任务
│   │   ├── utils/               # 工具函数
│   │   │   ├── security.py      # JWT + bcrypt + Fernet
│   │   │   └── deps.py          # 依赖注入（权限校验等）
│   │   └── uploads/             # 商品图片存储
│   ├── requirements.txt
│   └── alembic/                 # 数据库迁移（可选）
├── frontend/
│   ├── src/
│   │   ├── views/               # 页面组件
│   │   ├── components/          # 通用组件
│   │   ├── stores/              # Pinia 状态
│   │   ├── api/                 # API 调用封装
│   │   ├── router/              # Vue Router
│   │   └── utils/               # 工具函数
│   ├── package.json
│   └── vite.config.js
└── docs/
```

## 部署方式

本地运行：
- 后端：`uvicorn app.main:app --reload`
- 前端：`npm run dev`（开发）或 `npm run build` 后由 FastAPI 提供静态文件（生产）
