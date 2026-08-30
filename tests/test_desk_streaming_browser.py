import asyncio
from collections.abc import AsyncIterator
import shutil
import socket
import subprocess
import threading
import time

import pytest
import uvicorn

from app import main
from app.voice_chat.web_tts import WebVoiceReplyStore


def _playwright_available(node: str) -> bool:
    try:
        probe = subprocess.run(
            [node, "-e", "require('playwright')"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return probe.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _start_local_server(port: int) -> tuple[uvicorn.Server, threading.Thread]:
    server = uvicorn.Server(
        uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("local FastAPI server did not start for Desk browser test")
    return server, thread


def test_desk_displays_utf8_streamed_reply_without_using_plain_chat(monkeypatch) -> None:
    """Catch a Desk regression that silently switches text chat back to /api/v1/chat."""

    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required for the Desk browser test")
    if not _playwright_available(node):
        pytest.skip("playwright is not installed; Desk browser test requires playwright + Microsoft Edge")

    class StreamOnlyRuntime:
        plain_chat_calls = 0

        async def handle(self, *_args: object, **_kwargs: object) -> object:
            self.plain_chat_calls += 1
            raise RuntimeError("Desk text chat must use the streaming endpoint")

        async def stream(self, *_args: object, **_kwargs: object) -> AsyncIterator[str]:
            yield "unused"

    runtime = StreamOnlyRuntime()

    async def allow_local_web_request(request: main.ChatRequest, *_args: object) -> main.ChatRequest:
        return request

    async def split_utf8_stream(_source: object) -> AsyncIterator[bytes]:
        # Each boundary bisects a Chinese UTF-8 character. The browser must retain decoder state.
        for part in (b"\xe6\xb5", b"\x81\xe5", b"\xbc\x8f\xe5\x9b", b"\x9e\xe7\xad\x94"):
            yield part
            await asyncio.sleep(0.08)

    monkeypatch.setattr(main, "_authenticated_web_request", allow_local_web_request)
    monkeypatch.setattr(main, "build_head_runtime", lambda: runtime)
    monkeypatch.setattr(main, "stream_core_api_text", split_utf8_stream)
    monkeypatch.setattr(main, "should_use_database_v2", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(main, "public_web_tts_configured", True)
    monkeypatch.setattr(
        main,
        "web_voice_reply_store",
        WebVoiceReplyStore(reply_ttl_seconds=300, min_interval_seconds=0),
    )

    port = _unused_local_port()
    server, thread = _start_local_server(port)
    browser_script = r'''
const { chromium } = require("playwright");
const baseUrl = process.argv[1];
const expectedReply = "流式回答";

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const consoleErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    await page.route("**/api/v1/auth/status", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authentication_enabled: false, registration_enabled: false, password_reset_enabled: false }),
    }));
    await page.route("**/health", (route) => route.fulfill({ status: 200, body: '{"status":"ok"}' }));
    await page.route("**/api/v1/voice/status", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: true, provider_ready: true, max_reply_chars: 800 }),
    }));
    await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({
      status: 200,
      contentType: "audio/mpeg",
      body: "ID3fake-audio",
    }));
    await page.goto(`${baseUrl}/desk`, { waitUntil: "domcontentloaded" });
    await page.locator("#chatInput").fill("请用流式回答");
    await page.locator("#chatInput").press("Enter");
    await page.waitForFunction((reply) => {
      return [...document.querySelectorAll(".message.assistant p")]
        .some((node) => node.textContent === reply);
    }, expectedReply, { timeout: 5000 });

    const replies = await page.locator(".message.assistant p").allTextContents();
    if (!replies.includes(expectedReply)) throw new Error(`expected streamed reply, got: ${replies.join(" | ")}`);
    if (await page.locator(".thinking-status.error").count()) throw new Error("stream request rendered an error thinking state");
    await page.waitForFunction(() => document.body.getAttribute("aria-busy") === "false", { timeout: 5000 });
    const voiceButton = page.locator("[data-reply-voice]");
    if (await voiceButton.count() !== 1) throw new Error("streamed reply did not expose one voice playback control");
    const voiceRequestPromise = page.waitForRequest((request) => {
      return request.method() === "POST" && request.url().endsWith("/api/v1/voice/synthesize");
    });
    await voiceButton.click();
    const voiceRequest = await voiceRequestPromise;
    const voicePayload = voiceRequest.postDataJSON();
    if (!voicePayload.reply_id || voicePayload.text) throw new Error("voice playback sent an unsafe request payload");
    const input = page.locator("#chatInput");
    await input.fill("第一行\n第二行");
    const multilineHeight = await input.evaluate((node) => node.getBoundingClientRect().height);
    if (multilineHeight <= 48) throw new Error(`composer did not grow for multiline input: ${multilineHeight}`);
    if (await page.locator("#sendButton").isDisabled()) throw new Error("composer remained busy after streamed reply");
    if (await page.evaluate(() => localStorage.getItem("personacore_desk_input_draft")) !== "第一行\n第二行") {
      throw new Error("composer draft was not stored locally");
    }

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.body.getAttribute("aria-busy") === "false", { timeout: 5000 });
    if (await page.locator("#chatInput").inputValue() !== "第一行\n第二行") {
      throw new Error("composer draft was not restored after reload");
    }

    await page.route("**/api/v1/chat/stream", (route) => route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "temporary failure" }),
    }), { times: 1 });
    await page.locator("#chatInput").fill("重试逻辑");
    await page.locator("#chatInput").press("Enter");
    await page.locator(".message-retry-action").waitFor({ state: "visible", timeout: 5000 });
    await page.waitForFunction(() => document.body.getAttribute("aria-busy") === "false", { timeout: 5000 });
    await page.locator(".message-retry-action").click();
    await page.waitForFunction((reply) => {
      return [...document.querySelectorAll(".message.assistant p")]
        .some((node) => node.textContent === reply);
    }, expectedReply, { timeout: 5000 });
    const retriedUserMessages = await page.locator(".message.user p").allTextContents();
    if (retriedUserMessages.filter((text) => text === "重试逻辑").length !== 1) {
      throw new Error("retry duplicated the user message");
    }
    if (await page.evaluate(() => localStorage.getItem("personacore_desk_input_draft")) !== null) {
      throw new Error("sent composer draft was not cleared");
    }

    await page.evaluate(() => {
      const messages = document.querySelector("#messages");
      for (let index = 0; index < 30; index += 1) {
        const article = document.createElement("article");
        article.className = "message assistant";
        article.style.minHeight = "72px";
        article.style.flex = "0 0 72px";
        article.textContent = `scroll fixture ${index}`;
        messages.append(article);
      }
      messages.scrollTop = 0;
      messages.dispatchEvent(new Event("scroll"));
    });
    await page.locator("#scrollToLatest").waitFor({ state: "visible", timeout: 3000 });
    await page.locator("#scrollToLatest").click();
    await page.waitForFunction(() => {
      const node = document.querySelector("#messages");
      return node.scrollHeight - node.scrollTop - node.clientHeight < 72;
    }, undefined, { timeout: 3000 });
    await page.waitForFunction(() => document.body.getAttribute("aria-busy") === "false", { timeout: 5000 });
    const previousSessionId = await page.evaluate(() => localStorage.getItem("deskSessionId"));
    await page.locator("#newSessionAction").click();
    await page.waitForLoadState("domcontentloaded");
    await page.waitForFunction((previous) => {
      return localStorage.getItem("deskSessionId") !== previous
        && Boolean(document.querySelector(".conversation-welcome"));
    }, previousSessionId, { timeout: 5000 });
    if (await page.locator(".message").count()) throw new Error("new session did not clear the sandbox messages");
    const unexpectedConsoleErrors = consoleErrors.filter((message) => {
      return !message.includes("status of 503 (Service Unavailable)");
    });
    if (unexpectedConsoleErrors.length) {
      throw new Error(`browser console errors: ${unexpectedConsoleErrors.join(" | ")}`);
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
'''
    try:
        completed = subprocess.run(
            [node, "-e", browser_script, f"http://127.0.0.1:{port}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert runtime.plain_chat_calls == 0
