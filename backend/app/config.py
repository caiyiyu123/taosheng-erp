import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("WB_ERP_SECRET_KEY", "wb-erp-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

FERNET_KEY = os.environ.get("WB_ERP_FERNET_KEY", "wb-erp-fernet-key-must-be-32-bytes=")

# Database: use DATABASE_URL env var (Railway provides this for PostgreSQL)
# Falls back to local SQLite for development
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'wb_erp.db'}")
# Railway PostgreSQL uses "postgres://" but SQLAlchemy needs "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

UPLOAD_DIR = BASE_DIR / "app" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SYNC_INTERVAL_MINUTES = 30

# Production environment safety check
if "postgresql" in DATABASE_URL:
    if SECRET_KEY == "wb-erp-secret-key-change-in-production":
        print("[WARNING] Production detected but SECRET_KEY is using default value! Set WB_ERP_SECRET_KEY env var.")
    if FERNET_KEY == "wb-erp-fernet-key-must-be-32-bytes=":
        print("[WARNING] Production detected but FERNET_KEY is using default value! Set WB_ERP_FERNET_KEY env var.")

# CORS: allowed origins from env (comma-separated) or default to localhost
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
