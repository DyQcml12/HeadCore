from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Callable, Protocol


class SmtpClient(Protocol):
    def starttls(self) -> None: ...

    def login(self, username: str, password: str) -> None: ...

    def send_message(self, message: EmailMessage) -> None: ...

    def quit(self) -> None: ...


@dataclass(frozen=True)
class SmtpEmailSettings:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    starttls: bool = True

    def validate(self) -> None:
        if not all((self.host, self.username, self.password, self.from_address)):
            raise ValueError("SMTP settings are incomplete")
        if not 1 <= self.port <= 65535:
            raise ValueError("SMTP port is invalid")


class SmtpEmailVerificationDelivery:
    def __init__(
        self,
        settings: SmtpEmailSettings,
        *,
        smtp_factory: Callable[[str, int], SmtpClient] = smtplib.SMTP,
    ) -> None:
        settings.validate()
        self._settings = settings
        self._smtp_factory = smtp_factory

    async def send_verification(self, *, email: str, token: str, expires_at: datetime) -> None:
        await asyncio.to_thread(self._send, email, token, expires_at)

    async def send_password_reset(self, *, email: str, token: str, expires_at: datetime) -> None:
        await asyncio.to_thread(self._send_password_reset, email, token, expires_at)

    def _send(self, email: str, token: str, expires_at: datetime) -> None:
        message = EmailMessage()
        message["Subject"] = "HuTaoChatCore 邮箱验证"
        message["From"] = self._settings.from_address
        message["To"] = email
        message.set_content(
            "请在 HuTaoChatCore 的邮箱验证页面提交以下验证码：\n\n"
            f"{token}\n\n"
            f"有效期至：{expires_at.isoformat()}\n"
            "请勿将验证码分享给他人。"
        )
        client = self._smtp_factory(self._settings.host, self._settings.port)
        try:
            if self._settings.starttls:
                client.starttls()
            client.login(self._settings.username, self._settings.password)
            client.send_message(message)
        finally:
            client.quit()

    def _send_password_reset(self, email: str, token: str, expires_at: datetime) -> None:
        message = EmailMessage()
        message["Subject"] = "HuTaoChatCore 重置密码"
        message["From"] = self._settings.from_address
        message["To"] = email
        message.set_content(
            "请在 HuTaoChatCore 的重置密码页面提交以下重置令牌：\n\n"
            f"{token}\n\n"
            f"有效期至：{expires_at.isoformat()}\n"
            "如果不是你本人发起的请求，请忽略此邮件，且不要将令牌分享给他人。"
        )
        client = self._smtp_factory(self._settings.host, self._settings.port)
        try:
            if self._settings.starttls:
                client.starttls()
            client.login(self._settings.username, self._settings.password)
            client.send_message(message)
        finally:
            client.quit()
