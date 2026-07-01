from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import User, UserRole
from app.schemas.schemas import TokenOut, UserCreate, UserOut

router = APIRouter()


@router.post("/auth/register", response_model=UserOut)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter_by(username=payload.username).first() is not None:
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")
    user = User(
        username=payload.username,
        role=UserRole(payload.role) if payload.role else UserRole.engineer,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/login", response_model=TokenOut)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(User).filter_by(username=form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")
    token = create_access_token(subject=user.username, role=user.role.value)
    return TokenOut(access_token=token)
