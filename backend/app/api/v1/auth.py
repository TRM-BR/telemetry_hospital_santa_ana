"""
/api/v1/auth — Login, cadastro, recuperação de senha e dados do usuário autenticado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, or_, select, update

from app.api.deps import CurrentUser, DbDep
from app.db.models.auth_log import AuthLog
from app.db.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    PasswordVerifyCodeRequest,
    RegisterConfirmRequest,
    RegisterRequest,
    TokenResponse,
    UserMe,
)
from app.services.auth import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.services.email_codes import cleanup_expired, issue_code, peek_code, verify_code
from app.services.email_sender import get_email_sender
from app.services.email_templates import (
    RESET_BODY,
    RESET_SUBJECT,
    SIGNUP_BODY,
    SIGNUP_SUBJECT,
    build_reset_html,
    build_signup_html,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _find_user_by_identifier(db: DbDep, identifier: str) -> User | None:
    """Busca usuário por username (exato) ou email (case-insensitive)."""
    result = await db.execute(
        select(User).where(
            or_(
                User.username == identifier,
                func.lower(User.email) == identifier.lower(),
            )
        )
    )
    return result.scalar_one_or_none()


def _account_status_error(status_value: str) -> HTTPException:
    messages = {
        "pending_email": "Confirmação de email pendente. Verifique sua caixa de entrada.",
        "pending_approval": "Cadastro aguardando aprovação. Você será notificado por email.",
        "rejected": "Cadastro não aprovado. Entre em contato com o administrador.",
        "disabled": "Conta desativada. Entre em contato com o administrador.",
        "pending_email_change": (
            "Seu email precisa ser atualizado. "
            "Entre em contato com o administrador."
        ),
    }
    detail = messages.get(status_value, "Conta inativa.")
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DbDep):
    user = await _find_user_by_identifier(db, body.identifier)

    ok = (
        user is not None
        and user.is_active
        and user.account_status == "active"
        and verify_password(body.password, user.hashed_password)
    )

    # Registra tentativa em auth_logs
    log = AuthLog(
        user_id=user.id if user else None,
        username_attempted=body.identifier,
        action="login_ok" if ok else "login_fail",
    )
    db.add(log)

    if user and user.is_active and user.account_status != "active":
        await db.commit()
        raise _account_status_error(user.account_status)

    if not ok:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )

    await db.execute(
        update(User).where(User.id == user.id).values(last_login_at=datetime.now(timezone.utc))
    )
    await db.commit()

    token = create_access_token(user.id, user.username, user.role)
    return TokenResponse(access_token=token)


# ── Dados do usuário autenticado ──────────────────────────────────────────────

@router.get("/me", response_model=UserMe)
async def me(user_payload: CurrentUser, db: DbDep):
    result = await db.execute(select(User).where(User.id == int(user_payload["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user


# ── Cadastro ──────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(body: RegisterRequest, db: DbDep):
    """
    Inicia o fluxo de cadastro.

    Não cria o usuário ainda — guarda o payload em email_codes.pending_payload
    e envia o código de confirmação por email.

    Mensagem genérica para não revelar se username/email já existe.
    """
    await cleanup_expired(db)

    # Verifica unicidade (sem revelar detalhes)
    existing = await db.execute(
        select(User).where(
            or_(
                User.username == body.username,
                func.lower(User.email) == str(body.email).lower(),
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        # Retorna 202 mesmo assim (anti-enumeração)
        return {"detail": "Se o cadastro for válido, um código será enviado para o email."}

    hashed = hash_password(body.password)
    payload = {
        "username": body.username,
        "hashed_password": hashed,
        "requested_role": body.requested_role,
    }

    s_cfg = __import__("app.config", fromlist=["get_settings"]).get_settings()
    code = await issue_code(
        db,
        email=str(body.email),
        purpose="signup",
        payload=payload,
    )

    sender = get_email_sender()
    await sender.send(
        to=str(body.email),
        subject=SIGNUP_SUBJECT,
        body_text=SIGNUP_BODY.format(
            username=body.username,
            code=code,
            ttl_minutes=s_cfg.mail_otp_ttl_minutes,
        ),
        body_html=build_signup_html(
            username=body.username,
            code=code,
            ttl_minutes=s_cfg.mail_otp_ttl_minutes,
        ),
    )

    return {"detail": "Se o cadastro for válido, um código será enviado para o email."}


@router.post("/register/confirm", status_code=status.HTTP_201_CREATED)
async def register_confirm(body: RegisterConfirmRequest, db: DbDep):
    """Valida o código de confirmação e cria o usuário com status pending_approval."""
    try:
        record = await verify_code(db, str(body.email), "signup", body.code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    payload = record.pending_payload or {}

    # Verifica unicidade novamente (alguém pode ter se cadastrado no intervalo)
    existing = await db.execute(
        select(User).where(
            or_(
                User.username == payload.get("username"),
                func.lower(User.email) == str(body.email).lower(),
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username ou email já cadastrado.",
        )

    user = User(
        username=payload["username"],
        email=str(body.email),
        hashed_password=payload["hashed_password"],
        role="viewer",  # role provisória; será definida na aprovação
        requested_role=payload.get("requested_role", "viewer"),
        account_status="pending_approval",
        is_active=True,
    )
    db.add(user)
    await db.commit()

    return {"detail": "Email confirmado. Seu cadastro aguarda aprovação."}


# ── Recuperação de senha ──────────────────────────────────────────────────────

@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def password_forgot(body: PasswordForgotRequest, db: DbDep):
    """Envia código de recuperação de senha. Sempre retorna 202 (anti-enumeração)."""
    user = await _find_user_by_identifier(db, body.identifier)

    if user and user.email and user.account_status == "active":
        s_cfg = __import__("app.config", fromlist=["get_settings"]).get_settings()
        code = await issue_code(
            db,
            email=user.email,
            purpose="password_reset",
            user_id=user.id,
        )
        sender = get_email_sender()
        await sender.send(
            to=user.email,
            subject=RESET_SUBJECT,
            body_text=RESET_BODY.format(
                code=code,
                ttl_minutes=s_cfg.mail_otp_ttl_minutes,
            ),
            body_html=build_reset_html(
                username=user.username,
                code=code,
                ttl_minutes=s_cfg.mail_otp_ttl_minutes,
            ),
        )

    return {"detail": "Se o identificador for válido, um código será enviado."}


@router.post("/password/verify-code", status_code=status.HTTP_200_OK)
async def password_verify_code(body: PasswordVerifyCodeRequest, db: DbDep):
    """Valida o código de recuperação SEM consumi-lo. Usado na etapa 1 da UI."""
    user = await _find_user_by_identifier(db, body.identifier)
    if not user or not user.email or user.account_status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido, expirado ou já utilizado.",
        )
    try:
        await peek_code(db, user.email, "password_reset", body.code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"detail": "ok"}


@router.post("/password/reset", status_code=status.HTTP_200_OK)
async def password_reset(body: PasswordResetRequest, db: DbDep):
    """Redefine a senha usando o código recebido por email."""
    user = await _find_user_by_identifier(db, body.identifier)
    if not user or not user.email or user.account_status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido, expirado ou já utilizado.",
        )

    try:
        record = await verify_code(db, user.email, "password_reset", body.code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if record.user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código inválido.")

    await db.execute(
        update(User)
        .where(User.id == record.user_id)
        .values(
            hashed_password=hash_password(body.new_password),
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    return {"detail": "Senha redefinida com sucesso."}
