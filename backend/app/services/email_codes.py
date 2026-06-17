"""
app/services/email_codes.py — Geração e verificação de códigos OTP por email.

Cada código:
  - 6 dígitos numéricos, gerados via secrets.randbelow (criptograficamente seguro).
  - Armazenado como hash bcrypt na tabela email_codes.
  - Expira em TELEMETRY_MAIL_OTP_TTL_MINUTES (default 15 min).
  - Limitado a 5 tentativas de verificação antes de ser invalidado.
  - Marcado como usado_at após verificação bem-sucedida.

Apenas um código válido por (email, purpose) é mantido ativo — códigos
anteriores são invalidados antes de emitir um novo.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.email_code import EmailCode
from app.services.auth import hash_password, verify_password


async def issue_code(
    db: AsyncSession,
    email: str,
    purpose: str,
    *,
    user_id: Optional[int] = None,
    payload: Optional[dict[str, Any]] = None,
) -> str:
    """
    Gera e persiste um novo código OTP.

    Invalida códigos anteriores do mesmo (email, purpose) antes de criar o novo.
    Retorna o código em claro (para enviar por email).
    """
    # Invalida códigos anteriores não usados
    await db.execute(
        update(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.used_at.is_(None),
        )
        .values(used_at=datetime.now(timezone.utc))
    )

    # Gera código
    code = f"{secrets.randbelow(10 ** 6):06d}"
    code_hash = hash_password(code)

    s = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=s.mail_otp_ttl_minutes)

    record = EmailCode(
        user_id=user_id,
        email=email,
        purpose=purpose,
        code_hash=code_hash,
        expires_at=expires_at,
        pending_payload=payload,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return code


async def verify_code(
    db: AsyncSession,
    email: str,
    purpose: str,
    code: str,
) -> EmailCode:
    """
    Verifica o código OTP.

    Lança ValueError em caso de:
      - Código não encontrado / já usado / expirado.
      - Código incorreto (incrementa attempts; bloqueia após 5).

    Marca used_at em caso de sucesso.
    """
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.used_at.is_(None),
            EmailCode.expires_at > now,
        )
        .order_by(EmailCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise ValueError("Código inválido, expirado ou já utilizado.")

    if record.attempts >= 5:
        raise ValueError("Número máximo de tentativas excedido. Solicite um novo código.")

    if not verify_password(code, record.code_hash):
        record.attempts += 1
        await db.commit()
        remaining = 5 - record.attempts
        raise ValueError(
            f"Código incorreto. {remaining} tentativa(s) restante(s)."
        )

    record.used_at = now
    await db.commit()
    await db.refresh(record)
    return record


async def peek_code(
    db: AsyncSession,
    email: str,
    purpose: str,
    code: str,
) -> EmailCode:
    """Valida o código SEM consumi-lo (não marca used_at).

    Incrementa attempts em código incorreto (mantém proteção brute force).
    Lança ValueError nos mesmos casos de verify_code.
    Usado para validar o código na primeira etapa antes de gravar a senha.
    """
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.used_at.is_(None),
            EmailCode.expires_at > now,
        )
        .order_by(EmailCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise ValueError("Código inválido, expirado ou já utilizado.")

    if record.attempts >= 5:
        raise ValueError("Número máximo de tentativas excedido. Solicite um novo código.")

    if not verify_password(code, record.code_hash):
        record.attempts += 1
        await db.commit()
        remaining = 5 - record.attempts
        raise ValueError(
            f"Código incorreto. {remaining} tentativa(s) restante(s)."
        )

    # Não marca used_at — código continua válido para o /password/reset
    return record


async def cleanup_expired(db: AsyncSession) -> int:
    """Remove códigos expirados e já usados. Retorna quantidade removida."""
    from sqlalchemy import delete  # local import para evitar circular

    now = datetime.now(timezone.utc)
    result = await db.execute(
        delete(EmailCode).where(
            (EmailCode.expires_at < now) | (EmailCode.used_at.is_not(None))
        )
    )
    await db.commit()
    return result.rowcount  # type: ignore[return-value]
