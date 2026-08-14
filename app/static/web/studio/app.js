function localSandboxOwnerId() {
  const saved = localStorage.getItem("deskUserId");
  if (saved && saved !== "desk-local") return saved;
  const created = `desk-${crypto.randomUUID()}`;
  localStorage.setItem("deskUserId", created);
  return created;
}

const state = {
  sessionId: localStorage.getItem("deskSessionId") || `desk-${crypto.randomUUID()}`,
  userId: localSandboxOwnerId(),
  authEnabled: false,
  ready: false,
  busy: false,
  composerMode: "text",
  recorder: null,
  recordingClock: 0,
  recordingStartedAt: 0,
  chunks: [],
  holdingToTalk: false,
  ttsEnabled: false,
  ttsMaxReplyChars: 0,
  voicePlayback: null,
  activePersonaId: "default",
  activePersona: null,
  personas: [],
};

localStorage.setItem("deskSessionId", state.sessionId);
const $ = (selector) => document.querySelector(selector);
const SANDBOX_PERSONA_API = "/api/v1/sandbox/personas";

async function loadPersonas() {
  try {
    const userId = encodeURIComponent(state.userId);
    state.personas = await jsonFetch(`${SANDBOX_PERSONA_API}?user_id=${userId}`);
    renderPersonaOptions();
  } catch {
    state.personas = [];
    renderPersonaOptions();
    toast("本机人格服务暂时无法读取。", true);
  }
}

function updatePersonaDisplay() {
  const draft = state.activePersona;
  $("#personaModel").textContent = draft?.model_label
    ? `${draft.model_label} / 本机人格档案`
    : "基础对话模型 / 未绑定模型档案";
  $("#sessionMode").textContent = draft ? `正在测试：${draft.name}` : "未加载任何人格";
  $("#sandboxDetail").textContent = draft
    ? "此人格已保存到本机服务，并会作为受限表达层注入本次对话。"
    : "从工坊保存人格后，可在这里加载并测试。";
  const warning = $("#personaWarning");
  warning.hidden = !draft;
  if (draft) {
    warning.textContent = "人格设定会影响表达方式，但不能覆盖安全边界、记忆、权限或 HeadCore 状态。";
  }
}

function renderPersonaOptions() {
  const select = $("#personaSelect");
  const drafts = state.personas;
  select.replaceChildren();
  select.add(new Option("选择或加载你的人格模板...", "default"));
  for (const draft of drafts) {
    const traits = Array.isArray(draft.traits) ? draft.traits.join("、") : "";
    select.add(new Option(`${draft.name}${traits ? ` - ${traits}` : ""}`, draft.persona_id));
  }
  const requested = new URLSearchParams(location.search).get("persona");
  const selected = drafts.find(
    (draft) => draft.persona_id === requested || draft.persona_id === state.activePersonaId,
  );
  state.activePersona = selected || null;
  state.activePersonaId = selected?.persona_id || "default";
  select.value = state.activePersonaId;
  updatePersonaDisplay();
}

function selectPersona(personaId) {
  const draft = state.personas.find((item) => item.persona_id === personaId) || null;
  state.activePersonaId = draft?.persona_id || "default";
  state.activePersona = draft;
  $("#personaSelect").value = state.activePersonaId;
  updatePersonaDisplay();
}

function csrfToken() {
  const stored = sessionStorage.getItem("hutao_csrf_token");
  if (stored) return stored;
  const match = document.cookie.match(/(?:^|; )hutao_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.hidden = false;
  node.className = `toast${error ? " error" : ""}`;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => { node.hidden = true; }, 3400);
}

async function jsonFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = csrfToken();
  if (token && (options.method || "GET").toUpperCase() !== "GET") headers.set("X-CSRF-Token", token);
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : data?.detail?.code;
    const error = new Error(detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

const STREAM_TRUNCATED_MARKER = "\uE000stream-truncated\uE001";

async function streamTextFetch(url, options, onChunk) {
  const headers = new Headers(options.headers || {});
  const token = csrfToken();
  if (token) headers.set("X-CSRF-Token", token);
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const error = new Error(typeof data?.detail === "string" ? data.detail : `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (!response.body) throw new Error("回复流不可读取");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let interrupted = false;
  const accept = (raw) => {
    let chunk = raw;
    if (chunk.includes(STREAM_TRUNCATED_MARKER)) {
      interrupted = true;
      chunk = chunk.split(STREAM_TRUNCATED_MARKER).join("");
    }
    if (!chunk) return;
    text += chunk;
    onChunk(chunk, text);
  };
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    accept(decoder.decode(value, { stream: true }));
  }
  accept(decoder.decode());
  return { text, replyId: response.headers.get("X-Hutao-Reply-Id"), interrupted };
}

function messageTime() {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date());
}

function updateHistoryTimestamp() {
  const time = $("#historyTimestamp");
  const now = new Date();
  time.dateTime = now.toISOString();
  time.textContent = messageTime();
}

function setHistoryMenuOpen(open, restoreFocus = false) {
  const trigger = $("#historyMenuButton");
  const menu = $("#historyMenu");
  trigger.setAttribute("aria-expanded", String(open));
  menu.hidden = !open;
  if (open) menu.querySelector('[role="menuitem"]')?.focus();
  else if (restoreFocus) trigger.focus();
}

async function copySessionId() {
  try {
    if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText(state.sessionId);
    toast("本地会话编号已复制。");
  } catch {
    toast("浏览器没有允许复制，请从开发者工具读取 deskSessionId。", true);
  } finally {
    setHistoryMenuOpen(false, true);
  }
}

function setContextCollapsed(collapsed) {
  const shell = $(".conversation-shell");
  const sidebar = $("#contextSidebar");
  const content = $("#contextContent");
  const trigger = $("#contextToggle");
  const expanded = !collapsed;
  const label = collapsed ? "展开当前人格栏" : "折叠当前人格栏";

  shell.classList.toggle("context-collapsed", collapsed);
  sidebar.classList.toggle("is-collapsed", collapsed);
  content.hidden = collapsed;
  trigger.setAttribute("aria-expanded", String(expanded));
  trigger.setAttribute("aria-label", label);
  trigger.title = label;
}

function scrollMessages() {
  const node = $("#messages");
  node.scrollTop = node.scrollHeight;
}

function addMessage(role, text) {
  $(".conversation-welcome")?.remove();
  const article = document.createElement("article");
  const name = document.createElement("span");
  const content = document.createElement("p");
  const time = document.createElement("time");
  article.className = `message ${role}`;
  name.className = "message-author";
  name.textContent = role === "user" ? "你" : (state.activePersona?.name || "人格引擎");
  content.textContent = text;
  time.textContent = messageTime();
  article.append(name, content, time);
  $("#messages").append(article);
  scrollMessages();
  return article;
}

function addThinkingStatus(label = "正在组织回复") {
  $(".conversation-welcome")?.remove();
  const node = document.createElement("div");
  const dots = document.createElement("span");
  const text = document.createElement("span");
  node.className = "thinking-status";
  node.setAttribute("role", "status");
  dots.className = "thinking-dots";
  dots.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 3; index += 1) {
    dots.append(document.createElement("i"));
  }
  text.className = "thinking-label";
  text.textContent = label;
  node.append(dots, text);
  $("#messages").append(node);
  scrollMessages();
  return node;
}

function finishThinkingStatus(node, outcome = "done") {
  if (outcome === "error") node.classList.add("error");
  node.remove();
}

function updateComposer() {
  const input = $("#chatInput");
  $("#charCount").textContent = `${input.value.length}/4000`;
  $("#sendButton").disabled = !state.ready || state.busy || state.composerMode !== "text" || !input.value.trim();
  $("#holdToTalk").disabled = !state.ready || state.busy || state.composerMode !== "voice";
}

function setBusy(busy, label = "") {
  state.busy = busy;
  document.body.setAttribute("aria-busy", String(busy));
  $("#composerState").textContent = label;
  $("#sendLabel").textContent = busy ? "回复中" : "发送";
  $("#sendButton").setAttribute("aria-label", busy ? "正在等待回复" : "发送测试消息");
  updateComposer();
}

function redirectToLogin() {
  location.assign("/me");
}

function stopReplyVoice() {
  if (!state.voicePlayback) return;
  state.voicePlayback.audio.pause();
  URL.revokeObjectURL(state.voicePlayback.url);
  state.voicePlayback.button.textContent = "播放语音";
  state.voicePlayback = null;
}

async function playReplyVoice(button, replyId) {
  if (state.voicePlayback?.button === button) return stopReplyVoice();
  stopReplyVoice();
  button.disabled = true;
  button.textContent = "准备播放";
  try {
    const response = await fetch("/api/v1/voice/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(csrfToken() ? { "X-CSRF-Token": csrfToken() } : {}) },
      credentials: "same-origin",
      body: JSON.stringify({ reply_id: replyId, session_id: state.sessionId, user_id: state.userId }),
    });
    if (!response.ok) throw new Error("voice unavailable");
    const url = URL.createObjectURL(await response.blob());
    const audio = new Audio(url);
    const clear = () => {
      if (state.voicePlayback?.audio !== audio) return;
      URL.revokeObjectURL(url);
      button.textContent = "播放语音";
      state.voicePlayback = null;
    };
    audio.addEventListener("ended", clear, { once: true });
    audio.addEventListener("error", clear, { once: true });
    state.voicePlayback = { audio, url, button };
    button.textContent = "停止播放";
    await audio.play();
  } catch {
    button.textContent = "播放语音";
    toast("回复语音暂时无法播放。", true);
  } finally {
    button.disabled = false;
  }
}

function attachReplyVoiceControl(message, replyId, text) {
  if (!replyId || !state.ttsEnabled || text.length > state.ttsMaxReplyChars) return;
  const button = document.createElement("button");
  button.className = "message-voice-toggle";
  button.type = "button";
  button.dataset.replyVoice = "true";
  button.textContent = "播放语音";
  button.addEventListener("click", () => playReplyVoice(button, replyId));
  message.append(button);
}

async function sendChat(text, inputSource = "text") {
  const clean = text.trim();
  if (!clean || state.busy || !state.ready) return;
  addMessage("user", clean);
  updateHistoryTimestamp();
  if (inputSource === "text") $("#chatInput").value = "";
  const thinking = addThinkingStatus(inputSource === "audio" ? "正在生成回复" : "正在组织回复");
  setBusy(true, inputSource === "audio" ? "语音已识别，正在回复" : "正在回复");
  try {
    let responseMessage = null;
    const reply = await streamTextFetch("/api/v1/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_input: clean,
        session_id: state.sessionId,
        user_id: state.userId,
        input_source: inputSource,
        ...(state.activePersona ? { persona_id: state.activePersona.persona_id } : {}),
      }),
    }, (_chunk, replyText) => {
      if (!responseMessage) {
        finishThinkingStatus(thinking);
        responseMessage = addMessage("assistant", "");
      }
      responseMessage.querySelector("p").textContent = replyText;
      scrollMessages();
    });
    if (!responseMessage) {
      finishThinkingStatus(thinking);
      responseMessage = addMessage("assistant", reply.text || "当前没有生成可显示的回复。");
    }
    if (reply.interrupted) {
      const note = document.createElement("div");
      note.className = "message-stream-note";
      note.textContent = "回复在生成中途被截断，以上是已生成的部分内容。";
      responseMessage.append(note);
      toast("回复中途中断，仅显示部分内容。", true);
    }
    attachReplyVoiceControl(responseMessage, reply.replyId, reply.text);
  } catch (error) {
    if (error.status === 401 && state.authEnabled) return redirectToLogin();
    finishThinkingStatus(thinking, "error");
    addMessage("assistant", "这次回复没有完成，请稍后重试。");
    toast("对话请求没有完成，请检查服务状态。", true);
  } finally {
    setBusy(false);
    updateComposer();
    if (state.composerMode === "text") $("#chatInput").focus();
  }
}

function formatDuration(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function setRecordingControls(recording, disabled = false) {
  const button = $("#holdToTalk");
  button.classList.toggle("recording", recording);
  button.disabled = disabled || state.busy || !state.ready || state.composerMode !== "voice";
  $("#holdToTalkLabel").textContent = recording ? "松开发送" : disabled ? "正在发送" : "按住说话";
  if (!recording && !disabled) $("#voiceDuration").textContent = "00:00";
}

async function requestWithinTimeout(run, timeoutMs) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try { return await run(controller.signal); }
  finally { window.clearTimeout(timer); }
}

async function sendAudio(blob) {
  if (!state.ready || state.busy) return;
  const form = new FormData();
  form.append("file", blob, "voice.webm");
  form.append("session_id", state.sessionId);
  form.append("user_id", state.userId);
  const thinking = addThinkingStatus("正在转写语音");
  setBusy(true, "正在转写语音");
  setRecordingControls(false, true);
  try {
    const data = await requestWithinTimeout(
      (signal) => jsonFetch("/api/v1/audio/chat/prepare/file", { method: "POST", body: form, signal }),
      12_000,
    );
    finishThinkingStatus(thinking);
    if (data.chat_bypassed_due_to_asr_quality) {
      addMessage("assistant", data.clarification_reply || "这段语音不够清楚，请再说一次。");
      return;
    }
    state.busy = false;
    await sendChat(data.transcript_text || "未识别到有效文本", "audio");
  } catch (error) {
    finishThinkingStatus(thinking, "error");
    const message = error.name === "AbortError" ? "语音识别等待过久，请重试。" : "这段语音暂时没有处理完成，请再试一次。";
    addMessage("assistant", message);
    toast(message, true);
  } finally {
    setBusy(false);
    setRecordingControls(false);
    updateComposer();
  }
}

async function beginHoldRecording() {
  if (state.holdingToTalk || state.busy || !state.ready || state.composerMode !== "voice") return;
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    toast("当前浏览器不支持麦克风语音。", true);
    return;
  }
  state.holdingToTalk = true;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (!state.holdingToTalk) return stream.getTracks().forEach((track) => track.stop());
    state.chunks = [];
    state.recorder = new MediaRecorder(stream);
    state.recorder.ondataavailable = (event) => { if (event.data.size) state.chunks.push(event.data); };
    state.recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      window.clearInterval(state.recordingClock);
      const mimeType = state.recorder.mimeType || "audio/webm";
      if (state.chunks.length) sendAudio(new Blob(state.chunks, { type: mimeType }));
      else setRecordingControls(false);
    };
    state.recorder.start();
    state.recordingStartedAt = performance.now();
    state.recordingClock = window.setInterval(() => {
      $("#voiceDuration").textContent = formatDuration(performance.now() - state.recordingStartedAt);
    }, 250);
    setRecordingControls(true);
  } catch {
    state.holdingToTalk = false;
    setRecordingControls(false);
    toast("无法使用麦克风，请检查浏览器权限。", true);
  }
}

function finishHoldRecording() {
  if (!state.holdingToTalk) return;
  state.holdingToTalk = false;
  if (state.recorder?.state === "recording") {
    state.recorder.stop();
    setRecordingControls(false, true);
  }
}

function setComposerMode(mode, shouldFocus = true) {
  state.composerMode = mode === "voice" ? "voice" : "text";
  $("#chatForm").dataset.composerMode = state.composerMode;
  $("#textComposer").hidden = state.composerMode !== "text";
  $("#voiceComposer").hidden = state.composerMode !== "voice";
  const modeToggle = $("#voiceModeAction");
  const voiceActive = state.composerMode === "voice";
  const toggleLabel = voiceActive ? "切换到文字输入" : "切换到按住说话";
  modeToggle.dataset.composerMode = voiceActive ? "text" : "voice";
  modeToggle.classList.toggle("active", voiceActive);
  modeToggle.setAttribute("aria-pressed", String(voiceActive));
  modeToggle.setAttribute("aria-label", toggleLabel);
  modeToggle.title = toggleLabel;
  updateComposer();
  if (!shouldFocus) return;
  if (state.composerMode === "text") $("#chatInput").focus();
  else $("#holdToTalk").focus();
}

async function checkCore() {
  let label = "本机服务未连接";
  try {
    await jsonFetch("/health");
    label = "本机服务已连接";
  } catch {
  } finally {
    const footerStatus = $("#footerCoreStatus");
    if (footerStatus) footerStatus.textContent = label;
  }
}

function loadVoiceInputCapability() {
  return Boolean(navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined");
}

async function loadVoiceStatus() {
  try {
    const status = await jsonFetch("/api/v1/voice/status");
    state.ttsEnabled = Boolean(status.enabled);
    state.ttsMaxReplyChars = Number.isInteger(status.max_reply_chars) ? status.max_reply_chars : 0;
  } catch {
    state.ttsEnabled = false;
    state.ttsMaxReplyChars = 0;
  }
}

async function ensureDeskAccess() {
  setBusy(true, "正在确认会话");
  try {
    const authStatus = await jsonFetch("/api/v1/auth/status");
    state.authEnabled = Boolean(authStatus.authentication_enabled);
    if (state.authEnabled) {
      const account = await jsonFetch("/api/v1/auth/me");
      state.userId = account.profile_id;
      $("#accessModeLabel").textContent = `${account.display_name} 的测试会话`;
      $("#accountAction").textContent = "我的工坊";
      $("#accountAction").href = "/me";
      document.body.dataset.accessMode = "account";
    } else {
      localStorage.setItem("deskUserId", state.userId);
      $("#accessModeLabel").textContent = "临时测试会话";
      document.body.dataset.accessMode = "local";
    }
    state.ready = true;
  } catch (error) {
    if (error.status === 401) return redirectToLogin();
    $("#accessModeLabel").textContent = "暂时无法确认会话";
    $("#sessionMode").textContent = "不可用";
    toast("无法确认服务状态，暂时不能发送消息。", true);
  } finally {
    setBusy(false);
    updateComposer();
  }
}

$("#chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  sendChat($("#chatInput").value);
});
$("#chatInput").addEventListener("input", (event) => {
  updateComposer();
});
$("#chatInput").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  sendChat(event.currentTarget.value);
});
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#chatInput").value = button.dataset.prompt;
    $("#chatInput").focus();
    updateComposer();
  });
});
$("#attachmentAction").addEventListener("click", () => {
  toast("附件仅保留在本地沙盒，当前页面不会上传文件。");
});
$("#historyMenuButton").addEventListener("click", () => {
  const open = $("#historyMenuButton").getAttribute("aria-expanded") !== "true";
  setHistoryMenuOpen(open);
});
$("#historyMenu").addEventListener("click", (event) => {
  const action = event.target.closest("[data-history-action]");
  if (action?.dataset.historyAction === "copy-session") copySessionId();
});
$("#contextToggle").addEventListener("click", () => {
  const collapsed = $("#contextToggle").getAttribute("aria-expanded") === "true";
  setContextCollapsed(collapsed);
});
const compactContextQuery = window.matchMedia("(max-width: 1199px)");
compactContextQuery.addEventListener("change", (event) => setContextCollapsed(event.matches));
document.addEventListener("click", (event) => {
  if ($("#historyMenu").hidden || event.target.closest(".history-entry")) return;
  setHistoryMenuOpen(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || $("#historyMenu").hidden) return;
  event.preventDefault();
  setHistoryMenuOpen(false, true);
});
$("#voiceModeAction").addEventListener("click", () => {
  setComposerMode(state.composerMode === "voice" ? "text" : "voice");
});
$("#holdToTalk").addEventListener("pointerdown", (event) => { event.preventDefault(); event.currentTarget.setPointerCapture?.(event.pointerId); beginHoldRecording(); });
$("#holdToTalk").addEventListener("pointerup", finishHoldRecording);
$("#holdToTalk").addEventListener("pointercancel", finishHoldRecording);
$("#holdToTalk").addEventListener("keydown", (event) => { if (!event.repeat && ["Enter", " "].includes(event.key)) { event.preventDefault(); beginHoldRecording(); } });
$("#holdToTalk").addEventListener("keyup", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); finishHoldRecording(); } });
$("#personaSelect").addEventListener("change", (event) => selectPersona(event.currentTarget.value));
window.addEventListener("focus", () => {
  if (!state.busy) loadPersonas();
});

async function bootstrap() {
  await loadPersonas();
  const prompt = new URLSearchParams(location.search).get("prompt");
  if (prompt) $("#chatInput").value = prompt.slice(0, 4000);
  updateHistoryTimestamp();
  setComposerMode("text", false);
  setContextCollapsed(compactContextQuery.matches);
  loadVoiceInputCapability();
  await ensureDeskAccess();
  await Promise.all([checkCore(), loadVoiceStatus()]);
}

bootstrap();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/desk/service-worker.js", { scope: "/desk/" });
