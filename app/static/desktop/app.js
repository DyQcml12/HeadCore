const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  config: null,
  busy: false,
  sessionId: localStorage.getItem("hutao.desktop.session") || `desktop-${crypto.randomUUID()}`,
  userId: localStorage.getItem("hutao.desktop.user") || `desktop-user-${crypto.randomUUID()}`,
  attachment: null,
};
localStorage.setItem("hutao.desktop.session", state.sessionId);
localStorage.setItem("hutao.desktop.user", state.userId);

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )hutao_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function request(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const csrf = csrfToken();
  if (csrf && (options.method || "GET").toUpperCase() !== "GET") headers.set("X-CSRF-Token", csrf);
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof data?.detail === "string" ? data.detail : `请求失败（${response.status}）`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = `toast${error ? " error" : ""}`;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 3600);
}

function personaName() {
  const name = (state.config?.persona?.display_name || "助手").trim();
  return name || "助手";
}

function personaAvatarText() {
  return [...personaName()][0] || "助";
}

function renderPersona() {
  const name = personaName();
  const avatar = personaAvatarText();
  $("#personaName").textContent = name;
  $("#personaAvatar").textContent = avatar;
  $("#welcomeAuthor").textContent = name;
  $("#welcomeAvatar").textContent = avatar;
  $("#welcomeText").textContent = `你好，我是${name}。先把模型接好，我们就能开始聊天了。你也可以把一张图片拖进来，让我看看眼前的东西。`;
  $("#chatTitle").textContent = `和 ${name} 聊聊`;
}

function showView(name) {
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
  $$([".view"]).forEach((panel) => {
    const active = panel.dataset.viewPanel === name;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  $("#sidebar")?.classList.remove("open");
}

function formConfig() {
  const existing = state.config || {};
  return {
    text: {
      ...(existing.text || {}),
      provider: $("#textProvider").value.trim() || "OpenAI-compatible",
      model: $("#textModel").value.trim(),
      base_url: $("#textBaseUrl").value.trim(),
      capability: $("#textCapability").value,
      ...( $("#textApiKey").value ? { api_key: $("#textApiKey").value } : {}),
    },
    vision: {
      ...(existing.vision || {}),
      enabled: $("#visionEnabled").checked,
      model: $("#visionModel").value.trim(),
      base_url: $("#visionBaseUrl").value.trim(),
      ...( $("#visionApiKey").value ? { api_key: $("#visionApiKey").value } : {}),
    },
    memory: {
      ...(existing.memory || {}),
      enabled: $("#memoryEnabled").checked,
      auto_save: $("#memoryAuto").checked,
    },
    persona: {
      ...(existing.persona || {}),
      id: $("#personaId").value,
      display_name: $("#personaName").value.trim() || "助手",
      voice_profile: $("#voiceProfile").value,
    },
    computer_control: {
      ...(existing.computer_control || {}),
      mode: $("#controlMode").value,
      allow_shell: $("#allowShell").checked,
      allow_file_delete: false,
      allowed_apps: $("#allowBrowser").checked ? ["browser"] : [],
    },
  };
}

function renderConfig(config) {
  state.config = config || {};
  const text = state.config.text || {};
  const vision = state.config.vision || {};
  const memory = state.config.memory || {};
  const persona = state.config.persona || {};
  const controls = state.config.computer_control || {};
  $("#textProvider").value = text.provider || "DeepSeek";
  $("#textModel").value = text.model || "deepseek-v4-pro";
  $("#textBaseUrl").value = text.base_url || "https://api.deepseek.com";
  $("#textCapability").value = text.capability || "text-only";
  $("#visionEnabled").checked = vision.enabled !== false;
  $("#visionModel").value = vision.model || "qwen2.5-vl:7b";
  $("#visionBaseUrl").value = vision.base_url || "http://127.0.0.1:11434/v1";
  $("#memoryEnabled").checked = memory.enabled !== false;
  $("#memoryAuto").checked = Boolean(memory.auto_save);
  $("#personaId").value = persona.id || "hutao_v1";
  $("#personaName").value = persona.display_name || "助手";
  $("#voiceProfile").value = persona.voice_profile || "hutao_e15";
  renderPersona();
  $("#controlMode").value = controls.mode || "confirm";
  $("#allowBrowser").checked = Array.isArray(controls.allowed_apps) && controls.allowed_apps.includes("browser");
  $("#allowShell").checked = Boolean(controls.allow_shell);
  updateRouteCopy();
}

function setStatus(online, text) {
  $("#topSystemStatus").textContent = text;
  $("#topSystemDot").classList.toggle("ok", online);
}

async function loadStatus() {
  try {
    const status = await request("/api/v1/desktop/status");
    setStatus(true, status.supported_windows ? "Windows 本机服务已连接" : "本机服务已连接");
    $("#railModel").textContent = status.current_provider || "DeepSeek";
    $("#railModelState").textContent = status.text_api_configured ? `${status.current_model} · 已配置` : "等待 API 配置";
    $("#modelMeter").style.width = status.text_api_configured ? "88%" : "28%";
    $("#railMemory").textContent = status.memory_backend || "Qdrant";
    $("#railMemoryState").textContent = status.text_api_configured ? "本机记忆链路待刷新" : "等待文本模型配置";
    $("#chatModelLabel").textContent = `${status.current_provider || "DeepSeek"} · ${status.current_model || "默认模型"}`;
  } catch {
    setStatus(false, "本机服务未连接");
    toast("本机服务没有响应，请确认 FastAPI 已启动。", true);
  }
}

async function loadVoiceStatus() {
  try {
    const voice = await request("/api/v1/desktop/voice/status");
    $("#railVoice").textContent = voice.voice_profile || "声音";
    if (voice.reachable) {
      $("#railVoiceState").textContent = "本机 GPT-SoVITS 已连接";
    } else if (voice.tts_enabled) {
      $("#railVoiceState").textContent = "语音服务未启动（文字版）";
    } else {
      $("#railVoiceState").textContent = "语音未启用（文字版）";
    }
  } catch {
    $("#railVoiceState").textContent = "语音不可用";
  }
}

async function loadConfig() {
  try {
    const data = await request("/api/v1/desktop/config");
    renderConfig(data.config);
    $("#storagePath").textContent = data.paths.data_root;
    $("#dataPath").value = data.paths.data_root;
    $("#memoryPath").textContent = data.paths.config_file;
    $("#settingsSaveState").textContent = data.requires_restart ? "保存后需重启服务" : "本机配置";
    updateRouteCopy();
  } catch (error) {
    toast(error.message || "本地配置读取失败。", true);
  }
}

async function saveConfig(kind = "all") {
  const payload = formConfig();
  if (kind === "text") payload.vision = state.config?.vision || {};
  if (kind === "vision") payload.text = state.config?.text || {};
  try {
    const data = await request("/api/v1/desktop/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderConfig(data.config);
    $("#modelSaveState").textContent = "已保存 · 重启后生效";
    $("#settingsSaveState").textContent = "已保存 · 重启后生效";
    toast(data.message || "配置已保存。", false);
  } catch (error) {
    toast(error.message || "配置保存失败。", true);
  }
}

async function testTextConnection() {
  const button = $("#testText");
  button.disabled = true;
  button.textContent = "测试中…";
  try {
    const data = await request("/api/v1/desktop/config/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formConfig()),
    });
    $("#textState").textContent = "连接成功";
    $("#textState").className = "state-chip safe";
    toast(`${data.provider} · ${data.model} 连接成功。`);
  } catch (error) {
    $("#textState").textContent = "连接失败";
    $("#textState").className = "state-chip";
    toast(error.message || "模型连接失败。", true);
  } finally {
    button.disabled = false;
    button.textContent = "测试连接";
  }
}

function addMessage(role, text, extra = "") {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  if (role === "assistant") {
    const avatar = document.createElement("span");
    avatar.className = "message-avatar";
    avatar.textContent = personaAvatarText();
    article.append(avatar);
  }
  const wrapper = document.createElement("div");
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const author = document.createElement("strong");
  author.textContent = role === "assistant" ? personaName() : "你";
  const time = document.createElement("time");
  time.textContent = extra || "现在";
  meta.append(author, time);
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  wrapper.append(meta, paragraph);
  article.append(wrapper);
  $("#messages").append(article);
  article.scrollIntoView({ behavior: "smooth", block: "end" });
  return paragraph;
}

async function streamChat(text, paragraph = null) {
  const response = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(csrfToken() ? { "X-CSRF-Token": csrfToken() } : {}) },
    credentials: "same-origin",
    body: JSON.stringify({ user_input: text, session_id: state.sessionId, user_id: state.userId, input_source: "text" }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data?.detail === "string" ? data.detail : `聊天请求失败（${response.status}）`);
  }
  if (!response.body) throw new Error("回复流不可读取");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let fullText = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    fullText += decoder.decode(value, { stream: true });
    if (paragraph) paragraph.textContent = fullText;
  }
  fullText += decoder.decode();
  if (paragraph) paragraph.textContent = fullText || "这次没有生成可显示的回复。";
}

async function describeAttachment() {
  const form = new FormData();
  form.append("image", state.attachment.file, state.attachment.file.name);
  form.append("prompt", $("#chatInput").value.trim() || "请描述这张图片中的主要内容，并指出值得注意的细节。");
  const data = await request("/api/v1/desktop/vision/describe", { method: "POST", body: form });
  $("#railVisionState").textContent = data.route === "text-model-multimodal" ? "文本模型直接看图" : "视觉模型已完成观察";
  return data.description;
}

async function sendChat(event) {
  event.preventDefault();
  if (state.busy) return;
  const input = $("#chatInput");
  const text = input.value.trim();
  if (!text && !state.attachment) return;
  state.busy = true;
  $("#sendButton").disabled = true;
  let userText = text || "请看看这张图片。";
  const attachment = state.attachment;
  addMessage("user", attachment ? `${userText}\n[已附加图片：${attachment.file.name}]` : userText);
  input.value = "";
  updateComposer();
  try {
    if (attachment) {
      const description = await describeAttachment();
      userText = `${userText}\n\n[图片视觉观察]\n${description}`;
      clearAttachment();
    }
    const paragraph = addMessage("assistant", "正在组织回复…");
    await streamChat(userText, paragraph);
  } catch (error) {
    addMessage("assistant", error.message || "这次请求没有完成，请检查模型和视觉服务配置。");
    toast(error.message || "请求失败。", true);
  } finally {
    state.busy = false;
    $("#sendButton").disabled = false;
    updateComposer();
  }
}

function updateRouteCopy() {
  const multimodal = $("#textCapability")?.value === "multimodal";
  const enabled = $("#visionEnabled")?.checked !== false;
  const copy = multimodal ? "当前文本模型支持多模态，附图会直接交给文本模型。" : enabled ? "纯文本请求不会调用视觉模型；附图会转交视觉模型。" : "视觉路由已关闭，附图请求将被拒绝。";
  $("#routeHint").textContent = copy;
  if ($("#routeExplain")) $("#routeExplain").textContent = copy;
  if ($("#visionRouteBadge")) $("#visionRouteBadge").textContent = multimodal ? "文本模型直连" : "纯文本 → 视觉模型";
  $("#railVision").textContent = multimodal ? "多模态直连" : "自动路由";
}

function updateComposer() {
  const value = $("#chatInput").value;
  $("#charCount").textContent = `${value.length} / 4000`;
  $("#sendButton").disabled = state.busy || (!value.trim() && !state.attachment);
}

function setAttachment(file) {
  if (!file) return;
  if (!file.type.startsWith("image/") || file.size > 8 * 1024 * 1024) {
    toast("请选择不超过 8 MB 的图片文件。", true);
    return;
  }
  state.attachment = { file };
  $("#attachmentName").textContent = `图片：${file.name}`;
  $("#attachmentPreview").hidden = false;
  updateComposer();
}

function clearAttachment() {
  state.attachment = null;
  $("#imageInput").value = "";
  $("#attachmentPreview").hidden = true;
  updateComposer();
}

async function loadMemories() {
  try {
    const auth = await request("/api/v1/auth/status");
    if (auth.authentication_enabled) {
      $("#memoryPanelState").textContent = "登录后查看";
      $("#memoryList").innerHTML = "<div class=\"empty-state\"><strong>本机账户已启用认证</strong><span>登录后才能读取和删除长期记忆，聊天功能不受影响。</span></div>";
      return;
    }
    const data = await request(`/api/v1/memories?user_id=${encodeURIComponent(state.userId)}&limit=20`);
    const records = Array.isArray(data?.memories) ? data.memories : [];
    $("#memoryCount").textContent = String(records.length);
    $("#memoryPanelState").textContent = `${records.length} 条记录`;
    const list = $("#memoryList");
    list.replaceChildren();
    if (!records.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = "<strong>暂时没有长期记忆</strong><span>开启记忆策略后，经过筛选的内容会出现在这里。</span>";
      list.append(empty);
      return;
    }
    records.forEach((record) => {
      const row = document.createElement("div");
      row.className = "memory-item";
      const type = document.createElement("span");
      type.className = "memory-type";
      type.textContent = record.memory_type || "MEMORY";
      const content = document.createElement("p");
      content.textContent = record.content;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.title = "删除记忆";
      remove.addEventListener("click", async () => {
        await request(`/api/v1/memories/${encodeURIComponent(record.id)}?user_id=${encodeURIComponent(state.userId)}`, { method: "DELETE" });
        row.remove();
        toast("记忆已删除。");
      });
      row.append(type, content, remove);
      list.append(row);
    });
  } catch (error) {
    $("#memoryPanelState").textContent = "暂不可用";
    toast(error.message || "记忆档案读取失败。", true);
  }
}

function initWindowControls() {
  const controls = $("#windowControls");
  if (!controls) return;
  const api = window.pywebview && window.pywebview.api;
  if (!api) {
    controls.hidden = true;
    return;
  }
  controls.hidden = false;
  $("#winMin").addEventListener("click", () => api.minimize());
  $("#winMax").addEventListener("click", () => api.toggle_maximize());
  $("#winClose").addEventListener("click", () => api.close());
}

async function initialize() {
  initWindowControls();
  await Promise.all([loadStatus(), loadConfig(), loadMemories(), loadVoiceStatus()]);
  updateComposer();
}

$$('.nav-item').forEach((item) => item.addEventListener("click", () => showView(item.dataset.view)));
$$('[data-go]').forEach((button) => button.addEventListener("click", () => showView(button.dataset.go)));
$("#mobileMenu").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
$("#chatForm").addEventListener("submit", sendChat);
$("#chatInput").addEventListener("input", updateComposer);
$("#chatInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("#chatForm").requestSubmit();
  }
});
$("#imageInput").addEventListener("change", (event) => setAttachment(event.target.files[0]));
$("#clearAttachment").addEventListener("click", clearAttachment);
$("#newChat").addEventListener("click", () => { state.sessionId = `desktop-${crypto.randomUUID()}`; localStorage.setItem("hutao.desktop.session", state.sessionId); $("#messages").replaceChildren(); addMessage("assistant", `新会话已经准备好。我是${personaName()}，这次想聊什么？`); });
$("#refreshStatus").addEventListener("click", loadStatus);
$("#refreshMemory").addEventListener("click", loadMemories);
$("#saveText").addEventListener("click", () => saveConfig("text"));
$("#saveVision").addEventListener("click", () => saveConfig("vision"));
$("#saveControl").addEventListener("click", () => saveConfig("all"));
$("#testText").addEventListener("click", testTextConnection);
$("#textCapability").addEventListener("change", updateRouteCopy);
$("#visionEnabled").addEventListener("change", updateRouteCopy);
$("#visionInput").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  setAttachment(file);
  showView("chat");
  $("#chatInput").focus();
  toast("图片已加入对话输入框。发送后会按当前视觉路由处理。");
});
$("#dropZone").addEventListener("dragover", (event) => { event.preventDefault(); $("#dropZone").classList.add("dragging"); });
$("#dropZone").addEventListener("dragleave", () => $("#dropZone").classList.remove("dragging"));
$("#dropZone").addEventListener("drop", (event) => { event.preventDefault(); $("#dropZone").classList.remove("dragging"); setAttachment(event.dataTransfer.files[0]); showView("chat"); });
$("#openUninstall").addEventListener("click", () => $("#uninstallDialog").showModal());
$("#launchUninstall").addEventListener("click", async (event) => {
  event.preventDefault();
  try {
    const data = await request("/api/v1/desktop/uninstall", { method: "POST" });
    $("#uninstallDialog").close();
    if (data.launched) {
      toast("已启动卸载程序。卸载时可在向导中选择是否保留数据。", false);
    } else {
      toast(data.message || "未找到卸载程序。", true);
    }
  } catch (error) {
    toast(error.message || "卸载程序启动失败。", true);
  }
});
$("#clearAudit").addEventListener("click", () => toast("开发版暂不清空审计记录。"));
$("#exportData").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), config: state.config }, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "hutao-local-config.json";
  link.click();
  URL.revokeObjectURL(link.href);
  toast("已导出脱敏后的本机配置。密钥不会包含在导出文件中。");
});
$("#deleteData").addEventListener("click", () => {
  $("#uninstallDialog").showModal();
  toast("请在卸载向导中选择是否删除本机数据。", false);
});
for (const selector of ["#memoryEnabled", "#memoryAuto", "#personaId", "#personaName", "#voiceProfile"]) {
  $(selector).addEventListener("change", () => saveConfig("all"));
}

initialize();
