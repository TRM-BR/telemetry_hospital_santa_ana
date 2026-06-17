"""
/api/v1/users — Perfil do usuário e listagem.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select, update

from app.api.deps import AdminUser, CurrentUser, DbDep
from app.db.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    EmailChangeConfirmRequest,
    ProfileUpdateRequest,
    UserFull,
    UserMe,
)
from app.services.auth import hash_password, validate_password_strength, verify_password
from app.services.email_codes import issue_code, verify_code
from app.services.email_sender import get_email_sender
from app.services.email_templates import (
    EMAIL_CHANGE_BODY,
    EMAIL_CHANGE_SUBJECT,
    build_email_change_html,
)

router = APIRouter(prefix="/users", tags=["users"])


# ── Perfil próprio ────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserMe)
async def get_my_profile(user_payload: CurrentUser, db: DbDep):
    result = await db.execute(select(User).where(User.id == int(user_payload["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user


@router.patch("/me", status_code=status.HTTP_200_OK, response_model=UserMe)
async def update_my_profile(body: ProfileUpdateRequest, user_payload: CurrentUser, db: DbDep):
    """
    Atualiza username e/ou solicita troca de email.

    Se email for alterado, envia código de confirmação para o novo endereço
    — a troca só é efetivada após POST /users/me/email/confirm.
    """
    user_id = int(user_payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    changes: dict = {}

    if body.username and body.username != user.username:
        # Verifica unicidade
        conflict = await db.execute(
            select(User).where(User.username == body.username, User.id != user_id)
        )
        if conflict.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Username já em uso.")
        changes["username"] = body.username

    if body.email and str(body.email).lower() != (user.email or "").lower():
        new_email = str(body.email)
        conflict = await db.execute(
            select(User).where(
                func.lower(User.email) == new_email.lower(),
                User.id != user_id,
            )
        )
        if conflict.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email já em uso.")

        # Envia código de confirmação para o NOVO email
        s_cfg = __import__("app.config", fromlist=["get_settings"]).get_settings()
        code = await issue_code(
            db,
            email=new_email,
            purpose="email_change",
            user_id=user_id,
            payload={"new_email": new_email},
        )
        sender = get_email_sender()
        await sender.send(
            to=new_email,
            subject=EMAIL_CHANGE_SUBJECT,
            body_text=EMAIL_CHANGE_BODY.format(
                username=user.username,
                code=code,
                ttl_minutes=s_cfg.mail_otp_ttl_minutes,
            ),
            body_html=build_email_change_html(
                username=user.username,
                code=code,
                ttl_minutes=s_cfg.mail_otp_ttl_minutes,
            ),
        )
        # Não altera email agora — aguarda confirmação

    if changes:
        changes["updated_at"] = datetime.now(UTC)
        await db.execute(update(User).where(User.id == user_id).values(**changes))
        await db.commit()
        await db.refresh(user)

    return user


@router.post("/me/email/confirm", status_code=status.HTTP_200_OK, response_model=UserMe)
async def confirm_email_change(
    body: EmailChangeConfirmRequest, user_payload: CurrentUser, db: DbDep
):
    """Confirma a troca de email usando o código enviado para o novo endereço."""
    user_id = int(user_payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Busca o código de email_change pendente para este user_id
    from sqlalchemy import select as sel

    from app.db.models.email_code import EmailCode

    code_result = await db.execute(
        sel(EmailCode).where(
            EmailCode.user_id == user_id,
            EmailCode.purpose == "email_change",
            EmailCode.used_at.is_(None),
            EmailCode.expires_at > datetime.now(UTC),
        )
        .order_by(EmailCode.created_at.desc())
        .limit(1)
    )
    pending = code_result.scalar_one_or_none()
    if not pending or not pending.pending_payload:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma troca de email pendente. Solicite novamente no perfil.",
        )

    new_email: str = pending.pending_payload["new_email"]

    try:
        await verify_code(db, new_email, "email_change", body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(email=new_email, updated_at=datetime.now(UTC))
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: ChangePasswordRequest, user_payload: CurrentUser, db: DbDep):
    user_id = int(user_payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")

    try:
        validate_password_strength(
            body.new_password,
            username=user.username,
            email=user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            hashed_password=hash_password(body.new_password),
            updated_at=datetime.now(UTC),
        )
    )
    await db.commit()


# ── Listagem ──────────────────────────────────────────────────────────────────

@router.get("", status_code=status.HTTP_200_OK)
async def list_users(
    _user_payload: AdminUser,
    db: DbDep,
) -> list[UserFull]:
    """
    Lista usuários. Disponível apenas para admin.
    """
    result = await db.execute(
        select(User).where(User.account_status != "pending_approval").order_by(User.username)
    )
    users = result.scalars().all()

    return [UserFull.model_validate(u) for u in users]
