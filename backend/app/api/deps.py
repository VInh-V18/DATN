from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import TokenPayload, decode_access_token
from app.gns3.client import GNS3Client
from app.llm.client import LLMClient, get_llm_client
from app.tools.executor import ToolExecutor

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


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
    return ToolExecutor(db=db, gns3_client=gns3, project_id=project_id, dry_run=settings.agent_dry_run)


def get_llm() -> LLMClient:
    return get_llm_client()


def get_current_user(token: str | None = Depends(_oauth2_scheme)) -> TokenPayload:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Chưa đăng nhập hoặc token không hợp lệ",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise unauthorized
    payload = decode_access_token(token)
    if payload is None:
        raise unauthorized
    return payload


def require_approver(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """UC4: chỉ kỹ sư/admin mới được phê duyệt hành động rủi ro cao."""
    if user.role not in ("engineer", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không đủ quyền phê duyệt")
    return user
