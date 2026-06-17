from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.services.auth import validate_password_strength


# ── Login ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Aceita username OU email no campo identifier."""
    identifier: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMe(BaseModel):
    id: int
    username: str
    email: Optional[str]
    role: str
    account_status: str
    is_active: bool

    model_config = {"from_attributes": True}


# ── Cadastro ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    requested_role: Literal["viewer", "approver"] = "viewer"

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username deve ter pelo menos 3 caracteres.")
        if len(v) > 64:
            raise ValueError("Username deve ter no máximo 64 caracteres.")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username só pode conter letras, números, _ e -.")
        return v

    @model_validator(mode="after")
    def password_strong(self) -> "RegisterRequest":
        validate_password_strength(
            self.password,
            username=self.username,
            email=str(self.email),
        )
        return self


class RegisterConfirmRequest(BaseModel):
    email: EmailStr
    code: str


# ── Recuperação de senha ──────────────────────────────────────────────────────

class PasswordForgotRequest(BaseModel):
    identifier: str  # email ou username


class PasswordVerifyCodeRequest(BaseModel):
    identifier: str  # email ou username
    code: str


class PasswordResetRequest(BaseModel):
    identifier: str  # email ou username (resolvido no backend)
    code: str
    new_password: str

    @model_validator(mode="after")
    def password_strong(self) -> "PasswordResetRequest":
        validate_password_strength(self.new_password)
        return self


# ── Perfil ────────────────────────────────────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username deve ter pelo menos 3 caracteres.")
        if len(v) > 64:
            raise ValueError("Username deve ter no máximo 64 caracteres.")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username só pode conter letras, números, _ e -.")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class EmailChangeConfirmRequest(BaseModel):
    code: str


# ── Aprovação ─────────────────────────────────────────────────────────────────

class ApprovalVoteRequest(BaseModel):
    note: Optional[str] = None


# ── Lista de usuários ─────────────────────────────────────────────────────────

class UserBasic(BaseModel):
    """Visão mínima — exposta para approver."""
    id: int
    username: str
    email: Optional[str]

    model_config = {"from_attributes": True}


class UserFull(BaseModel):
    """Visão completa — exposta só para admin."""
    id: int
    username: str
    email: Optional[str]
    role: str
    account_status: str
    is_active: bool
    requested_role: Optional[str]

    model_config = {"from_attributes": True}


class PendingUserItem(BaseModel):
    """Item na fila de aprovação."""
    id: int
    username: str
    email: Optional[str]
    requested_role: Optional[str]
    approvals_count: int = 0  # votos de aprovação já registrados

    model_config = {"from_attributes": True}
