"""
users — Usuários do sistema.

Senhas armazenadas como hash bcrypt.
Roles: 'admin' | 'approver' | 'viewer'.
  - admin   : acesso total, incluindo auditoria e terminal MQTT.
  - approver: acesso padrão + pode aprovar/rejeitar cadastros de viewer;
              aprovação de outro approver exige 2 votos de approver ou 1 admin.
  - viewer  : acesso padrão ao dashboard e instalações.

account_status:
  - 'pending_email'        : aguardando confirmação do código enviado por email.
  - 'pending_approval'     : email confirmado, aguardando aprovação de admin/approver.
  - 'active'               : conta ativa, pode fazer login.
  - 'rejected'             : cadastro recusado.
  - 'disabled'             : conta desativada por admin.
  - 'pending_email_change' : email atual inválido/nulo, aguarda troca via fluxo de perfil.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Login — único por instância
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Email — único, obrigatório para novos usuários (migration backfill para existentes)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)

    # Hash bcrypt da senha (nunca armazenar texto puro)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)

    # Papel no sistema: 'admin' | 'approver' | 'viewer'
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="viewer", server_default="'viewer'"
    )

    # Estado da conta (ver docstring do módulo)
    account_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="active", server_default="'active'"
    )

    # Role solicitada no cadastro — apenas relevante enquanto pending_*
    requested_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Usuário pode fazer login (false = conta bloqueada sem motivo)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role} status={self.account_status!r}>"
