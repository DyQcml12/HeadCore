const { ApiClientError } = require("../../utils/api");

function createMessageId(sequence) {
  return `message-${Date.now()}-${sequence}`;
}

function userMessage(error) {
  if (error instanceof ApiClientError) {
    if (error.code === "authentication_required") return "登录状态已失效，请重新登录。";
    if (error.code === "rate_limited") return "操作太频繁了，稍后再试。";
    if (error.code === "api_base_url_missing") return "尚未配置小程序服务地址。";
  }
  return "连接没有完成，请检查网络后再试。";
}

Page({
  data: {
    ready: false,
    apiConfigured: false,
    authEnabled: false,
    signedIn: false,
    accountName: "访客",
    composerText: "",
    sending: false,
    thinking: false,
    recording: false,
    recordingSeconds: 0,
    recorderAvailable: false,
    playingReplyId: "",
    scrollTarget: "",
    messages: [
      {
        id: "message-welcome",
        role: "hutao",
        author: "胡桃",
        text: "哟，来得正好。今天想从哪一句说起？",
        replyId: "",
      },
    ],
  },

  onLoad() {
    this.messageSequence = 0;
    this.recorder = null;
    this.recordingClock = null;
    this.replyAudio = null;
    this.bindRecorder();
  },

  onShow() {
    this.bootstrap();
  },

  onHide() {
    this.stopRecording();
  },

  onUnload() {
    this.stopRecording();
    if (this.replyAudio) this.replyAudio.destroy();
  },

  async bootstrap() {
    const app = getApp();
    if (!app.globalData.apiConfigured) {
      this.setData({ apiConfigured: false, ready: true });
      return;
    }
    try {
      const status = await app.globalData.api.getAuthStatus();
      if (!status.authentication_enabled) {
        this.setData({
          apiConfigured: true,
          authEnabled: false,
          signedIn: true,
          accountName: "本地体验",
          ready: true,
        });
        return;
      }
      try {
        const account = await app.globalData.api.getCurrentAccount();
        app.globalData.account = account;
        this.setData({
          apiConfigured: true,
          authEnabled: true,
          signedIn: true,
          accountName: account.display_name,
          ready: true,
        });
      } catch (error) {
        if (!(error instanceof ApiClientError) || error.code !== "authentication_required") throw error;
        this.setData({ apiConfigured: true, authEnabled: true, signedIn: false, ready: true });
      }
    } catch (error) {
      this.setData({ apiConfigured: false, ready: true });
      wx.showToast({ title: userMessage(error), icon: "none" });
    }
  },

  bindRecorder() {
    if (typeof wx.getRecorderManager !== "function") return;
    this.recorder = wx.getRecorderManager();
    this.recorder.onStop((result) => this.sendRecording(result.tempFilePath));
    this.recorder.onError(() => {
      this.clearRecordingClock();
      this.setData({ recording: false, recordingSeconds: 0 });
      wx.showToast({ title: "录音未能开始，请检查麦克风权限。", icon: "none" });
    });
    this.setData({ recorderAvailable: true });
  },

  onComposerInput(event) {
    this.setData({ composerText: event.detail.value });
  },

  async sendText() {
    const text = this.data.composerText.trim();
    if (!text || this.data.sending) return;
    if (!this.data.signedIn && this.data.authEnabled) {
      this.goAuth();
      return;
    }
    this.setData({ composerText: "" });
    this.addMessage("user", text);
    await this.requestReply(() => getApp().globalData.api.sendChat({
      userInput: text,
      sessionId: getApp().globalData.session.getChatSessionId(),
      userId: getApp().globalData.account?.profile_id || "mini-local",
    }));
  },

  startRecording() {
    if (!this.recorder || this.data.sending || this.data.recording) return;
    if (!this.data.signedIn && this.data.authEnabled) {
      this.goAuth();
      return;
    }
    this.setData({ recording: true, recordingSeconds: 0 });
    this.recordingClock = setInterval(() => {
      this.setData({ recordingSeconds: this.data.recordingSeconds + 1 });
    }, 1000);
    this.recorder.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: "mp3",
    });
  },

  stopRecording() {
    if (!this.recorder || !this.data.recording) return;
    this.clearRecordingClock();
    this.setData({ recording: false });
    this.recorder.stop();
  },

  clearRecordingClock() {
    if (this.recordingClock) clearInterval(this.recordingClock);
    this.recordingClock = null;
  },

  async sendRecording(filePath) {
    this.clearRecordingClock();
    this.setData({ recording: false, recordingSeconds: 0 });
    if (!filePath) return;
    this.addMessage("user", "语音消息");
    await this.requestReply(async () => {
      const response = await getApp().globalData.api.sendAudio({
        filePath,
        sessionId: getApp().globalData.session.getChatSessionId(),
        userId: getApp().globalData.account?.profile_id || "mini-local",
      });
      return { text: response.reply_text || "我没有听清，再说一次好吗？", replyId: "" };
    });
  },

  async requestReply(request) {
    this.setData({ sending: true, thinking: true });
    try {
      const reply = await request();
      this.addMessage("hutao", reply.text || "我这边暂时没有接上，稍后再试一次吧。", reply.replyId || "");
    } catch (error) {
      if (error instanceof ApiClientError && error.code === "authentication_required") {
        this.setData({ signedIn: false });
      }
      wx.showToast({ title: userMessage(error), icon: "none" });
    } finally {
      this.setData({ sending: false, thinking: false });
    }
  },

  addMessage(role, text, replyId = "") {
    const id = createMessageId(++this.messageSequence);
    const messages = this.data.messages.concat({
      id,
      role,
      author: role === "hutao" ? "胡桃" : this.data.accountName,
      text,
      replyId,
    });
    this.setData({ messages, scrollTarget: id });
  },

  async playReply(event) {
    const replyId = event.currentTarget.dataset.replyid;
    if (!replyId || this.data.playingReplyId) return;
    this.setData({ playingReplyId: replyId });
    try {
      const audioData = await getApp().globalData.api.synthesizeReply({
        replyId,
        sessionId: getApp().globalData.session.getChatSessionId(),
        userId: getApp().globalData.account?.profile_id || "mini-local",
      });
      await this.playAudioBuffer(audioData);
    } catch (error) {
      wx.showToast({ title: "语音回复暂时不可用。", icon: "none" });
      this.setData({ playingReplyId: "" });
    }
  },

  playAudioBuffer(data) {
    const path = `${wx.env.USER_DATA_PATH}/hutao-current-reply.mp3`;
    return new Promise((resolve, reject) => {
      wx.getFileSystemManager().writeFile({
        filePath: path,
        data,
        success: () => {
          if (this.replyAudio) this.replyAudio.destroy();
          const audio = wx.createInnerAudioContext();
          this.replyAudio = audio;
          audio.src = path;
          audio.onEnded(() => this.setData({ playingReplyId: "" }));
          audio.onError(() => this.setData({ playingReplyId: "" }));
          audio.play();
          resolve();
        },
        fail: reject,
      });
    });
  },

  goAuth() {
    wx.navigateTo({ url: "/pages/auth/index" });
  },

  goProfile() {
    wx.switchTab({ url: "/pages/profile/index" });
  },
});
