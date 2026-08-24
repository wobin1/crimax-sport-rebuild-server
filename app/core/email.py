"""Templated transactional emails for auth and staff invites.

Wraps :class:`ZohoMailService` and renders Crimax Sports-branded HTML. When
email is disabled or unconfigured (e.g. local dev), sends are logged instead of
raising so flows keep working; HTML is logged so developers can copy links.
"""

from __future__ import annotations

import logging
from html import escape

from app.config import get_settings
from app.services.zoho_mail_service import ZohoMailError, zoho_mail_service

logger = logging.getLogger(__name__)

_BRAND = "#6d28d9"
_BRAND_SOFT = "#7c3aed"


def _layout(title: str, body_html: str) -> str:
    year = 2026
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;background:#0a0a0f;font-family:Arial,Helvetica,sans-serif;color:#e5e7eb;">
  <div style="max-width:520px;margin:0 auto;padding:32px 16px;">
    <div style="background:{_BRAND};border-radius:16px 16px 0 0;padding:24px 32px;">
      <span style="color:#ffffff;font-size:20px;font-weight:bold;letter-spacing:0.04em;">
        CRIMAX SPORTS
      </span>
    </div>
    <div style="background:#16162b;padding:32px;border-radius:0 0 16px 16px;">
      <h1 style="font-size:20px;margin:0 0 16px;color:#ffffff;">{escape(title)}</h1>
      {body_html}
    </div>
    <p style="text-align:center;color:#6b7280;font-size:12px;margin-top:24px;">
      &copy; {year} Crimax Sports. All rights reserved.
    </p>
  </div>
</body>
</html>"""


def _button(url: str, label: str) -> str:
    return (
        f'<a href="{escape(url, quote=True)}" '
        f'style="display:inline-block;background:{_BRAND_SOFT};color:#ffffff;'
        f'text-decoration:none;padding:12px 24px;border-radius:10px;font-weight:bold;'
        f'font-size:14px;">{escape(label)}</a>'
    )


def _paragraph(text: str) -> str:
    return f'<p style="font-size:14px;line-height:1.6;color:#d1d5db;margin:0 0 16px;">{text}</p>'


class EmailService:
    """High-level templated email sender."""

    async def _send(
        self, *, to_address: str, subject: str, html_content: str, context: str
    ) -> bool:
        settings = get_settings()
        if not settings.emails_enabled or not zoho_mail_service.is_configured:
            logger.info(
                "Email disabled/unconfigured; skipping %s to %s. Content logged for dev only.",
                context,
                to_address,
            )
            logger.info("[DEV EMAIL] %s -> %s\n%s", context, to_address, html_content)
            return False

        try:
            await zoho_mail_service.send(
                to_address=to_address,
                subject=subject,
                html_content=html_content,
            )
            logger.info("Sent %s email to %s", context, to_address)
            return True
        except ZohoMailError:
            logger.exception("Failed to send %s email to %s", context, to_address)
            return False

    async def send_invite_email(
        self, *, to_address: str, full_name: str, invite_url: str, role: str
    ) -> bool:
        settings = get_settings()
        role_label = role.replace("_", " ").title()
        body = (
            _paragraph(f"Hi {escape(full_name or 'there')},")
            + _paragraph(
                f"You've been invited to <strong>Crimax Sports</strong> as a "
                f"<strong>{escape(role_label)}</strong>."
            )
            + f'<p style="margin:24px 0;">{_button(invite_url, "Accept invite")}</p>'
            + _paragraph(
                "Or paste this link into your browser:<br/>"
                f'<a href="{escape(invite_url, quote=True)}" style="color:{_BRAND_SOFT};word-break:break-all;">'
                f"{escape(invite_url)}</a>"
            )
            + _paragraph(
                f"This link expires in about {settings.invite_expire_hours} hours. "
                "If you weren't expecting this, you can ignore it."
            )
        )
        return await self._send(
            to_address=to_address,
            subject="You're invited to Crimax Sports Admin",
            html_content=_layout("You're invited", body),
            context="invite",
        )

    async def send_welcome_email(self, *, to_address: str, name: str) -> bool:
        settings = get_settings()
        dashboard = f"{settings.frontend_url.rstrip('/')}/admin/dashboard"
        body = (
            _paragraph(f"Hi {escape(name or 'there')},")
            + _paragraph(
                "Your Crimax Sports admin account is active. You can sign in and "
                "start managing fixtures, clubs, and live matches."
            )
            + f'<p style="margin:24px 0;">{_button(dashboard, "Go to dashboard")}</p>'
        )
        return await self._send(
            to_address=to_address,
            subject="Welcome to Crimax Sports",
            html_content=_layout("You're all set", body),
            context="welcome",
        )

    async def send_password_reset_email(
        self, *, to_address: str, name: str, reset_url: str
    ) -> bool:
        settings = get_settings()
        body = (
            _paragraph(f"Hi {escape(name or 'there')},")
            + _paragraph(
                "We received a request to reset your Crimax Sports password. "
                "Click below to choose a new one."
            )
            + f'<p style="margin:24px 0;">{_button(reset_url, "Reset password")}</p>'
            + _paragraph(
                f"This link expires in {settings.password_reset_ttl_minutes} minutes. "
                "If you didn't request this, you can safely ignore this email — your "
                "password won't change."
            )
        )
        return await self._send(
            to_address=to_address,
            subject="Reset your Crimax Sports password",
            html_content=_layout("Reset your password", body),
            context="password_reset",
        )

    async def send_password_changed_email(self, *, to_address: str, name: str) -> bool:
        body = (
            _paragraph(f"Hi {escape(name or 'there')},")
            + _paragraph(
                "Your Crimax Sports password was just changed. If this was you, "
                "no action is needed."
            )
            + _paragraph(
                "If you didn't do this, reset your password immediately and contact support."
            )
        )
        return await self._send(
            to_address=to_address,
            subject="Your Crimax Sports password was changed",
            html_content=_layout("Password changed", body),
            context="password_changed",
        )

    async def send_new_login_email(
        self, *, to_address: str, name: str, when: str, ip_address: str
    ) -> bool:
        body = (
            _paragraph(f"Hi {escape(name or 'there')},")
            + _paragraph("We noticed a new sign-in to your Crimax Sports account:")
            + _paragraph(
                f"<strong>Time:</strong> {escape(when)}<br>"
                f"<strong>IP:</strong> {escape(ip_address)}"
            )
            + _paragraph(
                "If this was you, you can ignore this email. If not, reset your password "
                "right away."
            )
        )
        return await self._send(
            to_address=to_address,
            subject="New sign-in to your Crimax Sports account",
            html_content=_layout("New sign-in detected", body),
            context="new_login",
        )


email_service = EmailService()


# Backward-compatible alias used by invite routes.
async def send_invite_email(
    *, to: str, full_name: str, invite_url: str, role: str
) -> bool:
    return await email_service.send_invite_email(
        to_address=to,
        full_name=full_name,
        invite_url=invite_url,
        role=role,
    )
