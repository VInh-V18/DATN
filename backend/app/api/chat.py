from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_llm, get_tool_executor
from app.copilot.copilot import Copilot
from app.core.database import get_db
from app.llm.client import LLMClient
from app.models.models import ChatSession, User, UserRole
from app.schemas.schemas import ChatRequest, ChatResponse
from app.tools.executor import ToolExecutor

router = APIRouter()

DEFAULT_USERNAME = "default_engineer"


def _get_or_create_default_user(db: Session) -> User:
    user = db.query(User).filter_by(username=DEFAULT_USERNAME).first()
    if user is None:
        user = User(username=DEFAULT_USERNAME, role=UserRole.engineer, hashed_password="")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _get_or_create_session(db: Session, session_id: str | None) -> ChatSession:
    if session_id:
        session = db.get(ChatSession, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên hội thoại")
        return session
    user = _get_or_create_default_user(db)
    session = ChatSession(user_id=user.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    executor: ToolExecutor = Depends(get_tool_executor),
    llm: LLMClient = Depends(get_llm),
) -> ChatResponse:
    """Bảng 3.2: POST /api/chat - gửi câu hỏi tới Copilot và nhận phản hồi."""
    session = _get_or_create_session(db, request.session_id)
    copilot = Copilot(db=db, executor=executor, llm=llm)
    reply = copilot.ask(session, request.message)
    return ChatResponse(
        session_id=session.id,
        reply=reply.text,
        tool_calls=reply.tool_calls,
        requires_confirmation=reply.requires_confirmation,
        pending_action=reply.pending_action,
    )
