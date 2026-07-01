"""GNS3 REST API client.

Mắt xích giao thức thứ nhất giữa runtime và hạ tầng mạng (mục 2.3, 2.4):
tạo/quản lý dự án, liệt kê và điều khiển node, quản lý liên kết.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class GNS3Client:
    def __init__(self, base_url: str | None = None, user: str | None = None, password: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.gns3_url).rstrip("/")
        auth = (user or settings.gns3_user, password or settings.gns3_password)
        self._client = httpx.Client(base_url=f"{self.base_url}/v2", auth=auth, timeout=15.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GNS3Client":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # --- Projects ---

    def list_projects(self) -> list[dict]:
        return self._client.get("/projects").raise_for_status().json()

    def get_project(self, project_id: str) -> dict:
        return self._client.get(f"/projects/{project_id}").raise_for_status().json()

    def create_project(self, name: str) -> dict:
        return self._client.post("/projects", json={"name": name}).raise_for_status().json()

    def find_project_by_name(self, name: str) -> dict | None:
        for project in self.list_projects():
            if project["name"] == name:
                return project
        return None

    # --- Templates (mẫu thiết bị đã đăng ký sẵn trên GNS3 server) ---

    def list_templates(self) -> list[dict]:
        return self._client.get("/templates").raise_for_status().json()

    def find_template_by_name(self, name: str) -> dict | None:
        for template in self.list_templates():
            if template["name"] == name:
                return template
        return None

    # --- Nodes ---

    def list_nodes(self, project_id: str) -> list[dict]:
        return self._client.get(f"/projects/{project_id}/nodes").raise_for_status().json()

    def get_node(self, project_id: str, node_id: str) -> dict:
        return self._client.get(f"/projects/{project_id}/nodes/{node_id}").raise_for_status().json()

    def find_node_by_name(self, project_id: str, name: str) -> dict | None:
        for node in self.list_nodes(project_id):
            if node["name"] == name:
                return node
        return None

    def create_node_from_template(
        self, project_id: str, template_id: str, name: str, x: int = 0, y: int = 0
    ) -> dict:
        return (
            self._client.post(
                f"/projects/{project_id}/templates/{template_id}",
                json={"name": name, "x": x, "y": y},
            )
            .raise_for_status()
            .json()
        )

    def start_node(self, project_id: str, node_id: str) -> dict:
        return self._client.post(f"/projects/{project_id}/nodes/{node_id}/start").raise_for_status().json()

    def stop_node(self, project_id: str, node_id: str) -> dict:
        return self._client.post(f"/projects/{project_id}/nodes/{node_id}/stop").raise_for_status().json()

    def reload_node(self, project_id: str, node_id: str) -> dict:
        return self._client.post(f"/projects/{project_id}/nodes/{node_id}/reload").raise_for_status().json()

    # --- Links ---

    def list_links(self, project_id: str) -> list[dict]:
        return self._client.get(f"/projects/{project_id}/links").raise_for_status().json()

    def get_link(self, project_id: str, link_id: str) -> dict:
        return self._client.get(f"/projects/{project_id}/links/{link_id}").raise_for_status().json()

    def create_link(
        self,
        project_id: str,
        node_a_id: str,
        port_a_number: int,
        node_b_id: str,
        port_b_number: int,
        adapter_number: int = 0,
    ) -> dict:
        payload = {
            "nodes": [
                {"node_id": node_a_id, "adapter_number": adapter_number, "port_number": port_a_number},
                {"node_id": node_b_id, "adapter_number": adapter_number, "port_number": port_b_number},
            ]
        }
        return self._client.post(f"/projects/{project_id}/links", json=payload).raise_for_status().json()

    # --- Composite / convenience ---

    def get_topology(self, project_id: str) -> dict:
        """Trả về danh sách node, liên kết và trạng thái - dùng cho tool get_topology()."""
        return {
            "nodes": self.list_nodes(project_id),
            "links": self.list_links(project_id),
        }
