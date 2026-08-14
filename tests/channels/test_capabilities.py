from __future__ import annotations

from app.channels import capabilities_for, evaluate_delivery
from app.channels.contracts import ChannelResponse, ChannelResponsePart


def test_platform_capability_matrix_is_explicit() -> None:
    core = capabilities_for("core_api")

    assert core.text is True
    assert core.image is False


def test_entirely_unsupported_response_is_not_reported_as_success() -> None:
    response = ChannelResponse(parts=(ChannelResponsePart(kind="typing", content="on"),))

    result = evaluate_delivery(response, capabilities_for("core_api"))

    assert result.status == "unsupported"
    assert result.delivered_parts == ()
