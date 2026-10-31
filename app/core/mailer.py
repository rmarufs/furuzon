from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings


async def send_email(to: str, subject: str, body: str) -> None:
    if settings.MAIL_BACKEND == "console":
        print(f"[MAIL] To: {to}\nSubject: {subject}\n{body}\n")
        return

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER or None,
        password=settings.SMTP_PASSWORD or None,
    )
