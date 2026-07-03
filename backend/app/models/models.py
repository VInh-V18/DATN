import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DeviceRole(str, enum.Enum):
    router = "router"
    switch = "switch"
    host = "host"
    iot = "iot"
    server = "server"
    attacker = "attacker"


class LinkStatus(str, enum.Enum):
    up = "up"
    down = "down"
    flapping = "flapping"


class IncidentStatus(str, enum.Enum):
    open = "open"
    diagnosing = "diagnosing"
    awaiting_approval = "awaiting_approval"
    remediating = "remediating"
    resolved = "resolved"
    failed = "failed"


class Severity(str, enum.Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class UserRole(str, enum.Enum):
    admin = "admin"
    engineer = "engineer"
    viewer = "viewer"


class TraceSubjectType(str, enum.Enum):
    incident = "incident"
    security_alert = "security_alert"


# --- Nhóm hạ tầng và thiết bị ---


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    node_type: Mapped[str] = mapped_column(String, nullable=False)  # loại thiết bị GNS3 (dynamips, docker, iou...)
    role: Mapped[DeviceRole] = mapped_column(Enum(DeviceRole), default=DeviceRole.router)
    management_address: Mapped[str | None] = mapped_column(String, nullable=True)
    gns3_node_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    credentials_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    interfaces: Mapped[list["Interface"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    anomalies: Mapped[list["Anomaly"]] = relationship(back_populates="device", cascade="all, delete-orphan")


class Interface(Base):
    __tablename__ = "interfaces"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[LinkStatus] = mapped_column(Enum(LinkStatus), default=LinkStatus.down)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="interfaces")


class TopologyLink(Base):
    __tablename__ = "topology_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    port_a_id: Mapped[str] = mapped_column(ForeignKey("interfaces.id"), nullable=False)
    port_b_id: Mapped[str] = mapped_column(ForeignKey("interfaces.id"), nullable=False)
    status: Mapped[LinkStatus] = mapped_column(Enum(LinkStatus), default=LinkStatus.down)

    port_a: Mapped["Interface"] = relationship(foreign_keys=[port_a_id])
    port_b: Mapped["Interface"] = relationship(foreign_keys=[port_b_id])


# --- Nhóm giám sát và sự cố ---
# Lưu ý: số liệu time-series (metrics) được lưu trong InfluxDB theo thiết kế mục 3.5,
# không có bảng SQL riêng — xem app/monitoring/influx_client.py


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), default=Severity.info)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True)


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    features: Mapped[dict] = mapped_column(JSON, default=dict)

    device: Mapped["Device"] = relationship(back_populates="anomalies")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[IncidentStatus] = mapped_column(Enum(IncidentStatus), default=IncidentStatus.open)
    device_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pending_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    action_logs: Mapped[list["ActionLog"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    tool: Mapped[str] = mapped_column(String, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    incident: Mapped["Incident"] = relationship(back_populates="action_logs")


class AgentTrace(Base):
    """Nhật ký suy luận (audit trail) - ghi lại từng bước quan sát mà agent thực
    hiện trong pha Think (ReAct) trước khi đề xuất/thực thi hành động cuối
    cùng, phục vụ yêu cầu "khả năng kiểm toán" (mục 3.1). Dùng chung cho cả
    SelfHealingAgent (subject_type=incident) và SecurityAgent
    (subject_type=security_alert) - không dùng khóa ngoại cứng tới hai bảng
    khác nhau để tránh ràng buộc quan hệ đa hình phức tạp; subject_id được
    ứng dụng tự đối chiếu theo subject_type.
    """

    __tablename__ = "agent_traces"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    subject_type: Mapped[TraceSubjectType] = mapped_column(Enum(TraceSubjectType), nullable=False)
    subject_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tool: Mapped[str] = mapped_column(String, nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# --- Nhóm an ninh và hội thoại ---


class SecurityAlert(Base):
    __tablename__ = "security_alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_ip: Mapped[str] = mapped_column(String, nullable=False)
    attack_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), default=Severity.medium)
    status: Mapped[str] = mapped_column(String, default="detected")
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    attack_mappings: Mapped[list["AttackMapping"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class AttackMapping(Base):
    __tablename__ = "attack_mappings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    alert_id: Mapped[str] = mapped_column(ForeignKey("security_alerts.id"), nullable=False)
    technique_id: Mapped[str] = mapped_column(String, nullable=False)  # ví dụ T1046
    technique_name: Mapped[str] = mapped_column(String, nullable=False)
    tactic: Mapped[str] = mapped_column(String, nullable=False)

    alert: Mapped["SecurityAlert"] = relationship(back_populates="attack_mappings")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.engineer)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)

    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    pending_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "user" | "assistant" | "tool"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
