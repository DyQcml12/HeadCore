from __future__ import annotations

from pathlib import Path


AUTH_SCRIPT = Path(__file__).parents[1] / "app" / "static" / "auth" / "app.js"


def _handler_block(source: str, form_id: str, next_form_id: str | None = None) -> str:
    start = source.index(f'$("#{form_id}").addEventListener("submit"')
    end = source.find(f'$("#{next_form_id}").addEventListener("submit"', start) if next_form_id else len(source)
    return source[start:end]


def test_auth_form_payloads_are_captured_before_controls_are_disabled() -> None:
    source = AUTH_SCRIPT.read_text(encoding="utf-8")
    for form_id, next_form_id, endpoint in (
        ("resetRequestForm", "resetConfirmForm", "password-reset/request"),
        ("resetConfirmForm", "registerForm", "password-reset/confirm"),
        ("verifyForm", None, "verify-email"),
    ):
        block = _handler_block(source, form_id, next_form_id)
        payload_index = block.index("const payload = Object.fromEntries(new FormData(form));")
        busy_index = block.index("setBusy(form, true")
        post_index = block.index(f'await post("{endpoint}", payload);')
        assert payload_index < busy_index < post_index
