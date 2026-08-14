class ApiClientError extends Error {
  constructor(code, message, statusCode) {
    super(message);
    this.name = "ApiClientError";
    this.code = code;
    this.statusCode = statusCode;
  }
}

function normalizeBaseUrl(value) {
  const baseUrl = String(value || "").trim().replace(/\/+$/, "");
  if (!baseUrl) return "";
  if (!/^https?:\/\/[^/?#]+$/i.test(baseUrl)) {
    throw new ApiClientError("api_base_url_invalid", "API address must be an origin URL");
  }
  return baseUrl;
}

function readResponseData(data) {
  if (typeof data !== "string") return data || {};
  try {
    return JSON.parse(data);
  } catch {
    throw new ApiClientError("invalid_response", "The server returned an unreadable response");
  }
}

function responseError(response) {
  const data = readResponseData(response.data);
  const detail = typeof data.detail === "string" ? data.detail : "";
  if (response.statusCode === 401) {
    return new ApiClientError("authentication_required", detail || "Please sign in first", response.statusCode);
  }
  if (response.statusCode === 403) {
    return new ApiClientError("request_rejected", detail || "The request was rejected", response.statusCode);
  }
  if (response.statusCode === 429) {
    return new ApiClientError("rate_limited", detail || "Please try again later", response.statusCode);
  }
  return new ApiClientError("request_failed", detail || "The request could not be completed", response.statusCode);
}

function headerValue(headers, name) {
  const target = name.toLowerCase();
  for (const [key, value] of Object.entries(headers || {})) {
    if (key.toLowerCase() === target && typeof value === "string") return value;
  }
  return "";
}

function createApiClient({ baseUrl, request, uploadFile, session }) {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  if (typeof request !== "function" || typeof uploadFile !== "function") {
    throw new TypeError("request and uploadFile transports are required");
  }
  if (
    !session
    || typeof session.getCsrfToken !== "function"
    || typeof session.setCsrfToken !== "function"
    || typeof session.getAccessToken !== "function"
    || typeof session.setAccessToken !== "function"
  ) {
    throw new TypeError("a mini-program session store is required");
  }

  function endpoint(path) {
    if (!normalizedBaseUrl) {
      throw new ApiClientError("api_base_url_missing", "Set apiBaseUrl before using the mini program");
    }
    return `${normalizedBaseUrl}${path}`;
  }

  function headers({ json = false, csrf = false, auth = true } = {}) {
    const value = {};
    if (json) value["content-type"] = "application/json";
    const accessToken = session.getAccessToken();
    if (auth && accessToken) value.Authorization = `Bearer ${accessToken}`;
    const csrfToken = session.getCsrfToken();
    if (csrf && csrfToken) value["X-CSRF-Token"] = csrfToken;
    return value;
  }

  async function send(path, {
    method = "GET", data, json = false, csrf = false, auth = true, responseType, withResponse = false,
  } = {}) {
    const options = {
      url: endpoint(path),
      method,
      data,
      header: headers({ json, csrf, auth }),
    };
    if (responseType) options.responseType = responseType;
    const response = await request(options);
    if (response.statusCode < 200 || response.statusCode >= 300) throw responseError(response);
    const payload = responseType === "arraybuffer" ? response.data : readResponseData(response.data);
    return withResponse ? { payload, headers: response.header || {} } : payload;
  }

  return {
    getAuthStatus: () => send("/api/v1/auth/status", { auth: false }),
    async login({ email, password }) {
      const data = await send("/api/v1/auth/mobile/login", {
        method: "POST",
        data: { email, password },
        json: true,
        auth: false,
      });
      if (
        typeof data.csrf_token !== "string"
        || !data.csrf_token
        || typeof data.access_token !== "string"
        || !data.access_token
      ) {
        throw new ApiClientError("invalid_login_response", "The login response did not include a session token");
      }
      session.setCsrfToken(data.csrf_token);
      session.setAccessToken(data.access_token);
      return data;
    },
    register: ({ email, displayName, password }) => send("/api/v1/auth/register", {
      method: "POST",
      data: { email, display_name: displayName, password },
      json: true,
    }),
    verifyEmail: ({ token }) => send("/api/v1/auth/verify-email", {
      method: "POST",
      data: { token },
      json: true,
    }),
    requestPasswordReset: ({ email }) => send("/api/v1/auth/password-reset/request", {
      method: "POST",
      data: { email },
      json: true,
    }),
    confirmPasswordReset: ({ token, password }) => send("/api/v1/auth/password-reset/confirm", {
      method: "POST",
      data: { token, password },
      json: true,
    }),
    getCurrentAccount: () => send("/api/v1/auth/me"),
    async logout() {
      await send("/api/v1/auth/logout", { method: "POST", csrf: true });
      session.clear();
    },
    async sendChat({ userInput, sessionId, userId }) {
      const response = await send("/api/v1/chat", {
        method: "POST",
        data: {
          user_input: userInput,
          session_id: sessionId,
          user_id: userId,
          input_source: "text",
        },
        json: true,
        csrf: true,
        withResponse: true,
      });
      return { ...response.payload, replyId: headerValue(response.headers, "X-Hutao-Reply-Id") };
    },
    synthesizeReply: ({ replyId, sessionId, userId }) => send("/api/v1/voice/synthesize", {
      method: "POST",
      data: {
        reply_id: replyId,
        session_id: sessionId,
        user_id: userId,
      },
      json: true,
      csrf: true,
      responseType: "arraybuffer",
    }),
    async sendAudio({ filePath, sessionId, userId }) {
      const response = await uploadFile({
        url: endpoint("/api/v1/audio/chat/file"),
        filePath,
        name: "file",
        formData: { session_id: sessionId, user_id: userId },
        header: headers({ csrf: true }),
      });
      if (response.statusCode < 200 || response.statusCode >= 300) throw responseError(response);
      return readResponseData(response.data);
    },
    listMemories: () => send("/api/v1/memories"),
    deleteMemory: (memoryId) => send(`/api/v1/memories/${encodeURIComponent(memoryId)}`, {
      method: "DELETE",
      csrf: true,
    }),
    getDialogueContext: () => send("/api/v1/dialogue-context"),
  };
}

module.exports = { ApiClientError, createApiClient };
