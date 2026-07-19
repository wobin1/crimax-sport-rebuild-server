"""Outbound email via Zoho (or any) SMTP."""

from email.message import EmailMessage

import aiosmtplib

from app.config import get_settings


async def send_email(*, to: str, subject: str, text: str, html: str | None = None) -> None:
    settings = get_settings()
    if not settings.smtp_configured:
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD."
        )

    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    if settings.smtp_use_ssl:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=True,
        )
    else:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )


async def send_invite_email(*, to: str, full_name: str, invite_url: str, role: str) -> None:
    role_label = role.replace("_", " ").title()
    subject = "You're invited to Crimax Sports Admin"
    text = (
        f"Hi {full_name},\n\n"
        f"You've been invited to Crimax Sports as a {role_label}.\n\n"
        f"Accept your invite and set a password:\n{invite_url}\n\n"
        f"This link expires soon. If you weren't expecting this, you can ignore it.\n"
    )
    html = f"""\
<html>
  <body style="font-family: sans-serif; color: #111; line-height: 1.5;">
    <p>Hi {full_name},</p>
    <p>You've been invited to <strong>Crimax Sports</strong> as a
       <strong>{role_label}</strong>.</p>
    <p>
      <a href="{invite_url}"
         style="display:inline-block;padding:10px 18px;background:#16a34a;
                color:#fff;text-decoration:none;border-radius:8px;">
        Accept invite
      </a>
    </p>
    <p style="font-size:13px;color:#666;">
      Or paste this link into your browser:<br/>
      <a href="{invite_url}">{invite_url}</a>
    </p>
    <p style="font-size:13px;color:#666;">
      This link expires soon. If you weren't expecting this, you can ignore it.
    </p>
  </body>
</html>
"""
    await send_email(to=to, subject=subject, text=text, html=html)
