import asyncio
from datetime import datetime, timezone

from app.auth.smtp_delivery import SmtpEmailSettings, SmtpEmailVerificationDelivery


class FakeSmtpClient:
    def __init__(self) -> None:
        self.started_tls = False
        self.logged_in: tuple[str, str] | None = None
        self.message = None
        self.closed = False

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def send_message(self, message) -> None:
        self.message = message

    def quit(self) -> None:
        self.closed = True


def test_smtp_delivery_sends_a_post_body_verification_code_over_starttls() -> None:
    client = FakeSmtpClient()
    settings = SmtpEmailSettings(
        host="smtp.example.com",
        port=587,
        username="mailer",
        password="secret-not-logged",
        from_address="no-reply@example.com",
        starttls=True,
    )
    delivery = SmtpEmailVerificationDelivery(settings, smtp_factory=lambda host, port: client)

    asyncio.run(
        delivery.send_verification(
            email="reader@example.com",
            token="verification-token-value",
            expires_at=datetime(2026, 7, 26, 12, 30, tzinfo=timezone.utc),
        )
    )

    assert client.started_tls is True
    assert client.logged_in == ("mailer", "secret-not-logged")
    assert client.message["To"] == "reader@example.com"
    assert "verification-token-value" in client.message.get_content()
    assert "http" not in client.message.get_content().lower()
    assert client.closed is True


def test_smtp_delivery_sends_password_reset_token_over_starttls() -> None:
    client = FakeSmtpClient()
    settings = SmtpEmailSettings(
        host="smtp.example.com",
        port=587,
        username="mailer",
        password="secret-not-logged",
        from_address="no-reply@example.com",
        starttls=True,
    )
    delivery = SmtpEmailVerificationDelivery(settings, smtp_factory=lambda host, port: client)

    assert hasattr(delivery, "send_password_reset")
    asyncio.run(
        delivery.send_password_reset(
            email="reader@example.com",
            token="reset-token-value",
            expires_at=datetime(2026, 7, 30, 12, 30, tzinfo=timezone.utc),
        )
    )

    assert client.started_tls is True
    assert client.message["To"] == "reader@example.com"
    assert "reset-token-value" in client.message.get_content()
    assert "重置密码" in client.message["Subject"]
    assert "http" not in client.message.get_content().lower()
    assert client.closed is True
