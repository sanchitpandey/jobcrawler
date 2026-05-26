"""
Authentication routes.

POST /auth/register                   — create account (generic response, no enum leak)
POST /auth/login                      — get access + refresh tokens
POST /auth/refresh                    — rotate refresh token, return new pair
POST /auth/logout                     — revoke caller's refresh token
POST /auth/verify-email               — confirm signup with 6-digit code
POST /auth/resend-verification        — issue a new verification code
POST /auth/forgot-password            — email a reset code (always 204)
POST /auth/reset-password-with-email  — consume reset code, set new password
GET  /auth/me                         — return current user info
GET  /auth/me/export                  — download a JSON archive of all user data (GDPR Art. 15 / DPDP §11)
DELETE /auth/me                       — hard-delete the account and all user data (GDPR Art. 17 / DPDP §12)
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import InvalidTokenError as JWTError
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.logger import get_logger
from api.middleware import auth_throttle
from api.models.base import get_db
from api.models.user import User
from api.services import refresh_tokens
from api.services.account_data import delete_user_and_data, export_user_data
from api.services.email import send_password_reset_email, send_verification_email
from api.services.password_policy import assert_password_acceptable

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
log = get_logger(__name__)

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
_VERIFICATION_CODE_TTL_MINUTES = 15
_MAX_CODE_ATTEMPTS = 5
_MAX_FAILED_LOGINS = 10
_LOCKOUT_MINUTES = 15
REFRESH_COOKIE_NAME = "jc_refresh"
CSRF_COOKIE_NAME = "jc_csrf"  # readable by JS; double-submit token (audit N5)
CSRF_HEADER_NAME = "X-CSRF-Token"

# Constant-time decoy used when an email is unknown — prevents login timing oracle.
_DUMMY_HASH = bcrypt.hashpw(b"jobcrawler-decoy-password", bcrypt.gensalt(rounds=12)).decode()


# ── Schemas ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)


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


class GenericResponse(BaseModel):
    status: str = "ok"


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


def _create_access_token(user_id: uuid.UUID | str) -> str:
    # Audit fix L1: include iss + aud + jti so tokens are bound to this
    # deployment and audience, and each token carries a unique id (jti) so
    # future per-token revocation lists can name specific access tokens.
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expire,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": secrets.token_urlsafe(16),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


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
        # Audit fix L1: enforce iss + aud + exp on decode. PyJWT raises
        # InvalidIssuerError / InvalidAudienceError / ExpiredSignatureError
        # — all of which inherit from InvalidTokenError (our JWTError alias).
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iss", "aud", "sub", "type"]},
        )
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


async def require_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Gate dependency for sensitive endpoints (billing, applications, LLM).
    Audit fix #16: ``is_verified`` was being set but never enforced.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return current_user


def _set_refresh_cookie(response: Response, raw_refresh: str) -> None:
    """
    Browsers (web app) get the refresh token as an httpOnly cookie so XSS in
    a React render path cannot read it. Native callers (extension, mobile)
    ignore the cookie and use the JSON body — both pathways stay supported.

    Audit N5 (CSRF defense in depth): alongside the httpOnly refresh cookie
    we set a non-httpOnly ``jc_csrf`` cookie carrying a random token. The web
    client reads that cookie and echoes it as ``X-CSRF-Token`` on
    ``/auth/refresh`` and ``/auth/logout``. The cookie-bearing refresh path
    enforces a match; the body-bearing path (extension) bypasses CSRF since
    the attacker would need to know the refresh token itself.
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 3600,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
        path="/auth",  # only sent to /auth/* endpoints
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=secrets.token_urlsafe(32),
        max_age=settings.jwt_refresh_token_expire_days * 24 * 3600,
        httponly=False,  # JS must be able to read it to echo in the header
        secure=settings.app_env == "production",
        samesite="strict",
        path="/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/auth")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/auth")


def _enforce_csrf(
    used_cookie: bool, csrf_cookie: str | None, csrf_header: str | None
) -> None:
    """
    Audit N5: double-submit CSRF check on cookie-driven /auth/refresh and
    /auth/logout calls. ``used_cookie`` is True when the refresh token came
    from the ``jc_refresh`` cookie (vs. the JSON body). Body-driven calls
    skip CSRF — the attacker would need the refresh token itself, which the
    extension keeps in chrome.storage.session.
    """
    if not used_cookie:
        return
    if (
        not csrf_cookie
        or not csrf_header
        or not secrets.compare_digest(csrf_cookie, csrf_header)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid.",
        )


async def _issue_token_pair(
    db: AsyncSession,
    user_id: str,
    response: Response,
) -> TokenResponse:
    raw_refresh, _, _ = await refresh_tokens.issue(db, user_id)
    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(
        access_token=_create_access_token(user_id),
        refresh_token=raw_refresh,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_202_ACCEPTED, response_model=GenericResponse)
async def register(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GenericResponse:
    """
    Create an account. Returns a generic 202 whether or not the email already
    exists — registration completion is signalled through the verification email,
    not the HTTP response (fix #9: user-enumeration).
    """
    # Per-IP cap (5/hr) + per-email cap (3/hr) — fix N7 prevents mail-bombing.
    await auth_throttle.enforce(request, "register", key=req.email)
    # Defense in depth: 12-char floor + breach-list check (fix #13).
    assert_password_acceptable(req.password)

    existing = await db.execute(select(User).where(User.email == req.email))
    user = existing.scalar_one_or_none()
    if user is not None:
        # Don't reveal existence. If the account is unverified, resend the code
        # so a legitimate re-attempt still works; otherwise silently no-op.
        if not user.is_verified:
            code = _generate_verification_code()
            user.verification_token = _hash_verification_code(code)
            user.verification_expires = datetime.now(timezone.utc) + timedelta(
                minutes=_VERIFICATION_CODE_TTL_MINUTES
            )
            user.verification_attempts = 0
            await db.flush()
            send_verification_email(user.email, code)
        else:
            # Audit N10: the verified-already branch otherwise skips both the
            # bcrypt password hash AND the SMTP send that the new-account branch
            # below performs. Burn an equivalent bcrypt cost on the input so a
            # timing-side-channel attacker cannot tell verified-existing apart
            # from new-registration. The result is discarded.
            _hash_password(req.password)
        return GenericResponse(status="pending_verification")

    code = _generate_verification_code()
    new_user = User(
        email=req.email,
        hashed_password=_hash_password(req.password),
        is_verified=False,
        verification_token=_hash_verification_code(code),
        verification_expires=datetime.now(timezone.utc) + timedelta(
            minutes=_VERIFICATION_CODE_TTL_MINUTES
        ),
    )
    db.add(new_user)
    await db.flush()
    send_verification_email(new_user.email, code)
    return GenericResponse(status="pending_verification")


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # Per-IP + per-email throttle
    await auth_throttle.enforce(request, "login", key=req.email)

    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None:
        # Run a bcrypt verify against a fixed decoy so non-existent emails
        # consume the same CPU as existing ones (fix #10: timing oracle).
        bcrypt.checkpw(req.password.encode(), _DUMMY_HASH.encode())
        raise invalid_exc

    # Temporary lockout window
    lockout_until = _aware(user.lockout_until)
    if lockout_until and lockout_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked. Try again later.",
            headers={"Retry-After": str(int((lockout_until - datetime.now(timezone.utc)).total_seconds()))},
        )

    if not _verify_password(req.password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= _MAX_FAILED_LOGINS:
            user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
        await db.commit()
        raise invalid_exc

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    user.failed_login_attempts = 0
    user.lockout_until = None
    await db.flush()
    return await _issue_token_pair(db, user.id, response)


class RefreshRequestOptional(BaseModel):
    """`/auth/refresh` accepts the token from the cookie OR the JSON body.
    Web clients use the cookie (httpOnly); the extension passes JSON.
    """
    refresh_token: str | None = None


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    body: RefreshRequestOptional | None = None,
    jc_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    jc_csrf: str | None = Cookie(default=None, alias=CSRF_COOKIE_NAME),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER_NAME),
) -> TokenResponse:
    await auth_throttle.enforce(request, "login")  # share login IP bucket

    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
    )
    body_token = body.refresh_token if body else None
    raw = body_token or jc_refresh
    if not raw:
        raise invalid_exc
    # Audit N5: cookie-driven refreshes must echo the CSRF token in the header.
    _enforce_csrf(used_cookie=body_token is None, csrf_cookie=jc_csrf, csrf_header=csrf_header)

    rotated = await refresh_tokens.rotate(db, raw)
    if rotated is None:
        # Burn any stale cookie so the browser stops resending it.
        _clear_refresh_cookie(response)
        raise invalid_exc
    new_refresh, user_id = rotated

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        _clear_refresh_cookie(response)
        raise invalid_exc

    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(
        access_token=_create_access_token(user.id),
        refresh_token=new_refresh,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    body: RefreshRequestOptional | None = None,
    jc_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    jc_csrf: str | None = Cookie(default=None, alias=CSRF_COOKIE_NAME),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER_NAME),
) -> Response:
    """Revoke the caller's refresh token. Idempotent. Clears the cookie."""
    body_token = body.refresh_token if body else None
    raw = body_token or jc_refresh
    # Audit N5: cookie-driven logout must echo the CSRF token in the header.
    _enforce_csrf(used_cookie=body_token is None and jc_refresh is not None,
                  csrf_cookie=jc_csrf, csrf_header=csrf_header)
    if raw:
        await refresh_tokens.revoke(db, raw)
    _clear_refresh_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    req: VerifyEmailRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    await auth_throttle.enforce(request, "verify", key=current_user.id)

    if current_user.is_verified:
        return current_user

    expires = _aware(current_user.verification_expires)
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
        current_user.verification_attempts = (current_user.verification_attempts or 0) + 1
        if current_user.verification_attempts >= _MAX_CODE_ATTEMPTS:
            # Burn the code — user has to request a new one.
            current_user.verification_token = None
            current_user.verification_expires = None
            current_user.verification_attempts = 0
        # Commit explicitly: the subsequent raise would otherwise trigger
        # a request-scope rollback and we'd lose the brute-force counter.
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    current_user.is_verified = True
    current_user.verification_token = None
    current_user.verification_expires = None
    current_user.verification_attempts = 0
    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await auth_throttle.enforce(request, "verify", key=current_user.id)

    if current_user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified.")

    verification_code = _generate_verification_code()
    current_user.verification_token = _hash_verification_code(verification_code)
    current_user.verification_expires = datetime.now(timezone.utc) + timedelta(
        minutes=_VERIFICATION_CODE_TTL_MINUTES
    )
    current_user.verification_attempts = 0
    await db.flush()
    send_verification_email(current_user.email, verification_code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=12, max_length=128)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await auth_throttle.enforce(request, "forgot", key=req.email)

    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    # Always return 204 — never reveal whether an email is registered.
    if user and user.is_active:
        reset_code = _generate_verification_code()
        user.verification_token = _hash_verification_code(reset_code)
        user.verification_expires = datetime.now(timezone.utc) + timedelta(
            minutes=_VERIFICATION_CODE_TTL_MINUTES
        )
        user.verification_attempts = 0
        await db.flush()
        send_password_reset_email(user.email, reset_code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reset-password", response_model=UserResponse)
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Use POST /auth/reset-password-with-email instead.",
    )


class ResetPasswordWithEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=12, max_length=128)


@router.post("/reset-password-with-email", response_model=UserResponse)
async def reset_password_with_email(
    req: ResetPasswordWithEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    await auth_throttle.enforce(request, "reset", key=req.email)
    assert_password_acceptable(req.new_password)

    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    invalid_exc = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset code.",
    )
    if user is None or not user.is_active:
        # Match the rough cost of the success path to avoid timing leaks.
        bcrypt.checkpw(b"x", _DUMMY_HASH.encode())
        raise invalid_exc

    expires = _aware(user.verification_expires)
    if (
        user.verification_token is None
        or expires is None
        or expires < datetime.now(timezone.utc)
    ):
        raise invalid_exc

    if not _verify_verification_code(req.code, user.verification_token):
        user.verification_attempts = (user.verification_attempts or 0) + 1
        if user.verification_attempts >= _MAX_CODE_ATTEMPTS:
            user.verification_token = None
            user.verification_expires = None
            user.verification_attempts = 0
        await db.commit()
        raise invalid_exc

    user.hashed_password = _hash_password(req.new_password)
    user.verification_token = None
    user.verification_expires = None
    user.verification_attempts = 0
    # All existing sessions are now stale.
    await refresh_tokens.revoke_all_for_user(db, user.id)
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


# ── Data subject rights (GDPR Art. 15/17, India DPDP §11/§12) ─────────────────

# Re-derived locally to avoid importing from api.routes.profiles (which imports
# get_current_user from this module — would create a circular import).
from pathlib import Path as _Path  # noqa: E402

_UPLOAD_DIR = _Path(__file__).resolve().parents[2] / "uploads"


class DeleteAccountRequest(BaseModel):
    """Body for DELETE /auth/me.

    ``password`` reverification stops a stolen access token from wiping the
    account — the attacker would also need the user's password. ``confirmation``
    is a typed-by-hand sentinel that prevents accidental destructive calls from
    a client bug or curl-the-wrong-method.
    """
    password: str = Field(..., min_length=1, max_length=128)
    confirmation: str = Field(..., description="Must equal 'DELETE MY ACCOUNT'.")


@router.get("/me/export")
async def export_my_data(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return a JSON archive of every row the user owns.

    Implements GDPR Art. 15 (right of access) and India DPDP §11 (right to
    access information about personal data). Available to any authenticated
    user — including ``is_verified=False`` — because a half-onboarded user
    still has the right to see what we hold on them.
    """
    await auth_throttle.enforce(request, "account_destructive", key=current_user.id)
    archive = await export_user_data(current_user, db)
    filename = f"jobcrawler-export-{current_user.id}.json"
    return JSONResponse(
        content=archive,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    req: DeleteAccountRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Hard-delete the account and every row of user data.

    Implements GDPR Art. 17 (right to erasure) and India DPDP §12 (right to
    correction and erasure). Razorpay retains payment records on their side
    for tax compliance; see ``api/services/account_data.py`` for the cascade
    map and the legal-retention rationale.

    CSRF posture: this endpoint authenticates via the Bearer access token in
    the Authorization header, not via the ``jc_refresh`` cookie — so the
    Authorization header itself is the CSRF defence (cross-site fetch cannot
    attach a custom Authorization header without preflight, which our CORS
    config does not whitelist for arbitrary origins). The web client + the
    extension both use Bearer, so there is no cookie-driven variant to guard.

    Defence in depth:
      * password reverification — stolen access token alone cannot wipe the account
      * ``confirmation`` sentinel — prevents accidental client-bug deletion
      * per-user + per-IP throttle on the ``account_destructive`` bucket
      * all refresh tokens revoked before commit, refresh + CSRF cookies cleared
    """
    await auth_throttle.enforce(request, "account_destructive", key=current_user.id)

    if req.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation phrase missing or incorrect.",
        )

    if not _verify_password(req.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password reverification failed.",
        )

    await delete_user_and_data(current_user, db, _UPLOAD_DIR)

    # Clear the web client's cookies on the way out. The body-bearing extension
    # flow has no cookies; this is a no-op for it.
    _clear_refresh_cookie(response)
    log.info("account deleted", extra={"user_id": current_user.id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
