import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("WB_ERP_SECRET_KEY", "wb-erp-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

FERNET_KEY = os.environ.get("WB_ERP_FERNET_KEY", "wb-erp-fernet-key-must-be-32-bytes=")

DATABASE_URL = f"sqlite:///{BASE_DIR / 'wb_erp.db'}"

UPLOAD_DIR = BASE_DIR / "app" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SYNC_INTERVAL_MINUTES = 30
