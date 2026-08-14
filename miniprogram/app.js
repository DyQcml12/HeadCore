const { apiBaseUrl } = require("./config");
const { createApiClient } = require("./utils/api");
const { createSessionStore } = require("./utils/session");

function requestWithWx(options) {
  return new Promise((resolve, reject) => {
    wx.request({ ...options, timeout: 20000, success: resolve, fail: reject });
  });
}

function uploadWithWx(options) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({ ...options, success: resolve, fail: reject });
  });
}

App({
  globalData: {
    api: null,
    session: null,
    account: null,
    apiConfigured: false,
  },

  onLaunch() {
    const session = createSessionStore(wx);
    this.globalData.session = session;
    this.globalData.api = createApiClient({
      baseUrl: apiBaseUrl,
      request: requestWithWx,
      uploadFile: uploadWithWx,
      session,
    });
    this.globalData.apiConfigured = Boolean(apiBaseUrl.trim());
  },
});
