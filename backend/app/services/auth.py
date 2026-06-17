"""
app/services/auth.py — Hash de senha, JWT e validação de força de senha.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        import structlog
        structlog.get_logger().warning("verify_password.error", exc_info=True)
        return False


def validate_password_strength(
    password: str,
    *,
    username: Optional[str] = None,
    email: Optional[str] = None,
) -> None:
    """
    Valida força da senha segundo as regras do sistema.

    Regras:
      - Mínimo 10 caracteres.
      - Ao menos 1 letra maiúscula.
      - Ao menos 1 letra minúscula.
      - Ao menos 1 dígito.
      - Ao menos 1 símbolo (!@#$%^&*...).
      - Não pode conter o username ou a parte local do email.

    Lança ValueError com mensagem descritiva em caso de violação.
    """
    errors: list[str] = []

    if len(password) < 10:
        errors.append("A senha deve ter pelo menos 10 caracteres.")
    if not re.search(r"[A-Z]", password):
        errors.append("A senha deve conter pelo menos uma letra maiúscula.")
    if not re.search(r"[a-z]", password):
        errors.append("A senha deve conter pelo menos uma letra minúscula.")
    if not re.search(r"\d", password):
        errors.append("A senha deve conter pelo menos um número.")
    if not re.search(r'[!@#$%^&*()\-_=+\[\]{}|;:\'",.<>?/`~\\]', password):
        errors.append("A senha deve conter pelo menos um símbolo especial.")

    pw_lower = password.lower()
    if username and len(username) >= 3 and username.lower() in pw_lower:
        errors.append("A senha não pode conter o nome de usuário.")
    if email:
        local_part = email.split("@")[0].lower()
        if len(local_part) >= 3 and local_part in pw_lower:
            errors.append("A senha não pode conter parte do email.")

    if errors:
        raise ValueError(" ".join(errors))


def create_access_token(user_id: int, username: str, role: str) -> str:
    s = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=s.api_access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "username": username, "role": role, "exp": expire},
        s.api_secret_key,
        algorithm=s.api_jwt_algorithm,
    )


def decode_access_token(token: str) -> Optional[dict]:
    s = get_settings()
    try:
        return jwt.decode(token, s.api_secret_key, algorithms=[s.api_jwt_algorithm])
    except JWTError:
        return None
