from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.gns3.client import GNS3Client
from app.llm.client import LLMClient, get_llm_client
from app.tools.executor import ToolExecutor


def get_gns3_client() -> Generator[GNS3Client, None, None]:
    client = GNS3Client()
    try:
        yield client
    finally:
        client.close()


def get_tool_executor(
    db: Session = Depends(get_db),
    gns3: GNS3Client = Depends(get_gns3_client),
) -> ToolExecutor:
    settings = get_settings()
    project_id = settings.gns3_project_id or ""
    return ToolExecutor(db=db, gns3_client=gns3, project_id=project_id)


def get_llm() -> LLMClient:
    return get_llm_client()
