import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.registration import RegistrationError, RegistrationService, PendingWebUser
from app.auth.sessions import hash_opaque_token


class FakeRegistrationRepository:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.pending: PendingWebUser | None = None

    async def create_pending_user(self, **values: object) -> PendingWebUser:
        self.created = values
        self.pending = PendingWebUser(
            id="user-1",
            profile_id="profile-1",
            email_normalized=str(values["email_normalized"]),
        )
        return self.pending

    async def consume_email_verification_token(
        self, *, token_hash: str, now: datetime
    ) -> PendingWebUser | None:
        if self.created is None or token_hash != self.created["verification_token_hash"]:
            return None
        return self.pending


def test_registration_persists_only_a_hash_of_the_email_verification_token() -> None:
    repository = FakeRegistrationRepository()
    service = RegistrationService(repository, verification_lifetime=timedelta(minutes=30))
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)

    result = asyncio.run(
        service.register(
            email=" Reader@Example.com ",
            display_name="Reader",
            password="SafePassword!2026",
            now=now,
        )
    )

    assert result.email_normalized == "reader@example.com"
    assert repository.created is not None
    assert result.verification_token not in str(repository.created)
    assert repository.created["verification_token_hash"] == hash_opaque_token(
        result.verification_token
    )
    assert repository.created["verification_expires_at"] == now + timedelta(minutes=30)


def test_email_verification_activates_only_an_unexpired_one_time_token() -> None:
    repository = FakeRegistrationRepository()
    service = RegistrationService(repository)
    registration = asyncio.run(
        service.register(
            email="reader@example.com",
            display_name="Reader",
            password="SafePassword!2026",
        )
    )

    verified = asyncio.run(service.verify_email(token=registration.verification_token))

    assert verified.profile_id == "profile-1"
    with pytest.raises(RegistrationError, match="invalid or expired verification token"):
        asyncio.run(service.verify_email(token="invalid"))
