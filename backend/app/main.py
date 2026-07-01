from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, devices, incidents, security, topology, websocket
from app.core.config import get_settings
from app.core.database import Base, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Ghi chú: dùng Base.metadata.create_all() cho phát triển nhanh ở quy mô phòng lab;
    # dùng `alembic upgrade head` (xem backend/alembic) để quản lý schema production.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(topology.router, prefix="/api", tags=["topology"])
app.include_router(devices.router, prefix="/api", tags=["devices"])
app.include_router(incidents.router, prefix="/api", tags=["incidents"])
app.include_router(security.router, prefix="/api", tags=["security"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(websocket.router, tags=["websocket"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
