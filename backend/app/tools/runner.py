"""Adapter: biến ToolExecutor (DB/GNS3/Netmiko thật) thành cổng ToolRunner
thuần mà app.agent_core mong đợi - ranh giới giữa lõi suy luận và hạ tầng thật.
"""

from __future__ import annotations

from typing import Any

from app.agent_core.types import ToolOutcome
from app.tools.executor import ToolExecutor


class ExecutorToolRunner:
    def __init__(self, executor: ToolExecutor) -> None:
        self._executor = executor

    def run(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        result = self._executor.execute(name, arguments)
        return ToolOutcome(name=result.name, arguments=result.arguments, output=result.output, ok=result.ok, error=result.error)
