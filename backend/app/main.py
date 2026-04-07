import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import UPLOAD_DIR, CORS_ORIGINS
from app.database import Base, engine
import app.models  # noqa: F401
from app.routers import auth, users, shops, products, sku_mappings, orders, inventory, finance, dashboard, ads, shop_products
from app.services.scheduler import start_scheduler, stop_scheduler

Base.metadata.create_all(bind=engine)

# Create default admin user if no users exist
try:
    from app.database import SessionLocal
    from app.models.user import User
    from app.utils.security import hash_password
    db = SessionLocal()
    if db.query(User).count() == 0:
        default_password = os.environ.get("ADMIN_DEFAULT_PASSWORD", "admin123")
        admin = User(
            username="admin",
            password_hash=hash_password(default_password),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print("[Init] Default admin user created: admin / ********")
    db.close()
except Exception as e:
    print(f"[Init] Warning: {e}")

# Lightweight schema migration: add new columns to existing tables
try:
    with engine.connect() as conn:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        if "shops" in inspector.get_table_names():
            shop_cols = {c["name"]: c for c in inspector.get_columns("shops")}
            if "api_token" in shop_cols and "varchar" in str(shop_cols["api_token"]["type"]).lower():
                conn.execute(text("ALTER TABLE shops ALTER COLUMN api_token TYPE TEXT"))
                conn.commit()
        if "sku_mappings" in inspector.get_table_names():
            sku_cols = {c["name"] for c in inspector.get_columns("sku_mappings")}
            if "wb_nm_id" not in sku_cols:
                conn.execute(text("ALTER TABLE sku_mappings ADD COLUMN wb_nm_id VARCHAR(100)"))
            if "wb_image_url" not in sku_cols:
                conn.execute(text("ALTER TABLE sku_mappings ADD COLUMN wb_image_url VARCHAR(500) DEFAULT ''"))
            conn.commit()
        if "shop_products" in inspector.get_table_names():
            sp_cols = {c["name"] for c in inspector.get_columns("shop_products")}
            if "price" not in sp_cols:
                conn.execute(text("ALTER TABLE shop_products ADD COLUMN price FLOAT DEFAULT 0.0"))
            if "discount" not in sp_cols:
                conn.execute(text("ALTER TABLE shop_products ADD COLUMN discount INTEGER DEFAULT 0"))
            if "currency" not in sp_cols:
                conn.execute(text("ALTER TABLE shop_products ADD COLUMN currency VARCHAR(10) DEFAULT 'RUB'"))
            if "price_rub" not in sp_cols:
                conn.execute(text("ALTER TABLE shop_products ADD COLUMN price_rub FLOAT DEFAULT 0.0"))
            conn.commit()
except Exception as e:
    print(f"[Migration] Warning: {e}")


@asynccontextmanager
async def lifespan(app):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="TS-ERP", description="TS-ERP - Wildberries 订单管理系统", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(shops.router)
app.include_router(products.router)
app.include_router(sku_mappings.router)
app.include_router(orders.router)
app.include_router(inventory.router)
app.include_router(finance.router)
app.include_router(dashboard.router)
app.include_router(ads.router)
app.include_router(shop_products.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
