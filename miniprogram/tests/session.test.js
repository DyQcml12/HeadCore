const assert = require("node:assert/strict");
const test = require("node:test");

const { createSessionStore } = require("../utils/session");

function createStorage() {
  const values = new Map();
  return {
    getStorageSync: (key) => values.get(key),
    setStorageSync: (key, value) => values.set(key, value),
    removeStorageSync: (key) => values.delete(key),
  };
}

test("session store persists a generated chat session but clears only CSRF on logout", () => {
  const storage = createStorage();
  const session = createSessionStore(storage, { createSessionId: () => "mini-session-fixed" });

  assert.equal(session.getChatSessionId(), "mini-session-fixed");
  assert.equal(session.getChatSessionId(), "mini-session-fixed");
  session.setCsrfToken("csrf-1");
  assert.equal(session.getCsrfToken(), "csrf-1");
  session.setAccessToken("mini-token-1");
  assert.equal(session.getAccessToken(), "mini-token-1");

  session.clear();

  assert.equal(session.getCsrfToken(), "");
  assert.equal(session.getAccessToken(), "");
  assert.equal(session.getChatSessionId(), "mini-session-fixed");
});
