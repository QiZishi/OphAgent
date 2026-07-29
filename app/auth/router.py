# app/auth/router.py
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from app.auth.schemas import PasswordChange, Token, UserCreate, UserLogin, UserResponse
from app.auth.security import (
    create_access_token,
    get_current_user,
    get_password_hash,
    get_token_id,
    verify_password,
)
from app.core.config import settings
from app.db.crud import (
    create_session_token,
    create_user,
    get_user_by_username,
    revoke_session_token,
    revoke_user_sessions,
)
from app.db.database import get_session
from app.db.models import User

router = APIRouter()
_failed_logins: dict[str, deque[float]] = defaultdict(deque)
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_FAILURES = 5


def _issue_session(user: User, session: Session) -> str:
    jti = uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    create_session_token(session, jti, int(user.id), expires_at)
    return create_access_token(
        data={
            "sub": str(user.id),
            "jti": jti,
        },
    )


def _set_session_cookie(response: Response, access_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=f"bearer {access_token}",
        httponly=True,
        samesite="strict",
        secure=settings.ENVIRONMENT == "production",
        path="/",
    )


@router.post("/register", response_model=Token)
async def register(user_data: UserCreate, response: Response, session: Session = Depends(get_session)):
    existing_user = get_user_by_username(session, user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名不可用"
        )
    
    hashed_password = get_password_hash(user_data.password)
    user = create_user(session, user_data.username, hashed_password)
    
    access_token = _issue_session(user, session)
    _set_session_cookie(response, access_token)
    
    return Token(access_token=access_token, token_type="bearer")


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, response: Response, session: Session = Depends(get_session)):
    now = time.monotonic()
    failures = _failed_logins[user_data.username]
    while failures and now - failures[0] > _LOGIN_WINDOW_SECONDS:
        failures.popleft()
    if len(failures) >= _LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请稍后再试",
        )
    user = get_user_by_username(session, user_data.username)
    if not user or not verify_password(user_data.password, user.hashed_password):
        failures.append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    failures.clear()
    access_token = _issue_session(user, session)
    _set_session_cookie(response, access_token)
    
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        created_at=current_user.created_at.isoformat(),
        role=current_user.role,
    )


@router.post("/password", status_code=204)
async def change_password(
    payload: PasswordChange,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码不正确",
        )
    current_user.hashed_password = get_password_hash(payload.new_password)
    session.add(current_user)
    session.commit()
    revoke_user_sessions(session, int(current_user.id))
    response.delete_cookie("access_token", path="/")


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    raw_token = request.cookies.get("access_token")
    if raw_token:
        jti = get_token_id(raw_token)
        if jti:
            revoke_session_token(session, jti)
    response.delete_cookie("access_token", path="/")
