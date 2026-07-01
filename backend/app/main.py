import asyncio
import queue
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, devices, incidents, security, topology, websocket
from app.api.websocket import manager
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.events import event_queue
from app.monitoring.collector import run_collector_loop
from app.security.syslog_listener import run_syslog_listener

settings = get_settings()


async def _drain_event_queue(stop_event: asyncio.Event) -> None:
    """Tiêu thụ hàng đợi sự kiện (app.core.events) và phát qua WebSocket /ws/events."""
    while not stop_event.is_set():
        try:
            event_type, payload = await asyncio.to_thread(event_queue.get, True, 1.0)
        except queue.Empty:
            continue
        await manager.broadcast(event_type, payload)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Ghi chú: dùng Base.metadata.create_all() cho phát triển nhanh ở quy mô phòng lab;
    # dùng `alembic upgrade head` (xem backend/alembic) để quản lý schema production.
    Base.metadata.create_all(bind=engine)

    stop_event = asyncio.Event()
    background_tasks = [
        asyncio.create_task(run_collector_loop(SessionLocal, stop_event)),
        asyncio.create_task(run_syslog_listener(stop_event)),
        asyncio.create_task(_drain_event_queue(stop_event)),
    ]
    try:
        yield
    finally:
        stop_event.set()
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)


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
