const { ApiClientError } = require("../../utils/api");

const MODES = new Set(["login", "register", "verify", "resetRequest", "resetConfirm"]);

function noticeFor(error) {
  if (error instanceof ApiClientError) {
    if (error.code === "rate_limited") return "操作太频繁了，请稍后再试。";
    if (error.code === "api_base_url_missing") return "尚未配置小程序服务地址。";
  }
  return "请求没有完成，请检查填写内容后重试。";
}

function validPassword(password) {
  return password.length >= 12
    && /[a-z]/.test(password)
    && /[A-Z]/.test(password)
    && /\d/.test(password)
    && /[^A-Za-z0-9\s]/.test(password);
}

Page({
  data: {
    ready: false,
    apiConfigured: false,
    authEnabled: false,
    registrationEnabled: false,
    passwordResetEnabled: false,
    mode: "login",
    submitting: false,
    notice: "",
  },

  onLoad(options) {
    if (MODES.has(options.mode)) this.setData({ mode: options.mode });
  },

  onShow() {
    this.bootstrap();
  },

  async bootstrap() {
    const app = getApp();
    if (!app.globalData.apiConfigured) {
      this.setData({ ready: true, apiConfigured: false });
      return;
    }
    try {
      const status = await app.globalData.api.getAuthStatus();
      this.setData({
        ready: true,
        apiConfigured: true,
        authEnabled: Boolean(status.authentication_enabled),
        registrationEnabled: Boolean(status.registration_enabled),
        passwordResetEnabled: Boolean(status.password_reset_enabled),
      });
    } catch (error) {
      this.setData({ ready: true, apiConfigured: false, notice: noticeFor(error) });
    }
  },

  changeMode(event) {
    const mode = event.currentTarget.dataset.mode;
    if (!MODES.has(mode)) return;
    this.setData({ mode, notice: "" });
  },

  async submit(event) {
    if (this.data.submitting) return;
    const values = event.detail.value || {};
    const mode = this.data.mode;
    const validation = this.validate(mode, values);
    if (validation) {
      this.setData({ notice: validation });
      return;
    }
    this.setData({ submitting: true, notice: "" });
    try {
      const api = getApp().globalData.api;
      if (mode === "login") {
        await api.login({ email: values.email, password: values.password });
        getApp().globalData.account = await api.getCurrentAccount();
        wx.switchTab({ url: "/pages/chat/index" });
        return;
      }
      if (mode === "register") {
        await api.register({ email: values.email, displayName: values.display_name, password: values.password });
        this.setData({ mode: "verify", notice: "验证邮件已发送，请输入邮件中的完整验证码。" });
        return;
      }
      if (mode === "verify") {
        await api.verifyEmail({ token: values.token });
        this.setData({ mode: "login", notice: "邮箱已验证，请使用新账户登录。" });
        return;
      }
      if (mode === "resetRequest") {
        await api.requestPasswordReset({ email: values.email });
        this.setData({ mode: "resetConfirm", notice: "如该邮箱可重置，重置码已发送。" });
        return;
      }
      await api.confirmPasswordReset({ token: values.token, password: values.password });
      this.setData({ mode: "login", notice: "密码已更新，请重新登录。" });
    } catch (error) {
      this.setData({ notice: noticeFor(error) });
    } finally {
      this.setData({ submitting: false });
    }
  },

  validate(mode, values) {
    if (mode === "verify" || mode === "resetConfirm") {
      if (!String(values.token || "").trim()) return "请填写邮件中的验证码。";
    }
    if (mode === "login" || mode === "register" || mode === "resetRequest") {
      if (!/^\S+@\S+\.\S+$/.test(String(values.email || ""))) return "请填写有效的邮箱地址。";
    }
    if (mode === "register") {
      if (!String(values.display_name || "").trim()) return "请填写显示名称。";
      if (!validPassword(String(values.password || ""))) return "密码至少 12 位，并包含大小写字母、数字和符号。";
    }
    if (mode === "login" && !String(values.password || "")) return "请填写密码。";
    if (mode === "resetConfirm" && !validPassword(String(values.password || ""))) {
      return "新密码至少 12 位，并包含大小写字母、数字和符号。";
    }
    return "";
  },
});
