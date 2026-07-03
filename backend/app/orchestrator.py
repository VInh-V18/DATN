"""Orchestrator - điều phối kiến trúc đa tác tử (multi-agent).

Trước đây không có gì tự động giao một sự cố mới cho SelfHealingAgent xử lý:
lớp Giám sát (collector + tương quan sự kiện, đóng vai "MonitorAgent") chỉ tạo
bản ghi `incidents` với trạng thái "open" rồi dừng lại - agent chỉ thực sự
chạy khi có người gọi `POST /api/incidents/{id}/approve`. Orchestrator lấp
khoảng trống đó: ngay khi MonitorAgent xác định một sự cố (mới hoặc vừa được
gộp thêm thiết bị) vẫn đang ở trạng thái "open", nó giao việc cho
SelfHealingAgent xử lý ngay lập tức - đúng tinh thần "tự vận hành" của đề tài.

Việc giao việc chạy trong một luồng riêng (`asyncio.to_thread`) vì cả gọi LLM
lẫn phiên SSH/Netmiko đều là I/O đồng bộ, có thể mất vài giây - không được
chặn vòng lặp sự kiện chính của FastAPI (nơi còn phải phục vụ HTTP/WebSocket).
"""

from __future__ import annotations

import asyncio
import logging

from app.agent.self_healing import SelfHealingAgent
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.gns3.client import GNS3Client
from app.llm.client import get_llm_client
from app.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)


class Orchestrator:
    """Giao sự cố cho SelfHealingAgent (và, trong tương lai, các agent chuyên
    biệt khác) - ranh giới duy nhất giữa MonitorAgent (lớp Giám sát) và lớp
    Tự khắc phục."""

    def dispatch_incident_sync(self, incident_id: str) -> None:
        """Chạy đồng bộ - gọi từ thread pool qua `dispatch_incident()`, hoặc
        trực tiếp trong ngữ cảnh đồng bộ (ví dụ script/test)."""
        settings = get_settings()
        db = SessionLocal()
        try:
            with GNS3Client() as gns3:
                executor = ToolExecutor(
                    db=db, gns3_client=gns3, project_id=settings.gns3_project_id or "", dry_run=settings.agent_dry_run
                )
                agent = SelfHealingAgent(db=db, executor=executor, llm=get_llm_client())
                agent.tu_khac_phuc(incident_id)
        except Exception:
            logger.exception("Orchestrator: lỗi khi giao sự cố %s cho SelfHealingAgent", incident_id)
        finally:
            db.close()

    async def dispatch_incident(self, incident_id: str) -> None:
        await asyncio.to_thread(self.dispatch_incident_sync, incident_id)


orchestrator = Orchestrator()
