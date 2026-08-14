const { ApiClientError } = require("../../utils/api");

function formatDate(value) {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未记录";
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, "0")}.${String(date.getDate()).padStart(2, "0")}`;
}

function errorMessage(error) {
  if (error instanceof ApiClientError && error.code === "api_base_url_missing") return "尚未配置小程序服务地址。";
  if (error instanceof ApiClientError && error.code === "authentication_required") return "登录状态已失效，请重新登录。";
  return "资料暂时无法读取，请稍后再试。";
}

Page({
  data: {
    ready: false,
    apiConfigured: false,
    signedIn: false,
    account: null,
    activeView: "profile",
    memories: [],
    memoriesLoading: false,
  },

  onShow() {
    this.bootstrap();
  },

  async bootstrap() {
    const app = getApp();
    if (!app.globalData.apiConfigured) {
      this.setData({ ready: true, apiConfigured: false, signedIn: false });
      return;
    }
    try {
      const status = await app.globalData.api.getAuthStatus();
      if (!status.authentication_enabled) {
        this.setData({ ready: true, apiConfigured: true, signedIn: false });
        return;
      }
      const account = await app.globalData.api.getCurrentAccount();
      const viewAccount = {
        ...account,
        initial: Array.from(account.display_name.trim())[0] || "我",
        createdDate: formatDate(account.created_at),
        sessionExpiresDate: formatDate(account.session_expires_at),
      };
      app.globalData.account = viewAccount;
      this.setData({ ready: true, apiConfigured: true, signedIn: true, account: viewAccount });
      if (this.data.activeView === "memory") this.loadMemories();
    } catch (error) {
      this.setData({ ready: true, apiConfigured: true, signedIn: false, account: null });
      if (!(error instanceof ApiClientError) || error.code !== "authentication_required") {
        wx.showToast({ title: errorMessage(error), icon: "none" });
      }
    }
  },

  switchView(event) {
    const activeView = event.currentTarget.dataset.view;
    this.setData({ activeView });
    if (activeView === "memory" && this.data.signedIn) this.loadMemories();
  },

  async loadMemories() {
    if (this.data.memoriesLoading) return;
    this.setData({ memoriesLoading: true });
    try {
      const response = await getApp().globalData.api.listMemories();
      const memories = (response.memories || []).map((memory) => ({
        ...memory,
        displayDate: formatDate(memory.updated_at),
      }));
      this.setData({ memories });
    } catch (error) {
      if (error instanceof ApiClientError && error.code === "authentication_required") {
        this.setData({ signedIn: false, account: null });
      }
      wx.showToast({ title: "记忆暂时无法读取。", icon: "none" });
    } finally {
      this.setData({ memoriesLoading: false });
    }
  },

  deleteMemory(event) {
    const memoryId = event.currentTarget.dataset.memoryid;
    wx.showModal({
      title: "删除这段记忆？",
      content: "删除后不能恢复。",
      confirmColor: "#b96d4f",
      success: async (result) => {
        if (!result.confirm) return;
        try {
          const response = await getApp().globalData.api.deleteMemory(memoryId);
          if (!response.deleted) throw new Error("memory not found");
          this.setData({ memories: this.data.memories.filter((memory) => memory.id !== memoryId) });
        } catch {
          wx.showToast({ title: "删除没有完成，请稍后再试。", icon: "none" });
        }
      },
    });
  },

  async logout() {
    try {
      await getApp().globalData.api.logout();
      getApp().globalData.account = null;
      this.setData({ signedIn: false, account: null, memories: [], activeView: "profile" });
      wx.showToast({ title: "已退出当前账户", icon: "none" });
    } catch {
      wx.showToast({ title: "退出没有完成，请稍后再试。", icon: "none" });
    }
  },

  goAuth() {
    wx.navigateTo({ url: "/pages/auth/index" });
  },
});
