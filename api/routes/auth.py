"""
Authentication routes.

POST /auth/register  — create account
POST /auth/login     — get access + refresh tokens
POST /auth/refresh   — exchange refresh token for new access token
GET  /auth/me        — return current user info
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.logger import get_logger
from api.models.base import get_db
from api.models.user import User
from api.services.email import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
log = get_logger(__name__)

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
_VERIFICATION_CODE_TTL_MINUTES = 15


# ── Schemas ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    tier: str
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RefreshRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=14)).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_verification_code(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt(rounds=14)).decode()


def _verify_verification_code(code: str, hashed: str) -> bool:
    return bcrypt.checkpw(code.encode(), hashed.encode())


def _create_token(subject: str, expires_delta: timedelta, token_type: str = "access") -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "exp": expire, "type": token_type}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _create_access_token(user_id: uuid.UUID) -> str:
    return _create_token(
        str(user_id),
        timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "access",
    )


def _create_refresh_token(user_id: uuid.UUID) -> str:
    return _create_token(
        str(user_id),
        timedelta(days=settings.jwt_refresh_token_expire_days),
        "refresh",
    )


async def get_current_user(
    token: str = Depends(_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise credentials_exc
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exc
    return user


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    verification_code = _generate_verification_code()
    verification_expires = datetime.now(timezone.utc) + timedelta(
        minutes=_VERIFICATION_CODE_TTL_MINUTES
    )

    user = User(
        email=req.email,
        hashed_password=_hash_password(req.password),
        is_verified=False,
        verification_token=_hash_verification_code(verification_code),
        verification_expires=verification_expires,
    )
    db.add(user)
    await db.flush()  # get user.id before commit
    send_verification_email(user.email, verification_code)

    return TokenResponse(
        access_token=_create_access_token(user.id),
        refresh_token=_create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if user is None or not _verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    return TokenResponse(
        access_token=_create_access_token(user.id),
        refresh_token=_create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
    )
    try:
        payload = jwt.decode(
            req.refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != "refresh":
            raise credentials_exc
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exc

    return TokenResponse(
        access_token=_create_access_token(user.id),
        refresh_token=_create_refresh_token(user.id),
    )


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    req: VerifyEmailRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if current_user.is_verified:
        return current_user

    expires = current_user.verification_expires
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if (
        current_user.verification_token is None
        or expires is None
        or expires < datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code expired or unavailable.",
        )

    if not _verify_verification_code(req.code, current_user.verification_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    current_user.is_verified = True
    current_user.verification_token = None
    current_user.verification_expires = None
    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if current_user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified.")

    verification_code = _generate_verification_code()
    current_user.verification_token = _hash_verification_code(verification_code)
    current_user.verification_expires = datetime.now(timezone.utc) + timedelta(
        minutes=_VERIFICATION_CODE_TTL_MINUTES
    )
    await db.flush()
    send_verification_email(current_user.email, verification_code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    req: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    # Always return 204 — never reveal whether an email is registered.
    if user and user.is_active:
        reset_code = _generate_verification_code()
        user.verification_token = _hash_verification_code(reset_code)
        user.verification_expires = datetime.now(timezone.utc) + timedelta(
            minutes=_VERIFICATION_CODE_TTL_MINUTES
        )
        await db.flush()
        send_password_reset_email(user.email, reset_code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reset-password", response_model=UserResponse)
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    # Find user whose reset code matches (brute-force safe: bcrypt check + expiry)
    # We require the user to pass their email too so we can look them up without
    # a plaintext token stored in the DB.
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Use POST /auth/reset-password-with-email instead.",
    )


class ResetPasswordWithEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/reset-password-with-email", response_model=UserResponse)
async def reset_password_with_email(
    req: ResetPasswordWithEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    invalid_exc = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset code.",
    )
    if user is None or not user.is_active:
        raise invalid_exc

    expires = user.verification_expires
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if (
        user.verification_token is None
        or expires is None
        or expires < datetime.now(timezone.utc)
    ):
        raise invalid_exc

    if not _verify_verification_code(req.code, user.verification_token):
        raise invalid_exc

    user.hashed_password = _hash_password(req.new_password)
    user.verification_token = None
    user.verification_expires = None
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
