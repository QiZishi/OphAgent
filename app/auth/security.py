# app/auth/security.py
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session

from app.core.config import settings
from app.db.crud import get_session_token, get_user_by_id
from app.db.database import get_session
from app.db.models import User

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

security = HTTPBearer(auto_error=False)
cookie_scheme = APIKeyCookie(name="access_token", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def get_user_from_token(token: str, session: Session) -> User | None:
    try:
        token_value = token.split(" ")[1] if " " in token else token
        payload = jwt.decode(
            token_value,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: str = payload.get("sub")
        jti: str = payload.get("jti")
        if user_id is None or jti is None:
            return None
        if get_session_token(session, jti, int(user_id)) is None:
            return None
        user = get_user_by_id(session, user_id=int(user_id))
        return user
    except (JWTError, ValueError, IndexError):
        return None


def get_token_id(token: str) -> str | None:
    try:
        token_value = token.split(" ")[1] if " " in token else token
        payload = jwt.decode(
            token_value,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload.get("jti")
    except (JWTError, ValueError, IndexError):
        return None


async def get_current_user(
    session: Session = Depends(get_session),
    token: str | None = Depends(cookie_scheme),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    user = None
    if token:
        user = get_user_from_token(token, session)
    
    if user is None and credentials:
        user = get_user_from_token(credentials.credentials, session)
    
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_user_from_ws(
    websocket: WebSocket,
    session: Session
) -> User | None:
    token = websocket.query_params.get("token")
    if token:
        user = get_user_from_token(token, session)
        if user:
            return user
    
    token = websocket.cookies.get("access_token")
    if token:
        user = get_user_from_token(token, session)
        if user:
            return user
    
    return None
