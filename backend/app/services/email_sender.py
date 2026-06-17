"""
app/services/email_sender.py — Envio de email.

Dois backends:
  - SmtpEmailSender  : usa aiosmtplib com STARTTLS. Ativado quando MAIL_HOST
                       estiver configurado.
  - ConsoleEmailSender: loga o email no nível INFO. Ativado quando MAIL_HOST
                        estiver vazio. Ideal para dev/test.

Uso:
    from app.services.email_sender import get_email_sender
    sender = get_email_sender()
    await sender.send(to="foo@bar.com", subject="...", body_text="...")
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmailSender(ABC):
    @abstractmethod
    async def send(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> None:
        """Envia um email. Lança exceção em caso de falha."""


class SmtpEmailSender(EmailSender):
    """Envia via SMTP com STARTTLS."""

    async def send(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> None:
        s = get_settings()

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = s.mail_from
        msg["To"] = to

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=s.mail_host,
            port=s.mail_port,
            username=s.mail_user or None,
            password=s.mail_password or None,
            start_tls=s.mail_starttls,
        )
        logger.info("email.sent", extra={"to": to, "subject": subject})


class ConsoleEmailSender(EmailSender):
    """Loga o email no console em vez de enviá-lo. Usado em dev/test."""

    async def send(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> None:
        logger.info(
            "email.console_sender [DEV — não enviado por SMTP]",
            extra={"to": to, "subject": subject, "body": body_text},
        )
        # Imprime também em stdout para facilitar leitura nos logs do uvicorn
        separator = "─" * 60
        print(f"\n{separator}")
        print(f"[EMAIL DEV] Para:     {to}")
        print(f"[EMAIL DEV] Assunto:  {subject}")
        print(f"[EMAIL DEV] Mensagem:\n{body_text}")
        print(f"{separator}\n")


_sender: Optional[EmailSender] = None


def get_email_sender() -> EmailSender:
    """Retorna singleton do sender adequado ao ambiente."""
    global _sender
    if _sender is None:
        s = get_settings()
        _sender = SmtpEmailSender() if s.mail_host else ConsoleEmailSender()
    return _sender
