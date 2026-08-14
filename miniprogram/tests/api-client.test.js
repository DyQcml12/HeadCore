const assert = require("node:assert/strict");
const test = require("node:test");

const { createApiClient, ApiClientError } = require("../utils/api");

function createSessionStore() {
  let csrfToken = "";
  let accessToken = "";
  return {
    getCsrfToken: () => csrfToken,
    setCsrfToken: (value) => { csrfToken = value; },
    getAccessToken: () => accessToken,
    setAccessToken: (value) => { accessToken = value; },
    clear: () => { csrfToken = ""; accessToken = ""; },
  };
}

function createTransport(responses = []) {
  const calls = [];
  return {
    calls,
    request: async (options) => {
      calls.push(options);
      return responses.shift() || { statusCode: 200, data: {} };
    },
    uploadFile: async (options) => {
      calls.push(options);
      return responses.shift() || { statusCode: 200, data: "{}" };
    },
  };
}

test("login stores the CSRF token and chat uses only the public chat endpoint", async () => {
  const session = createSessionStore();
  const transport = createTransport([
    { statusCode: 200, data: { profile_id: "profile-7", csrf_token: "csrf-7", access_token: "mini-token-7" } },
    {
      statusCode: 200,
      data: { text: "收到", provider: "test", model: "test", used_live_api: false },
      header: { "x-hutao-reply-id": "reply-7" },
    },
  ]);
  const api = createApiClient({
    baseUrl: "https://api.example.test",
    request: transport.request,
    uploadFile: transport.uploadFile,
    session,
  });

  await api.login({ email: "reader@example.com", password: "SafePassword!2026" });
  const reply = await api.sendChat({ userInput: "晚上好", sessionId: "mini-session", userId: "profile-7" });

  assert.equal(session.getCsrfToken(), "csrf-7");
  assert.equal(session.getAccessToken(), "mini-token-7");
  assert.equal(reply.replyId, "reply-7");
  assert.deepEqual(transport.calls[0], {
    url: "https://api.example.test/api/v1/auth/mobile/login",
    method: "POST",
    data: { email: "reader@example.com", password: "SafePassword!2026" },
    header: { "content-type": "application/json" },
  });
  assert.deepEqual(transport.calls[1], {
    url: "https://api.example.test/api/v1/chat",
    method: "POST",
    data: {
      user_input: "晚上好",
      session_id: "mini-session",
      user_id: "profile-7",
      input_source: "text",
    },
    header: {
      "content-type": "application/json",
      "X-CSRF-Token": "csrf-7",
      Authorization: "Bearer mini-token-7",
    },
  });
});

test("audio upload and memory deletion keep the authenticated public-api boundary", async () => {
  const session = createSessionStore();
  session.setCsrfToken("csrf-audio");
  session.setAccessToken("mini-token-audio");
  const transport = createTransport([
    { statusCode: 200, data: JSON.stringify({ transcript_text: "你好", reply_text: "我在听" }) },
    { statusCode: 200, data: { deleted: true } },
  ]);
  const api = createApiClient({
    baseUrl: "https://api.example.test/",
    request: transport.request,
    uploadFile: transport.uploadFile,
    session,
  });

  await api.sendAudio({ filePath: "/tmp/voice.mp3", sessionId: "mini-session", userId: "profile-7" });
  await api.deleteMemory("memory-12");

  assert.deepEqual(transport.calls[0], {
    url: "https://api.example.test/api/v1/audio/chat/file",
    filePath: "/tmp/voice.mp3",
    name: "file",
    formData: { session_id: "mini-session", user_id: "profile-7" },
    header: { "X-CSRF-Token": "csrf-audio", Authorization: "Bearer mini-token-audio" },
  });
  assert.deepEqual(transport.calls[1], {
    url: "https://api.example.test/api/v1/memories/memory-12",
    method: "DELETE",
    data: undefined,
    header: { "X-CSRF-Token": "csrf-audio", Authorization: "Bearer mini-token-audio" },
  });
  assert.equal(transport.calls.some((call) => call.url.includes("/api/control/") || call.url.includes("/workbench")), false);
});

test("a missing API address fails locally without sending a request", async () => {
  const session = createSessionStore();
  const transport = createTransport();
  const api = createApiClient({
    baseUrl: "",
    request: transport.request,
    uploadFile: transport.uploadFile,
    session,
  });

  await assert.rejects(
    () => api.getAuthStatus(),
    (error) => error instanceof ApiClientError && error.code === "api_base_url_missing",
  );
  assert.equal(transport.calls.length, 0);
});

test("voice playback requests server-saved reply audio as an ArrayBuffer", async () => {
  const session = createSessionStore();
  session.setCsrfToken("csrf-voice");
  session.setAccessToken("mini-token-voice");
  const audio = new Uint8Array([73, 68, 51]).buffer;
  const transport = createTransport([{ statusCode: 200, data: audio }]);
  const api = createApiClient({
    baseUrl: "https://api.example.test",
    request: transport.request,
    uploadFile: transport.uploadFile,
    session,
  });

  const result = await api.synthesizeReply({ replyId: "reply-id-0123456789", sessionId: "mini-session", userId: "profile-7" });

  assert.equal(result, audio);
  assert.deepEqual(transport.calls[0], {
    url: "https://api.example.test/api/v1/voice/synthesize",
    method: "POST",
    data: {
      reply_id: "reply-id-0123456789",
      session_id: "mini-session",
      user_id: "profile-7",
    },
    header: {
      "content-type": "application/json",
      "X-CSRF-Token": "csrf-voice",
      Authorization: "Bearer mini-token-voice",
    },
    responseType: "arraybuffer",
  });
});
