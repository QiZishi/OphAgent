# app/auth/router.py
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlmodel import Session
from app.db.database import get_session
from app.db.crud import create_user, get_user_by_username
from app.auth.schemas import UserCreate, UserLogin, Token, UserResponse
from app.auth.security import verify_password, get_password_hash, create_access_token, get_current_user
from app.db.models import User

router = APIRouter()

@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, session: Session = Depends(get_session)):
    """用户注册"""
    # 检查用户名是否已存在
    existing_user = get_user_by_username(session, user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # 创建新用户
    hashed_password = get_password_hash(user_data.password)
    user = create_user(session, user_data.username, hashed_password)
    
    return UserResponse(
        id=user.id,
        username=user.username,
        created_at=user.created_at.isoformat()
    )

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, response: Response, session: Session = Depends(get_session)):
    """用户登录"""
    user = get_user_by_username(session, user_data.username)
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    
    response.set_cookie(
        key="access_token",
        value=f"bearer {access_token}",
        httponly=True,
        samesite="strict",
        secure=False, # 在生产环境中应设为 True
        path="/"
    )
    
    return Token(access_token=access_token, token_type="bearer")
