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

    # --- Nodes ---

    def list_nodes(self, project_id: str) -> list[dict]:
        return self._client.get(f"/projects/{project_id}/nodes").raise_for_status().json()

    def get_node(self, project_id: str, node_id: str) -> dict:
        return self._client.get(f"/projects/{project_id}/nodes/{node_id}").raise_for_status().json()

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

    # --- Composite / convenience ---

    def get_topology(self, project_id: str) -> dict:
        """Trả về danh sách node, liên kết và trạng thái - dùng cho tool get_topology()."""
        return {
            "nodes": self.list_nodes(project_id),
            "links": self.list_links(project_id),
        }
