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
  serviceReachable: false,
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
  streamController: null,
  voiceInputAvailable: false,
  activePersonaId: "default",
  activePersona: null,
  personas: [],
  followMessages: true,
};

localStorage.setItem("deskSessionId", state.sessionId);
const $ = (selector) => document.querySelector(selector);
const SANDBOX_PERSONA_API = "/api/v1/sandbox/personas";
const CHAT_HISTORY_API = "/api/v1/chat/history";
const DESK_DRAFT_KEY = "personacore_desk_input_draft";

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

function messageTime(value = null) {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(
    value ? new Date(value) : new Date(),
  );
}

function updateHistoryTimestamp() {
  const time = $("#historyTimestamp");
  const now = new Date();
  time.dateTime = now.toISOString();
  time.textContent = messageTime();
}

function updateHistoryLabel(title = "") {
  const node = $("#historyTitle");
  if (!node) return;
  const clean = String(title || "").replace(/\s+/g, " ").trim();
  node.textContent = clean ? clean.slice(0, 34) : "\u65b0\u4f1a\u8bdd";
}

function clearMessages() {
  $("#messages").querySelectorAll(".message, .thinking-status").forEach((node) => node.remove());
}

async function loadHistory() {
  const params = new URLSearchParams({
    session_id: state.sessionId,
    user_id: state.userId,
    limit: "80",
  });
  try {
    const data = await jsonFetch(`${CHAT_HISTORY_API}?${params}`);
    const messages = Array.isArray(data?.messages) ? data.messages : [];
    clearMessages();
    if (!messages.length) {
      updateHistoryLabel();
      updateHistoryTimestamp();
      return;
    }
    messages.forEach((message) => addMessage(message.role, message.content, {
      forceScroll: false,
      createdAt: message.created_at,
    }));
    updateHistoryLabel(messages.find((message) => message.role === "user")?.content);
    const latest = messages[messages.length - 1]?.created_at;
    const time = $("#historyTimestamp");
    if (latest) {
      time.dateTime = latest;
      time.textContent = messageTime(latest);
    }
    scrollMessages(true);
  } catch (error) {
    if (error.status !== 401) toast("历史消息暂时无法读取，当前仍可继续对话。", true);
  }
}

function startNewSession() {
  if (state.busy || state.holdingToTalk) {
    toast("请先停止当前回复，再新建会话。", true);
    return;
  }
  stopReplyVoice();
  state.sessionId = `desk-${crypto.randomUUID()}`;
  localStorage.setItem("deskSessionId", state.sessionId);
  location.reload();
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

function setContextCollapsed(collapsed, restoreMobileFocus = false) {
  const shell = $(".conversation-shell");
  const sidebar = $("#contextSidebar");
  const content = $("#contextContent");
  const trigger = $("#contextToggle");
  const mobileTrigger = $("#mobileContextAction");
  const backdrop = $("#contextBackdrop");
  const expanded = !collapsed;
  const label = collapsed ? "展开当前人格栏" : "折叠当前人格栏";

  shell.classList.toggle("context-collapsed", collapsed);
  sidebar.classList.toggle("is-collapsed", collapsed);
  content.hidden = collapsed;
  trigger.setAttribute("aria-expanded", String(expanded));
  trigger.setAttribute("aria-label", label);
  trigger.title = label;
  mobileTrigger.setAttribute("aria-expanded", String(expanded));
  mobileTrigger.setAttribute("aria-label", expanded ? "关闭当前人格" : "查看当前人格");
  mobileTrigger.title = expanded ? "关闭当前人格" : "查看当前人格";

  const mobileOpen = mobileContextQuery.matches && expanded;
  document.body.classList.toggle("context-drawer-open", mobileOpen);
  backdrop.hidden = !mobileOpen;
  if (restoreMobileFocus && mobileContextQuery.matches) mobileTrigger.focus();
}

function messagesNearBottom() {
  const node = $("#messages");
  return node.scrollHeight - node.scrollTop - node.clientHeight < 72;
}

function updateScrollControl() {
  const button = $("#scrollToLatest");
  const show = !state.followMessages && $("#messages").scrollHeight > $("#messages").clientHeight;
  button.hidden = !show;
}

function scrollMessages(force = false) {
  const node = $("#messages");
  if (force) state.followMessages = true;
  if (state.followMessages) node.scrollTop = node.scrollHeight;
  window.requestAnimationFrame(updateScrollControl);
}

function addMessage(role, text, { forceScroll = role === "user", createdAt = null } = {}) {
  $(".conversation-welcome")?.remove();
  const article = document.createElement("article");
  const name = document.createElement("span");
  const content = document.createElement("p");
  const time = document.createElement("time");
  article.className = `message ${role}`;
  name.className = "message-author";
  name.textContent = role === "user" ? "你" : (state.activePersona?.name || "人格引擎");
  content.textContent = text;
  if (createdAt) time.dateTime = createdAt;
  time.textContent = messageTime(createdAt);
  article.append(name, content, time);
  $("#messages").append(article);
  scrollMessages(forceScroll);
  return article;
}

function attachRetryControl(message, text, inputSource) {
  const button = document.createElement("button");
  button.className = "message-retry-action";
  button.type = "button";
  button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" /></svg><span>重试</span>';
  button.addEventListener("click", () => {
    if (state.busy || !navigator.onLine) return;
    message.remove();
    sendChat(text, inputSource, { appendUser: false });
  });
  message.append(button);
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
  const sendButton = $("#sendButton");
  const canSendText = state.ready
    && state.serviceReachable
    && navigator.onLine
    && state.composerMode === "text"
    && Boolean(input.value.trim());
  sendButton.disabled = state.busy ? !state.streamController : !canSendText;
  sendButton.dataset.busy = String(state.busy);
  $("#holdToTalk").disabled = !state.ready
    || !state.serviceReachable
    || !navigator.onLine
    || state.busy
    || state.composerMode !== "voice";
}

function readInputDraft() {
  try {
    return localStorage.getItem(DESK_DRAFT_KEY) || "";
  } catch {
    return "";
  }
}

function persistInputDraft(value) {
  try {
    if (value) localStorage.setItem(DESK_DRAFT_KEY, value);
    else localStorage.removeItem(DESK_DRAFT_KEY);
  } catch {
    // Chat remains usable when browser storage is unavailable.
  }
}

function resizeComposerInput() {
  const input = $("#chatInput");
  input.style.height = "0px";
  const maxHeight = window.innerWidth <= 767 ? 120 : 144;
  input.style.height = `${Math.min(Math.max(input.scrollHeight, 24), maxHeight)}px`;
  input.style.overflowY = input.scrollHeight > maxHeight ? "auto" : "hidden";
}

function setBusy(busy, label = "") {
  state.busy = busy;
  document.body.setAttribute("aria-busy", String(busy));
  $("#composerState").textContent = label;
  $("#sendLabel").textContent = busy ? "停止" : "发送";
  $("#sendButton").setAttribute("aria-label", busy ? "停止当前回复" : "发送消息");
  const sendIcon = $("#sendButton svg");
  if (sendIcon) {
    sendIcon.innerHTML = busy
      ? '<rect x="7" y="7" width="10" height="10" rx="1.5"></rect>'
      : '<path d="M12 19V5m-6 6 6-6 6 6" />';
  }
  updateComposer();
}

function redirectToLogin() {
  const returnTo = `${location.pathname}${location.search}`;
  location.assign(`/auth?return_to=${encodeURIComponent(returnTo)}`);
}

function cancelActiveReply() {
  if (!state.streamController) return;
  state.streamController.abort();
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
    const response = await requestWithinTimeout(
      (signal) => fetch("/api/v1/voice/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(csrfToken() ? { "X-CSRF-Token": csrfToken() } : {}) },
      credentials: "same-origin",
      signal,
      body: JSON.stringify({ reply_id: replyId, session_id: state.sessionId, user_id: state.userId }),
      }),
      20_000,
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail = typeof payload?.detail === "string" ? payload.detail : "";
      if (response.status === 404) throw new Error("\u8fd9\u6761\u56de\u590d\u5df2\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u53d1\u9001\u6d88\u606f");
      if (response.status === 503) throw new Error("\u8bed\u97f3\u670d\u52a1\u6682\u672a\u542f\u52a8\uff0c\u6587\u5b57\u56de\u590d\u4ecd\u53ef\u6b63\u5e38\u4f7f\u7528");
      throw new Error(detail || "\u8bed\u97f3\u64ad\u653e\u6682\u65f6\u4e0d\u53ef\u7528");
    }
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
  } catch (error) {
    button.textContent = "播放语音";
    const message = error?.name === "AbortError"
      ? "\u8bed\u97f3\u5408\u6210\u7b49\u5f85\u8d85\u65f6\uff0c\u8bf7\u68c0\u67e5\u672c\u5730\u8bed\u97f3\u670d\u52a1"
      : error?.message || "\u56de\u590d\u8bed\u97f3\u6682\u65f6\u65e0\u6cd5\u64ad\u653e";
    toast(message, true);
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

async function sendChat(text, inputSource = "text", { appendUser = true } = {}) {
  const clean = text.trim();
  if (!clean || state.busy || !state.ready || !navigator.onLine) return;
  if (appendUser) {
    addMessage("user", clean);
    updateHistoryLabel(clean);
    updateHistoryTimestamp();
  }
  if (inputSource === "text" && appendUser) {
    $("#chatInput").value = "";
    persistInputDraft("");
    resizeComposerInput();
  }
  const thinking = addThinkingStatus(inputSource === "audio" ? "正在生成回复" : "正在组织回复");
  const controller = new AbortController();
  state.streamController = controller;
  setBusy(true, inputSource === "audio" ? "语音已识别，正在回复" : "正在回复");
  let responseMessage = null;
  try {
    const reply = await streamTextFetch("/api/v1/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
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
    if (error.name === "AbortError") {
      finishThinkingStatus(thinking);
      if (responseMessage) {
        const note = document.createElement("div");
        note.className = "message-stream-note interrupted";
        note.textContent = "回复已停止，以上是已生成的内容。";
        responseMessage.append(note);
      } else {
        addMessage("assistant", "回复已停止。");
      }
      return;
    }
    if (error.status === 401 && state.authEnabled) return redirectToLogin();
    finishThinkingStatus(thinking, "error");
    const failureMessage = addMessage("assistant", "这次回复没有完成。你可以直接重试，不需要重新输入。", { forceScroll: false });
    failureMessage.classList.add("message-error");
    attachRetryControl(failureMessage, clean, inputSource);
    toast("对话请求没有完成，请检查服务状态。", true);
    checkCore();
  } finally {
    if (state.streamController === controller) state.streamController = null;
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
  button.disabled = disabled
    || state.busy
    || !state.ready
    || !state.serviceReachable
    || !navigator.onLine
    || state.composerMode !== "voice";
  $("#holdToTalkLabel").textContent = recording ? "松开发送" : disabled ? "正在发送" : "按住说话";
  if (!recording && !disabled) $("#voiceDuration").textContent = "00:00";
}

function setVoiceReview(visible, text = "") {
  const panel = $("#voiceReview");
  panel.hidden = !visible;
  $("#voiceTranscript").value = text;
  if (visible) window.requestAnimationFrame(() => $("#voiceTranscript").focus());
}

async function requestWithinTimeout(run, timeoutMs) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try { return await run(controller.signal); }
  finally { window.clearTimeout(timer); }
}

async function sendAudio(blob) {
  if (!state.ready || !state.serviceReachable || !navigator.onLine || state.busy) return;
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
      45_000,
    );
    finishThinkingStatus(thinking);
    if (data.chat_bypassed_due_to_asr_quality) {
      addMessage("assistant", data.clarification_reply || "这段语音不够清楚，请再说一次。");
      return;
    }
    state.busy = false;
    setVoiceReview(true, data.transcript_text || "");
    setBusy(false, "请确认识别结果后发送");
  } catch (error) {
    setVoiceReview(false);
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
  if (state.holdingToTalk
    || state.busy
    || !state.ready
    || !state.serviceReachable
    || !navigator.onLine
    || state.composerMode !== "voice") return;
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
  if (mode === "voice" && !state.voiceInputAvailable) {
    toast("当前浏览器不支持麦克风输入。", true);
    return;
  }
  state.composerMode = mode === "voice" ? "voice" : "text";
  if (state.composerMode === "text") setVoiceReview(false);
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
  let connected = false;
  let label = navigator.onLine ? "本机服务未连接" : "网络已断开";
  try {
    if (!navigator.onLine) throw new Error("offline");
    await jsonFetch("/health");
    connected = true;
    label = "本机服务已连接";
  } catch {
  } finally {
    state.serviceReachable = connected;
    const footerStatus = $("#footerCoreStatus");
    if (footerStatus) {
      footerStatus.textContent = label;
      footerStatus.classList.toggle("offline", !connected);
    }
    updateComposer();
    setRecordingControls(false);
  }
}

function loadVoiceInputCapability() {
  state.voiceInputAvailable = Boolean(navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined");
  const button = $("#voiceModeAction");
  button.disabled = !state.voiceInputAvailable;
  if (!state.voiceInputAvailable) {
    button.setAttribute("aria-label", "当前浏览器不支持语音输入");
    button.title = "当前浏览器不支持语音输入";
  }
  return state.voiceInputAvailable;
}

async function loadVoiceStatus() {
  const checkButton = $("#voiceCheckAction");
  if (checkButton) {
    checkButton.disabled = true;
    checkButton.setAttribute("aria-busy", "true");
  }
  try {
    const status = await jsonFetch("/api/v1/voice/status");
    state.ttsEnabled = Boolean(status.enabled && status.provider_ready);
    state.ttsMaxReplyChars = Number.isInteger(status.max_reply_chars) ? status.max_reply_chars : 0;
    const statusNode = $("#voiceStatus");
    if (statusNode) {
      statusNode.textContent = state.ttsEnabled
        ? `语音回复在线 · ${status.provider || "本地服务"}`
        : status.enabled
          ? "语音回复未启动"
          : "语音回复未启用";
      statusNode.classList.toggle("offline", !state.ttsEnabled);
      statusNode.dataset.state = state.ttsEnabled ? "ready" : "offline";
    }
  } catch {
    state.ttsEnabled = false;
    state.ttsMaxReplyChars = 0;
    const statusNode = $("#voiceStatus");
    if (statusNode) {
      statusNode.textContent = "语音回复不可用";
      statusNode.classList.add("offline");
      statusNode.dataset.state = "offline";
    }
  } finally {
    if (checkButton) {
      checkButton.disabled = false;
      checkButton.removeAttribute("aria-busy");
    }
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
  if (state.busy) {
    cancelActiveReply();
    return;
  }
  sendChat($("#chatInput").value);
});
$("#chatInput").addEventListener("input", (event) => {
  persistInputDraft(event.currentTarget.value);
  resizeComposerInput();
  updateComposer();
});
$("#chatInput").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  if (state.busy) {
    cancelActiveReply();
    return;
  }
  sendChat(event.currentTarget.value);
});
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#chatInput").value = button.dataset.prompt;
    persistInputDraft($("#chatInput").value);
    resizeComposerInput();
    $("#chatInput").focus();
    updateComposer();
  });
});
$("#historyMenuButton").addEventListener("click", () => {
  const open = $("#historyMenuButton").getAttribute("aria-expanded") !== "true";
  setHistoryMenuOpen(open);
});
$("#historyMenu").addEventListener("click", (event) => {
  const action = event.target.closest("[data-history-action]");
  if (action?.dataset.historyAction === "copy-session") copySessionId();
});
$("#newSessionAction").addEventListener("click", startNewSession);
$("#newSessionSidebar").addEventListener("click", startNewSession);
$("#contextToggle").addEventListener("click", () => {
  const collapsed = $("#contextToggle").getAttribute("aria-expanded") === "true";
  setContextCollapsed(collapsed, collapsed);
});
const compactContextQuery = window.matchMedia("(max-width: 1199px)");
const mobileContextQuery = window.matchMedia("(max-width: 840px)");
compactContextQuery.addEventListener("change", (event) => setContextCollapsed(event.matches));
$("#mobileContextAction").addEventListener("click", () => {
  const expanded = $("#mobileContextAction").getAttribute("aria-expanded") === "true";
  setContextCollapsed(expanded, expanded);
  if (!expanded) window.requestAnimationFrame(() => $("#contextToggle").focus());
});
$("#contextBackdrop").addEventListener("click", () => setContextCollapsed(true, true));
document.addEventListener("click", (event) => {
  if ($("#historyMenu").hidden || event.target.closest(".history-entry")) return;
  setHistoryMenuOpen(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!$("#historyMenu").hidden) {
    event.preventDefault();
    setHistoryMenuOpen(false, true);
    return;
  }
  if (mobileContextQuery.matches && $("#mobileContextAction").getAttribute("aria-expanded") === "true") {
    event.preventDefault();
    setContextCollapsed(true, true);
  }
});
$("#voiceModeAction").addEventListener("click", () => {
  setComposerMode(state.composerMode === "voice" ? "text" : "voice");
});
$("#holdToTalk").addEventListener("pointerdown", (event) => { event.preventDefault(); event.currentTarget.setPointerCapture?.(event.pointerId); beginHoldRecording(); });
$("#holdToTalk").addEventListener("pointerup", finishHoldRecording);
$("#holdToTalk").addEventListener("pointercancel", finishHoldRecording);
$("#holdToTalk").addEventListener("keydown", (event) => { if (!event.repeat && ["Enter", " "].includes(event.key)) { event.preventDefault(); beginHoldRecording(); } });
$("#holdToTalk").addEventListener("keyup", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); finishHoldRecording(); } });
$("#voiceTranscriptSend").addEventListener("click", () => {
  const text = $("#voiceTranscript").value.trim();
  if (!text) {
    toast("请先确认识别结果，或重新录音。", true);
    $("#voiceTranscript").focus();
    return;
  }
  setVoiceReview(false);
  sendChat(text, "audio");
});
$("#voiceTranscriptCancel").addEventListener("click", () => {
  setVoiceReview(false);
  $("#holdToTalk").focus();
});
$("#personaSelect").addEventListener("change", (event) => selectPersona(event.currentTarget.value));
$("#voiceCheckAction")?.addEventListener("click", loadVoiceStatus);
$("#messages").addEventListener("scroll", () => {
  state.followMessages = messagesNearBottom();
  updateScrollControl();
}, { passive: true });
$("#scrollToLatest").addEventListener("click", () => scrollMessages(true));
window.addEventListener("resize", () => {
  resizeComposerInput();
  updateScrollControl();
});
window.addEventListener("offline", () => {
  state.serviceReachable = false;
  $("#footerCoreStatus").textContent = "网络已断开";
  $("#footerCoreStatus").classList.add("offline");
  updateComposer();
  toast("网络已断开，输入草稿已保留。", true);
});
window.addEventListener("online", async () => {
  await checkCore();
  if (state.serviceReachable) toast("本机服务连接已恢复。");
});
window.addEventListener("focus", () => {
  if (!state.busy) loadPersonas();
});

async function bootstrap() {
  await loadPersonas();
  const params = new URLSearchParams(location.search);
  const prompt = params.get("prompt");
  $("#chatInput").value = prompt ? prompt.slice(0, 4000) : readInputDraft().slice(0, 4000);
  if (prompt) {
    persistInputDraft($("#chatInput").value);
    params.delete("prompt");
    const query = params.toString();
    history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}`);
  }
  resizeComposerInput();
  updateHistoryTimestamp();
  setComposerMode("text", false);
  setContextCollapsed(compactContextQuery.matches);
  loadVoiceInputCapability();
  await ensureDeskAccess();
  await Promise.all([checkCore(), loadVoiceStatus()]);
  if (state.ready && state.serviceReachable) await loadHistory();
}

bootstrap();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/desk/service-worker.js", { scope: "/desk/" });
