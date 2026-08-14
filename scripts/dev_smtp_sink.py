"""Local development SMTP sink for email-verification integration.

Receives mail only (never sends), writes each message to
``logs/dev-smtp-inbox/`` and echoes the body so verification codes can be
read without any real mailbox. Accepts any AUTH credentials.

Usage:
    python scripts/dev_smtp_sink.py

The control-center launcher starts this automatically when ``.env`` has
``SMTP_HOST=127.0.0.1`` and nothing is listening on port 1025 yet. Replace
the SMTP_* settings with a real mailbox to stop using it.
"""
from __future__ import annotations

import asyncio
import base64
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INBOX = PROJECT_ROOT / "logs" / "dev-smtp-inbox"
HOST, PORT = "127.0.0.1", 1025

_sequence = 0


def _next_inbox_path() -> Path:
    global _sequence
    _sequence += 1
    INBOX.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return INBOX / f"msg-{stamp}-{_sequence:03d}.eml"


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    async def send(line: str) -> None:
        writer.write((line + "\r\n").encode("utf-8"))
        await writer.drain()

    async def recv() -> str:
        data = await reader.readline()
        return data.decode("utf-8", errors="replace").rstrip("\r\n")

    await send("220 local-dev-smtp ESMTP ready")
    in_auth_login = False
    while True:
        line = await recv()
        if not line:
            break
        upper = line.upper()
        if in_auth_login:
            in_auth_login = False
            await send("235 2.7.0 authentication successful")
            continue
        if upper.startswith("EHLO"):
            await send("250-local-dev-smtp")
            await send("250-AUTH PLAIN LOGIN")
            await send("250 8BITMIME")
        elif upper.startswith("HELO"):
            await send("250 local-dev-smtp")
        elif upper.startswith("AUTH PLAIN"):
            await send("235 2.7.0 authentication successful")
        elif upper.startswith("AUTH LOGIN"):
            in_auth_login = True
            await send("334 " + base64.b64encode(b"Username:").decode())
        elif upper.startswith("MAIL FROM:") or upper.startswith("RCPT TO:"):
            await send("250 2.1.0 ok")
        elif upper == "DATA":
            await send("354 end with <CR><LF>.<CR><LF>")
            body_lines: list[str] = []
            while True:
                data_line = await recv()
                if data_line == ".":
                    break
                body_lines.append(data_line if not data_line.startswith("..") else data_line[1:])
            path = _next_inbox_path()
            path.write_text("\n".join(body_lines), encoding="utf-8")
            print(f"[dev-smtp] saved {path.relative_to(PROJECT_ROOT)}")
            for chunk in "\n".join(body_lines).split("\n"):
                stripped = chunk.strip()
                if stripped and not stripped.startswith((
                    "Content-", "Subject:", "From:", "To:", "MIME-",
                )):
                    print(f"  BODY> {stripped}")
            await send("250 2.0.0 queued")
        elif upper.startswith("QUIT"):
            await send("221 2.0.0 bye")
            break
        elif upper.startswith(("RSET", "NOOP")):
            await send("250 2.0.0 ok")
        else:
            await send("250 2.0.0 ok")
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass


async def main() -> None:
    server = await asyncio.start_server(handle, HOST, PORT)
    print(f"dev smtp sink listening on {HOST}:{PORT}, inbox={INBOX.relative_to(PROJECT_ROOT)}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("dev smtp sink stopped")
