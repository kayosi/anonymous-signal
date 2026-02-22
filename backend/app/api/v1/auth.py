"""
Authentication Module
=====================
JWT-based auth for analyst dashboard users only.
Report submitters NEVER authenticate.

Roles:
  - analyst: Read reports, view insights
  - senior_analyst: Read + acknowledge alerts
  - admin: Full access including user management
"""

from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.models import AnalystUser
from app.schemas.schemas import LoginRequest, TokenResponse

logger = structlog.get_logger(__name__)
router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def get_current_analyst(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AnalystUser:
    """Dependency: Validate JWT and return current analyst user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        select(AnalystUser).where(
            AnalystUser.username == username,
            AnalystUser.is_active == True,
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    return user


def require_role(*roles: str):
    """Role-based access control dependency factory."""
    async def role_checker(current_user: AnalystUser = Depends(get_current_analyst)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {roles}",
            )
        return current_user
    return role_checker


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Analyst dashboard login."""
    result = await db.execute(
        select(AnalystUser).where(
            AnalystUser.username == credentials.username,
            AnalystUser.is_active == True,
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
        logger.warning("failed_login_attempt", username=credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Update last login
    await db.execute(
        update(AnalystUser)
        .where(AnalystUser.id == user.id)
        .values(last_login=datetime.utcnow())
    )
    await db.commit()

    token = create_access_token({"sub": user.username, "role": user.role})
    logger.info("analyst_logged_in", username=user.username, role=user.role)

    return TokenResponse(
        access_token=token,
        role=user.role,
    )
