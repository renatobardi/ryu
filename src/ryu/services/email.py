"""Serviço de e-mail do Ryu (paridade multica server/internal/service/email.go).

Prioridade de entrega: SMTP relay → Resend API → DEV stdout.
Ativado por env vars (RYU_SMTP_HOST / RYU_RESEND_API_KEY); sem nada
configurado, imprime no stdout/log com aviso claro (modo dev).

Exporta:
- EmailService (send_verification_code / send_invitation_email)
- get_email_service() — singleton preguiçoso baseado nas settings atuais.
"""
from __future__ import annotations

import asyncio
import html
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

import httpx
import structlog

from ryu.config import settings

log = structlog.get_logger("ryu.email")

# cap de texto controlado pelo usuário no Subject (anti-phishing; multica)
MAX_SUBJECT_FIELD_CHARS = 60


def _sanitize_subject_field(s: str) -> str:
    cleaned = "".join(ch for ch in s if ch.isprintable())
    if len(cleaned) <= MAX_SUBJECT_FIELD_CHARS:
        return cleaned
    return cleaned[: MAX_SUBJECT_FIELD_CHARS - 1] + "…"


class EmailService:
    def __init__(self) -> None:
        self.smtp_host = (settings.smtp_host or "").strip()
        self.smtp_port = settings.smtp_port
        self.smtp_username = settings.smtp_username or ""
        self.smtp_password = settings.smtp_password or ""
        self.smtp_tls_insecure = settings.smtp_tls_insecure
        self.smtp_ehlo_name = (settings.smtp_ehlo_name or "").strip() or None
        tls_mode = (settings.smtp_tls or "").strip().lower()
        self.smtp_tls_implicit = tls_mode in ("implicit", "smtps", "ssl") or (
            tls_mode == "" and self.smtp_port == 465
        )
        if tls_mode not in ("", "starttls", "implicit", "smtps", "ssl"):
            log.warning("smtp_tls_unrecognized", value=tls_mode, fallback="starttls")
        self.resend_api_key = (settings.resend_api_key or "").strip()
        self.from_email = self._resolve_from_email()

        if self.smtp_host:
            log.info(
                "email_service_mode",
                mode="smtp",
                host=self.smtp_host,
                port=self.smtp_port,
                tls="implicit" if self.smtp_tls_implicit else "starttls",
                from_email=self.from_email,
            )
        elif self.resend_api_key:
            log.info("email_service_mode", mode="resend", from_email=self.from_email)
        else:
            log.info(
                "email_service_mode",
                mode="dev-stdout",
                hint="configure RYU_SMTP_HOST ou RYU_RESEND_API_KEY para envio real",
            )

    def _resolve_from_email(self) -> str:
        resend_from = (settings.resend_from_email or "").strip()
        if not self.smtp_host:
            return resend_from or "noreply@ryu.local"
        smtp_from = (settings.smtp_from_email or "").strip()
        return smtp_from or resend_from

    # ── SMTP ──────────────────────────────────────────────────────────
    def _send_smtp_sync(self, to: str, subject: str, html_body: str) -> None:
        if not self.from_email:
            raise RuntimeError("RYU_SMTP_FROM_EMAIL ou RYU_RESEND_FROM_EMAIL é obrigatório com SMTP")

        tls_ctx = ssl.create_default_context()
        if self.smtp_tls_insecure:
            tls_ctx.check_hostname = False
            tls_ctx.verify_mode = ssl.CERT_NONE

        if self.smtp_tls_implicit:
            client = smtplib.SMTP_SSL(
                self.smtp_host,
                self.smtp_port,
                local_hostname=self.smtp_ehlo_name,
                timeout=30,
                context=tls_ctx,
            )
        else:
            client = smtplib.SMTP(
                self.smtp_host, self.smtp_port, local_hostname=self.smtp_ehlo_name, timeout=30
            )
        try:
            if not self.smtp_tls_implicit:
                client.ehlo()
                if client.has_extn("starttls"):
                    client.starttls(context=tls_ctx)
                    client.ehlo()
            if self.smtp_username:
                try:
                    client.login(self.smtp_username, self.smtp_password)
                except smtplib.SMTPAuthenticationError:
                    raise
                except smtplib.SMTPException:
                    # fallback AUTH LOGIN p/ servidores sem AUTH PLAIN
                    try:
                        client.auth("LOGIN", client.auth_login, initial_response_ok=False)
                    except Exception as exc:  # noqa: BLE001
                        raise RuntimeError(f"smtp auth falhou (PLAIN e LOGIN): {exc}") from exc
            msg = MIMEText(html_body, "html", "utf-8")
            msg["From"] = self.from_email
            msg["To"] = to
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=False)
            msg["Message-ID"] = make_msgid(domain=self.smtp_host)
            client.sendmail(self.from_email, [to], msg.as_string())
        finally:
            try:
                client.quit()
            except Exception:  # noqa: BLE001
                pass

    # ── Resend ────────────────────────────────────────────────────────
    async def _send_resend(self, to: str, subject: str, html_body: str) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.resend_api_key}"},
                json={
                    "from": self.from_email or "noreply@ryu.local",
                    "to": [to],
                    "subject": subject,
                    "html": html_body,
                },
            )
            if r.status_code >= 400:
                raise RuntimeError(f"resend API {r.status_code}: {r.text[:300]}")

    async def _send(self, to: str, subject: str, html_body: str, dev_line: str) -> None:
        if self.smtp_host:
            await asyncio.to_thread(self._send_smtp_sync, to, subject, html_body)
            return
        if self.resend_api_key:
            await self._send_resend(to, subject, html_body)
            return
        print(dev_line, flush=True)
        log.info("email_dev_stdout", to=to, subject=subject)

    # ── API pública ───────────────────────────────────────────────────
    async def send_verification_code(self, to: str, code: str) -> None:
        body = f"""<div style="font-family: sans-serif; max-width: 400px; margin: 0 auto;">
            <h2>Your verification code</h2>
            <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; margin: 24px 0;">{code}</p>
            <p>This code expires in 15 minutes.</p>
            <p style="color: #666; font-size: 14px;">If you didn't request this code, you can safely ignore this email.</p>
        </div>"""
        await self._send(
            to,
            "Your Ryu verification code",
            body,
            f"[ryu-auth] verification code for {to}: {code}",
        )

    async def send_invitation_email(
        self, to: str, inviter_name: str, workspace_name: str, invitation_id: str
    ) -> None:
        app_url = (settings.app_url or "").rstrip("/") or "http://localhost:8000"
        invite_url = f"{app_url}/invite/{invitation_id}"
        safe_ws = html.escape(workspace_name)
        safe_inviter = html.escape(inviter_name)
        subject = (
            f"{_sanitize_subject_field(inviter_name)} invited you to "
            f"{_sanitize_subject_field(workspace_name)} on Ryu"
        )
        body = f"""<div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
            <h2>You're invited to join {safe_ws}</h2>
            <p><strong>{safe_inviter}</strong> invited you to collaborate in the <strong>{safe_ws}</strong> workspace on Ryu.</p>
            <p style="margin: 24px 0;">
                <a href="{invite_url}" style="display: inline-block; padding: 12px 24px; background: #000; color: #fff; text-decoration: none; border-radius: 6px; font-weight: 500;">Accept invitation</a>
            </p>
            <p style="color: #666; font-size: 14px;">You'll need to log in to accept or decline the invitation.</p>
        </div>"""
        await self._send(
            to,
            subject,
            body,
            f"[ryu-email] invitation to {to}: {inviter_name} invited you to {workspace_name} — {invite_url}",
        )


_service: EmailService | None = None


def get_email_service() -> EmailService:
    global _service
    if _service is None:
        _service = EmailService()
    return _service
