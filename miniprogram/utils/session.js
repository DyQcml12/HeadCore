const CHAT_SESSION_KEY = "hutao_mini_chat_session_id";
const CSRF_TOKEN_KEY = "hutao_mini_csrf_token";
const ACCESS_TOKEN_KEY = "hutao_mini_access_token";

function defaultSessionId() {
  return `mini-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function createSessionStore(storage, { createSessionId = defaultSessionId } = {}) {
  if (!storage || typeof storage.getStorageSync !== "function" || typeof storage.setStorageSync !== "function") {
    throw new TypeError("a mini-program storage adapter is required");
  }

  function getChatSessionId() {
    const stored = storage.getStorageSync(CHAT_SESSION_KEY);
    if (typeof stored === "string" && stored.trim()) return stored;
    const sessionId = createSessionId();
    storage.setStorageSync(CHAT_SESSION_KEY, sessionId);
    return sessionId;
  }

  return {
    getChatSessionId,
    getCsrfToken() {
      const stored = storage.getStorageSync(CSRF_TOKEN_KEY);
      return typeof stored === "string" ? stored : "";
    },
    setCsrfToken(value) {
      storage.setStorageSync(CSRF_TOKEN_KEY, String(value || ""));
    },
    getAccessToken() {
      const stored = storage.getStorageSync(ACCESS_TOKEN_KEY);
      return typeof stored === "string" ? stored : "";
    },
    setAccessToken(value) {
      storage.setStorageSync(ACCESS_TOKEN_KEY, String(value || ""));
    },
    clear() {
      if (typeof storage.removeStorageSync === "function") {
        storage.removeStorageSync(CSRF_TOKEN_KEY);
        storage.removeStorageSync(ACCESS_TOKEN_KEY);
      } else {
        storage.setStorageSync(CSRF_TOKEN_KEY, "");
        storage.setStorageSync(ACCESS_TOKEN_KEY, "");
      }
    },
  };
}

module.exports = { createSessionStore };
