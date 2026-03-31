from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import UPLOAD_DIR
from app.database import Base, engine
import app.models  # noqa: F401
from app.routers import auth, users, shops

Base.metadata.create_all(bind=engine)

app = FastAPI(title="WB-ERP", description="Wildberries 订单管理系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(shops.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
