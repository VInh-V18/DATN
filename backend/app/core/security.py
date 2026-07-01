"""Xác thực và phân quyền người dùng - yêu cầu phi chức năng "Bảo mật" (mục 3.1).

Mật khẩu được băm bằng bcrypt; phiên đăng nhập dùng JWT ngắn hạn để bảo vệ các
endpoint có khả năng thay đổi hệ thống (phê duyệt hành động rủi ro cao, UC4).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


class TokenPayload:
    def __init__(self, username: str, role: str) -> None:
        self.username = username
        self.role = role


def decode_access_token(token: str) -> TokenPayload | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    username = payload.get("sub")
    role = payload.get("role")
    if username is None:
        return None
    return TokenPayload(username=username, role=role or "viewer")
