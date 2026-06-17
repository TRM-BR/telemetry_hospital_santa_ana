"""
app/services/email_templates.py — Templates de email (texto puro + HTML).

Texto puro: strings simples com .format(**kwargs) — usadas como fallback
multipart e no ConsoleEmailSender em desenvolvimento.

HTML: builders que geram email estilizado com header azul, card central,
dígitos do OTP em caixas individuais e badge de expiração.
"""
from __future__ import annotations

# ── Cadastro — validação de email ────────────────────────────────────────────

SIGNUP_SUBJECT = "Confirmação de cadastro — Telemetria Hídrica"

SIGNUP_BODY = """\
Olá, {username}!

Você solicitou cadastro na plataforma de Telemetria Hídrica.

Seu código de confirmação é:

    {code}

O código expira em {ttl_minutes} minutos.

Se você não solicitou este cadastro, ignore este email.

—
Telemetria Hídrica · Prefeitura de Barueri
"""

# ── Recuperação de senha ──────────────────────────────────────────────────────

RESET_SUBJECT = "Recuperação de senha — Telemetria Hídrica"

RESET_BODY = """\
Olá!

Recebemos uma solicitação de recuperação de senha para a conta associada
a este email.

Seu código de redefinição é:

    {code}

O código expira em {ttl_minutes} minutos.

Se você não solicitou a recuperação, ignore este email. Sua senha não
será alterada.

—
Telemetria Hídrica · Prefeitura de Barueri
"""

# ── Troca de email ───────────────────────────────────────────────────────────

EMAIL_CHANGE_SUBJECT = "Confirmação de novo email — Telemetria Hídrica"

EMAIL_CHANGE_BODY = """\
Olá, {username}!

Foi solicitada a troca do email da sua conta para este endereço.

Seu código de confirmação é:

    {code}

O código expira em {ttl_minutes} minutos.

Se você não solicitou esta alteração, ignore este email.

—
Telemetria Hídrica · Prefeitura de Barueri
"""

# ── Builders HTML ────────────────────────────────────────────────────────────


def _render_digit_cells(code: str) -> str:
    return "".join(
        f'<td style="padding:0 5px;">'
        f'<div style="width:46px;height:58px;line-height:58px;'
        f'text-align:center;background-color:#ffffff;'
        f'border:1px solid #d6e6f2;border-radius:10px;'
        f'font-family:\'Courier New\',Courier,monospace;'
        f'font-size:26px;font-weight:700;color:#0b4f8a;'
        f'box-shadow:0 1px 2px rgba(11,79,138,0.08);">{d}</div></td>'
        for d in code
    )


def _build_otp_email_html(
    *,
    title: str,
    greeting: str,
    intro_html: str,
    code: str,
    ttl_minutes: int,
    warning_html: str,
) -> str:
    digit_cells = _render_digit_cells(code)
    return f"""\
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#f0f4f8;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f0f4f8;padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#0b4f8a 0%,#1583c4 100%);
                       border-radius:16px 16px 0 0;padding:36px 40px 28px;text-align:center;">
              <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:0.18em;
                         color:rgba(255,255,255,0.7);text-transform:uppercase;">VECTOR</p>
              <p style="margin:0;font-size:20px;font-weight:700;color:#ffffff;">
                Telemetria H&#237;drica
              </p>
            </td>
          </tr>

          <!-- Card -->
          <tr>
            <td style="background-color:#ffffff;border-radius:0 0 16px 16px;
                       padding:40px 40px 32px;box-shadow:0 4px 24px rgba(11,79,138,0.10);">

              <h1 style="margin:0 0 20px;font-size:20px;font-weight:700;color:#0b4f8a;
                          text-align:center;">{title}</h1>

              <p style="margin:0 0 12px;font-size:15px;color:#334155;">{greeting}</p>
              <p style="margin:0 0 28px;font-size:15px;color:#334155;line-height:1.6;">
                {intro_html}
              </p>

              <!-- Digit boxes -->
              <table cellpadding="0" cellspacing="0" style="margin:0 auto 28px;">
                <tr>
                  {digit_cells}
                </tr>
              </table>

              <!-- Expiry badge -->
              <p style="text-align:center;margin:0 0 28px;">
                <span style="display:inline-block;background-color:#fffbeb;
                             border:1px solid #fcd34d;border-radius:20px;
                             padding:6px 16px;font-size:13px;font-weight:600;color:#92400e;">
                  &#9203; Expira em {ttl_minutes} minuto{'s' if ttl_minutes != 1 else ''}
                </span>
              </p>

              <!-- Warning -->
              <p style="margin:0;font-size:13px;color:#64748b;line-height:1.5;
                         border-top:1px solid #e2e8f0;padding-top:20px;">
                {warning_html}
              </p>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 0;text-align:center;">
              <p style="margin:0;font-size:12px;color:#94a3b8;">
                Telemetria H&#237;drica &middot; Prefeitura de Barueri
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_signup_html(*, username: str, code: str, ttl_minutes: int) -> str:
    return _build_otp_email_html(
        title="Confirme seu cadastro",
        greeting=f"Ol&#225;, {username}!",
        intro_html=(
            "Voc&#234; solicitou cadastro na plataforma de <strong>Telemetria H&#237;drica</strong>. "
            "Use o c&#243;digo abaixo para confirmar seu email:"
        ),
        code=code,
        ttl_minutes=ttl_minutes,
        warning_html=(
            "Se voc&#234; n&#227;o solicitou este cadastro, ignore este email. "
            "Nenhuma conta ser&#225; criada."
        ),
    )


def build_reset_html(*, username: str | None, code: str, ttl_minutes: int) -> str:
    greeting = f"Ol&#225;, {username}!" if username else "Ol&#225;!"
    return _build_otp_email_html(
        title="Redefini&#231;&#227;o de senha",
        greeting=greeting,
        intro_html=(
            "Recebemos uma solicita&#231;&#227;o de recupera&#231;&#227;o de senha. "
            "Use o c&#243;digo abaixo para redefinir sua senha:"
        ),
        code=code,
        ttl_minutes=ttl_minutes,
        warning_html=(
            "Se voc&#234; n&#227;o solicitou a recupera&#231;&#227;o, ignore este email. "
            "Sua senha <strong>n&#227;o ser&#225;</strong> alterada."
        ),
    )


def build_email_change_html(*, username: str, code: str, ttl_minutes: int) -> str:
    return _build_otp_email_html(
        title="Confirma&#231;&#227;o de novo email",
        greeting=f"Ol&#225;, {username}!",
        intro_html=(
            "Foi solicitada a troca do email da sua conta para este endere&#231;o. "
            "Use o c&#243;digo abaixo para confirmar:"
        ),
        code=code,
        ttl_minutes=ttl_minutes,
        warning_html=(
            "Se voc&#234; n&#227;o solicitou esta altera&#231;&#227;o, ignore este email. "
            "Seu email atual <strong>n&#227;o ser&#225;</strong> alterado."
        ),
    )


# ── Aprovação de cadastro ─────────────────────────────────────────────────────

APPROVAL_APPROVED_SUBJECT = "Cadastro aprovado — Telemetria Hídrica"

APPROVAL_APPROVED_BODY = """\
Olá, {username}!

Seu cadastro na plataforma de Telemetria Hídrica foi aprovado.

Você já pode fazer login em:
  {login_url}

—
Telemetria Hídrica · Prefeitura de Barueri
"""

APPROVAL_REJECTED_SUBJECT = "Cadastro não aprovado — Telemetria Hídrica"

APPROVAL_REJECTED_BODY = """\
Olá, {username}!

Infelizmente seu cadastro na plataforma de Telemetria Hídrica não foi
aprovado.

Se acredita que houve um engano, entre em contato com o administrador
do sistema.

—
Telemetria Hídrica · Prefeitura de Barueri
"""
