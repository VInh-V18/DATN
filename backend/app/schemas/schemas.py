from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class InterfaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str
    ip_address: str | None = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    node_type: str
    role: str
    management_address: str | None = None
    gns3_node_id: str | None = None
    interfaces: list[InterfaceOut] = []


class TopologyLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    port_a_id: str
    port_b_id: str
    status: str


class TopologyOut(BaseModel):
    devices: list[DeviceOut]
    links: list[TopologyLinkOut]


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime
    description: str
    root_cause: str | None = None
    status: str
    device_ids: list[str] = []
    resolved_at: datetime | None = None


class ActionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    tool: str
    parameters: dict[str, Any]
    result: dict[str, Any]
    timestamp: datetime


class SecurityAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime
    source_ip: str
    attack_type: str
    severity: str
    status: str
    attack_techniques: list[str] = []


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tool_calls: list[dict[str, Any]] = []
    requires_confirmation: bool = False
    pending_action: dict[str, Any] | None = None


class ApprovalRequest(BaseModel):
    approved: bool
    approver: str | None = None
    comment: str | None = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
