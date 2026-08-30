const $ = (selector) => document.querySelector(selector);

function localSandboxOwnerId() {
  const saved = localStorage.getItem("deskUserId");
  if (saved && saved !== "desk-local") return saved;
  const created = `desk-${crypto.randomUUID()}`;
  localStorage.setItem("deskUserId", created);
  return created;
}

const LEGACY_PERSONA_DRAFTS_KEY = "personacore.local-personas.v1";
const LEGACY_PERSONA_MIGRATION_KEY = "personacore.local-personas.server-migrated.v1";
const MODEL_DRAFT_KEY = "personacore.local-model-draft.v1";
const AGENT_CONFIG_KEY = "personacore.agent-config.v1";
const AGENT_CONFIG_DEFAULTS = {
  agent_name: "人格引擎",
  system_prompt: "",
  temperature: 0.7,
  top_p: 0.9,
  max_tokens: "1024",
  web_search: false,
  code_interpreter: false,
  save_notices: true,
  avatar_data: "",
};
let agentConfigSaveTimer = 0;
let agentAvatarData = "";
const SANDBOX_PERSONA_API = "/api/v1/sandbox/personas";
const state = {
  account: null,
  authEnabled: false,
  capabilities: null,
  memoryRecords: [],
  pendingMemoryId: null,
  editingPersonaId: null,
  personaSaveBusy: false,
  personas: [],
  personaOwnerId: localSandboxOwnerId(),
};
const presets = {
  scholar: { name: "冷静学者", traits: "清晰、克制、求证", detail: "重视事实来源与不确定性。说话简洁，先澄清问题再给出有依据的建议。" },
  friend: { name: "热情挚友", traits: "主动、温暖、陪伴", detail: "保持真诚和边界感，先回应感受，再一起拆解正在面对的事情。" },
  assistant: { name: "严谨助手", traits: "可靠、准确、有边界", detail: "把事实、假设和下一步分开表达。遇到未知信息时明确说明，不假装具备未启用的能力。" },
};

function csrfToken() {
  const stored = sessionStorage.getItem("hutao_csrf_token");
  if (stored) return stored;
  const match = document.cookie.match(/(?:^|; )hutao_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function jsonFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = csrfToken();
  if (token && (options.method || "GET").toUpperCase() !== "GET") headers.set("X-CSRF-Token", token);
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof data?.detail === "string" ? data.detail : `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function legacyPersonas() {
  try {
    const saved = JSON.parse(localStorage.getItem(LEGACY_PERSONA_DRAFTS_KEY) || "[]");
    return Array.isArray(saved) ? saved.filter((item) => item && typeof item.name === "string") : [];
  } catch {
    return [];
  }
}

function parseTraits(value) {
  const source = Array.isArray(value) ? value : String(value || "").split(/[、,，\s]+/);
  return source.map((item) => String(item).trim()).filter(Boolean).slice(0, 3);
}

function traitsText(value) {
  return parseTraits(value).join("、");
}

async function loadPersonas() {
  if (state.authEnabled && !state.account) {
    state.personas = [];
    renderPersonaList();
    renderDraftStatus();
    return;
  }
  try {
    const owner = encodeURIComponent(state.personaOwnerId);
    state.personas = await jsonFetch(`${SANDBOX_PERSONA_API}?user_id=${owner}`);
  } catch (error) {
    state.personas = [];
    if (error.status === 401 && state.authEnabled) {
      renderLocalAccountState("账户会话已失效；登录后才能读取人格草稿。 ");
    } else {
      toast("本机人格服务暂时无法读取，请检查服务状态。", true);
    }
  }
  renderPersonaList();
  const active = state.personas.find((item) => item.persona_id === state.editingPersonaId) || null;
  renderDraftStatus(active);
}

async function migrateLegacyPersonas() {
  if (localStorage.getItem(LEGACY_PERSONA_MIGRATION_KEY)) return;
  const records = legacyPersonas();
  if (!records.length) {
    localStorage.setItem(LEGACY_PERSONA_MIGRATION_KEY, "done");
    return;
  }
  try {
    for (const record of records) {
      await jsonFetch(SANDBOX_PERSONA_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: state.personaOwnerId,
          name: record.name,
          traits: parseTraits(record.traits),
          detail: String(record.detail || ""),
          model_label: record.modelName || null,
        }),
      });
    }
    localStorage.setItem(LEGACY_PERSONA_MIGRATION_KEY, "done");
  } catch {
    toast("旧草稿还未迁移，请保持本机服务运行后重试。", true);
  }
}

function readModelDraft() {
  try { return JSON.parse(localStorage.getItem(MODEL_DRAFT_KEY) || "null"); } catch { return null; }
}

function formatDate(value) {
  if (!value) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = `toast${error ? " error" : ""}`;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 3200);
}

function readAgentConfig() {
  try {
    const saved = JSON.parse(localStorage.getItem(AGENT_CONFIG_KEY) || "null");
    return saved && typeof saved === "object" ? { ...AGENT_CONFIG_DEFAULTS, ...saved } : { ...AGENT_CONFIG_DEFAULTS };
  } catch {
    return { ...AGENT_CONFIG_DEFAULTS };
  }
}

function renderAgentAvatar(data = "", name = "人格引擎") {
  const initial = String(name || "P").trim().slice(0, 1).toUpperCase() || "P";
  for (const id of ["sidebarAvatarPreview", "configAvatarPreview"]) {
    const image = $(`#${id}`);
    image.src = data || "";
    image.hidden = !data;
  }
  for (const id of ["sidebarAvatarFallback", "configAvatarFallback"]) {
    const fallback = $(`#${id}`);
    fallback.textContent = initial;
    fallback.hidden = Boolean(data);
  }
}

function renderAgentConfig(config = readAgentConfig()) {
  $("#agentName").value = String(config.agent_name || "").slice(0, 60);
  $("#systemPrompt").value = String(config.system_prompt || "").slice(0, 8000);
  $("#temperature").value = String(config.temperature ?? 0.7);
  $("#topP").value = String(config.top_p ?? 0.9);
  $("#maxTokens").value = ["512", "1024", "4096"].includes(String(config.max_tokens)) ? String(config.max_tokens) : "1024";
  $("#toolWebSearch").checked = Boolean(config.web_search);
  $("#toolCodeInterpreter").checked = Boolean(config.code_interpreter);
  $("#localSaveNotices").checked = config.save_notices !== false;
  $("#temperatureValue").textContent = Number($("#temperature").value).toFixed(1);
  $("#topPValue").textContent = Number($("#topP").value).toFixed(2).replace(/0$/, "");
  agentAvatarData = typeof config.avatar_data === "string" ? config.avatar_data : "";
  renderAgentAvatar(agentAvatarData, $("#agentName").value);
}

function renderCapabilities(data = {}) {
  state.capabilities = data;
  const tools = data.tools || {};
  const rows = [
    ["web_search", "toolWebSearch", "toolWebSearchState", "toolWebSearchHint"],
    ["code_interpreter", "toolCodeInterpreter", "toolCodeInterpreterState", "toolCodeInterpreterHint"],
  ];
  for (const [key, inputId, stateId, hintId] of rows) {
    const capability = tools[key] || {};
    const input = $(`#${inputId}`);
    const badge = $(`#${stateId}`);
    const hint = $(`#${hintId}`);
    const enabled = capability.enabled === true;
    input.checked = false;
    input.disabled = true;
    badge.textContent = enabled ? "已接通" : "未接通";
    badge.classList.toggle("ready", enabled);
    hint.textContent = enabled ? "服务端已提供该能力" : (capability.reason || "当前没有可调用的后端契约");
  }
}

async function loadCapabilities() {
  try {
    renderCapabilities(await jsonFetch("/api/v1/capabilities"));
  } catch {
    renderCapabilities({ tools: {
      web_search: { enabled: false, reason: "无法读取服务能力" },
      code_interpreter: { enabled: false, reason: "无法读取服务能力" },
    } });
  }
}

function formAgentConfig() {
  return {
    agent_name: $("#agentName").value.trim(),
    system_prompt: $("#systemPrompt").value.trim(),
    temperature: Number($("#temperature").value),
    top_p: Number($("#topP").value),
    max_tokens: $("#maxTokens").value,
    web_search: $("#toolWebSearch").checked,
    code_interpreter: $("#toolCodeInterpreter").checked,
    save_notices: $("#localSaveNotices").checked,
    avatar_data: agentAvatarData,
  };
}

function setAgentConfigSaveState(message) {
  const stateNode = $("#configSaveState");
  if (stateNode) stateNode.textContent = message;
}

function saveAgentConfig() {
  const config = formAgentConfig();
  try {
    localStorage.setItem(AGENT_CONFIG_KEY, JSON.stringify(config));
  } catch {
    setAgentConfigSaveState("保存失败");
    toast("Agent 配置无法保存，请检查浏览器本地存储空间。", true);
    return false;
  }
  const time = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date());
  setAgentConfigSaveState(`已保存 · ${time}`);
  renderAgentAvatar(config.avatar_data, config.agent_name);
  if (config.save_notices) toast("Saved · Agent 配置已保存到当前浏览器");
  return true;
}

function scheduleAgentConfigSave() {
  clearTimeout(agentConfigSaveTimer);
  setAgentConfigSaveState("等待自动保存");
  agentConfigSaveTimer = setTimeout(saveAgentConfig, 2000);
}

function selectAgentAvatar(file) {
  if (!file) return;
  const allowedTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
  if (!allowedTypes.has(file.type) || file.size > 512 * 1024) {
    toast("请选择不超过 512 KB 的 PNG、JPEG 或 WebP 图片。", true);
    $("#agentAvatarInput").value = "";
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    agentAvatarData = typeof reader.result === "string" ? reader.result : "";
    renderAgentAvatar(agentAvatarData, $("#agentName").value);
    scheduleAgentConfigSave();
  }, { once: true });
  reader.readAsDataURL(file);
}

function formPersona() {
  return {
    name: $("#personaName").value.trim(),
    traits: parseTraits($("#personaTraits").value),
    detail: $("#personaDetail").value.trim(),
  };
}

function setFormPersona(persona = {}) {
  $("#personaName").value = persona.name || "";
  $("#personaTraits").value = traitsText(persona.traits);
  $("#personaDetail").value = persona.detail || "";
}

function renderDraftStatus(record = null) {
  $("#draftSaveStatus").textContent = record ? `已保存 · ${formatDate(record.updated_at)}` : "尚未保存";
  const name = record?.name || formPersona().name;
  $("#sandboxPersonaState").textContent = name ? `正在测试：${name}` : "未加载任何人格";
}

function renderPersonaList() {
  const node = $("#personaList");
  const records = state.personas;
  if (!records.length) {
    node.innerHTML = '<p class="empty-personas">还没有保存的人格草稿。</p>';
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const record of records) {
    const row = document.createElement("div");
    row.className = `persona-list-row${record.persona_id === state.editingPersonaId ? " active" : ""}`;
    row.dataset.personaId = record.persona_id;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "persona-list-item";
    button.dataset.personaSelect = record.persona_id;
    const name = document.createElement("strong");
    const detail = document.createElement("small");
    name.textContent = record.name;
    detail.textContent = traitsText(record.traits) || "未填写性格词";
    button.append(name, detail);
    const actions = document.createElement("span");
    actions.className = "persona-list-actions";
    const duplicate = document.createElement("button");
    duplicate.type = "button";
    duplicate.className = "persona-list-action";
    duplicate.dataset.personaDuplicate = record.persona_id;
    duplicate.textContent = "复制";
    duplicate.setAttribute("aria-label", `复制 ${record.name}`);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "persona-list-action danger";
    remove.dataset.personaDelete = record.persona_id;
    remove.textContent = "删除";
    remove.setAttribute("aria-label", `删除 ${record.name}`);
    actions.append(duplicate, remove);
    row.append(button, actions);
    fragment.append(row);
  }
  node.replaceChildren(fragment);
}

function selectDraft(id) {
  const record = state.personas.find((item) => item.persona_id === id);
  if (!record) return;
  state.editingPersonaId = record.persona_id;
  setFormPersona(record);
  renderDraftStatus(record);
  renderPersonaList();
}

async function duplicatePersona(id) {
  const source = state.personas.find((item) => item.persona_id === id);
  if (!source) return;
  try {
    const record = await jsonFetch(SANDBOX_PERSONA_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: state.personaOwnerId,
        name: `${source.name} - \u526f\u672c`,
        traits: parseTraits(source.traits),
        detail: source.detail || "",
        model_label: source.model_label || null,
      }),
    });
    state.personas.unshift(record);
    state.editingPersonaId = record.persona_id;
    setFormPersona(record);
    renderPersonaList();
    renderDraftStatus(record);
    toast("人格草稿已复制。");
  } catch {
    toast("复制人格草稿失败，请稍后重试。", true);
  }
}

async function deletePersona(id) {
  const record = state.personas.find((item) => item.persona_id === id);
  if (!record || !window.confirm(`确定删除“${record.name}”吗？此操作不可撤销。`)) return;
  try {
    const query = new URLSearchParams({ user_id: state.personaOwnerId });
    await jsonFetch(`${SANDBOX_PERSONA_API}/${encodeURIComponent(id)}?${query}`, { method: "DELETE" });
    state.personas = state.personas.filter((item) => item.persona_id !== id);
    if (state.editingPersonaId === id) {
      state.editingPersonaId = null;
      setFormPersona();
    }
    renderPersonaList();
    renderDraftStatus();
    toast("人格草稿已删除。");
  } catch {
    toast("删除人格草稿失败，请稍后重试。", true);
  }
}

function selectPreset(name) {
  const preset = presets[name];
  if (!preset) return;
  state.editingPersonaId = null;
  setFormPersona(preset);
  renderDraftStatus();
}

async function savePersona() {
  if (state.personaSaveBusy) return null;
  if (state.authEnabled && !state.account) {
    toast("请先登录账户，再保存可在沙盒加载的人格草稿。", true);
    openAuthDialog();
    return null;
  }
  const persona = formPersona();
  if (!persona.name) {
    $("#personaName").focus();
    toast("请先填写人格名字。", true);
    return null;
  }
  const model = readModelDraft();
  const payload = {
    user_id: state.personaOwnerId,
    ...persona,
    model_label: model?.bound ? model.name : null,
  };
  state.personaSaveBusy = true;
  const saveButton = $("#personaForm button[type=submit]");
  saveButton.disabled = true;
  saveButton.setAttribute("aria-busy", "true");
  saveButton.textContent = "保存中…";
  try {
    const url = state.editingPersonaId
      ? `${SANDBOX_PERSONA_API}/${encodeURIComponent(state.editingPersonaId)}`
      : SANDBOX_PERSONA_API;
    const record = await jsonFetch(url, {
      method: state.editingPersonaId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const index = state.personas.findIndex((item) => item.persona_id === record.persona_id);
    if (index >= 0) state.personas[index] = record;
    else state.personas.unshift(record);
    state.editingPersonaId = record.persona_id;
    renderDraftStatus(record);
    renderPersonaList();
    toast("人格草稿已保存到本机服务。服务重启后仍可加载。");
    return record;
  } catch {
    toast("人格草稿没有保存成功，请检查本机服务。", true);
    return null;
  } finally {
    state.personaSaveBusy = false;
    saveButton.disabled = false;
    saveButton.removeAttribute("aria-busy");
    saveButton.textContent = "保存草稿到本机服务";
  }
}

function clearDraft() {
  setFormPersona();
  state.editingPersonaId = null;
  renderDraftStatus();
  renderPersonaList();
  toast("已清空编辑区；已保存的人格不会被删除。");
}

async function openSandbox(event) {
  event.preventDefault();
  const record = state.editingPersonaId
    ? state.personas.find((item) => item.persona_id === state.editingPersonaId)
    : await savePersona();
  if (!record?.persona_id) return;
  const params = new URLSearchParams({ persona: record.persona_id });
  const prompt = $("#sandboxPrompt").value.trim();
  if (prompt) params.set("prompt", prompt);
  location.assign(`/desk?${params}`);
}

function renderModelDraft(draft = readModelDraft()) {
  const card = $("#modelDraftCard");
  if (!draft?.name) { card.hidden = true; return; }
  $("#modelDraftName").textContent = draft.name;
  $("#bindModel").checked = Boolean(draft.bound);
  card.hidden = false;
}

function selectModelFile(file) {
  if (!file) return;
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!["zip", "safetensors", "gguf"].includes(extension)) {
    toast("请选择 .zip、.safetensors 或 .gguf 文件。", true);
    return;
  }
  const draft = { name: file.name, bound: false, selectedAt: new Date().toISOString() };
  localStorage.setItem(MODEL_DRAFT_KEY, JSON.stringify(draft));
  renderModelDraft(draft);
  toast("已记录模型文件名；文件没有上传或部署。");
}

function setModelBinding(bound) {
  const draft = readModelDraft();
  if (!draft?.name) return;
  draft.bound = bound;
  localStorage.setItem(MODEL_DRAFT_KEY, JSON.stringify(draft));
  renderModelDraft(draft);
}

function activateView(target) {
  document.querySelectorAll(".workshop-view").forEach((view) => {
    const active = view.dataset.view === target;
    view.setAttribute("aria-hidden", String(!active));
    view.hidden = !active;
    view.classList.toggle("active", active);
  });
  document.querySelectorAll("[data-workshop-view]").forEach((button) => {
    const active = button.dataset.workshopView === target;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  const params = new URLSearchParams(location.search);
  if (params.get("view") !== target) {
    params.set("view", target);
    history.replaceState(null, "", `${location.pathname}?${params}`);
  }
  if (target === "memory") loadMemories();
}

function handleTablistKeydown(event) {
  const current = event.target.closest('[role="tab"]');
  if (!current || !event.currentTarget.contains(current)) return;
  const tabs = [...event.currentTarget.querySelectorAll('[role="tab"]:not(:disabled)')];
  if (tabs.length < 2) return;
  const index = tabs.indexOf(current);
  if (index < 0) return;
  let nextIndex = index;
  if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % tabs.length;
  if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (index - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") nextIndex = 0;
  if (event.key === "End") nextIndex = tabs.length - 1;
  if (nextIndex === index) return;
  event.preventDefault();
  tabs[nextIndex].focus();
  tabs[nextIndex].click();
}

function setCloudState({ loggedIn = false, available = false } = {}) {
  const cloud = $(".cloud-card");
  const action = $("#cloudAuthAction");
  if (!loggedIn) {
    cloud.dataset.cloudState = "locked";
    $("#cloudStatus").textContent = "登录后解锁云端同步";
    $("#cloudDescription").textContent = "当前未登录。云端发布不会从本机草稿自动发生。";
    action.textContent = "登录以查看云端状态";
    action.disabled = false;
    $("#footerCloudState").textContent = "云端同步需登录";
    return;
  }
  cloud.dataset.cloudState = available ? "ready" : "unavailable";
  $("#cloudStatus").textContent = available ? "可发布到云端" : "云端人格发布尚未接入";
  $("#cloudDescription").textContent = available ? "当前人格可发布到服务器。" : "账户已登录，但当前后端尚未启用人格云端发布。";
  action.textContent = available ? "发布到云端" : "云端发布暂不可用";
  action.disabled = true;
  $("#footerCloudState").textContent = available ? "云端发布可用" : "云端发布未启用";
}

function openAuthDialog() {
  const dialog = $("#authDialog");
  $("#authFrame").src = "/auth?embed=1&return_to=%2Fme";
  if (!dialog.open) dialog.showModal();
}

function renderLocalAccountState(message) {
  state.account = null;
  document.body.dataset.profileState = "local";
  $("#workshopAccountState").textContent = message || "当前处于本地创作模式：人格草稿只保存在本机服务。";
  $("#openAuth").textContent = "登录";
  $("#sidebarUsername").textContent = "本地创作者";
  $("#sidebarAccountState").textContent = "本机工作区";
  $("#profileDisplayName").textContent = "本地创作者";
  $("#profileEmail").textContent = "尚未登录";
  $("#profileCreatedAt").textContent = "登录后显示";
  $("#profileSessionExpiry").textContent = "登录后显示";
  $("#securitySessionState").textContent = "当前没有服务端账户会话。";
  $("#logoutAction").disabled = true;
  setCloudState();
}

function renderAccount(account) {
  state.account = account;
  state.personaOwnerId = account.profile_id || state.personaOwnerId;
  document.body.dataset.profileState = "account";
  $("#workshopAccountState").textContent = `${account.display_name} 已登录：记忆档案可按账户边界读取。`;
  $("#openAuth").textContent = account.display_name;
  $("#sidebarUsername").textContent = account.display_name;
  $("#sidebarAccountState").textContent = "账户已登录";
  $("#profileDisplayName").textContent = account.display_name;
  $("#profileEmail").textContent = account.email;
  $("#profileCreatedAt").textContent = formatDate(account.created_at);
  $("#profileSessionExpiry").textContent = formatDate(account.session_expires_at);
  $("#securitySessionState").textContent = `当前会话有效至 ${formatDate(account.session_expires_at)}。`;
  $("#logoutAction").disabled = false;
  setCloudState({ loggedIn: true, available: false });
}

async function logoutAccount() {
  if (!state.account) return;
  $("#logoutAction").disabled = true;
  try {
    await jsonFetch("/api/v1/auth/logout", { method: "POST" });
    sessionStorage.removeItem("hutao_csrf_token");
    renderLocalAccountState("已退出账户；本地 Agent 配置和人格草稿仍保留在本机。 ");
    state.personas = [];
    state.editingPersonaId = null;
    renderPersonaList();
    renderDraftStatus();
    toast("已退出登录。");
    activateView("configuration");
  } catch {
    $("#logoutAction").disabled = false;
    toast("退出登录没有完成，请稍后重试。", true);
  }
}

function memoryEmpty(message, countLabel = null) {
  const node = document.createElement("p");
  node.className = "empty-state";
  node.textContent = message;
  $("#memoryList").replaceChildren(node);
  if (countLabel) $("#memoryCountLabel").textContent = countLabel;
  if (!countLabel) $("#memoryCountLabel").textContent = "0 条记录";
}

function renderMemoryList() {
  const query = $("#memorySearch")?.value.trim().toLowerCase() || "";
  const filter = $("#memoryFilter")?.value || "all";
  const records = state.memoryRecords.filter((memory) => {
    const type = memory.memory_type || "会话记忆";
    const matchesType = filter === "all" || type === filter;
    const matchesQuery = !query || `${type} ${memory.content}`.toLowerCase().includes(query);
    return matchesType && matchesQuery;
  });
  $("#memoryCountLabel").textContent = `${records.length} / ${state.memoryRecords.length} 条记录`;
  if (!records.length) {
    memoryEmpty(
      query || filter !== "all" ? "没有符合筛选条件的记忆。" : "当前账户还没有可展示的长期记忆。",
      `${records.length} / ${state.memoryRecords.length} 条记录`,
    );
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const memory of records) {
    const article = document.createElement("article");
    article.className = "memory-item";
    article.dataset.memoryId = memory.id;
    const heading = document.createElement("div");
    heading.className = "memory-item-meta";
    const type = document.createElement("span");
    type.className = "memory-type";
    type.textContent = memory.memory_type || "会话记忆";
    const time = document.createElement("time");
    time.textContent = formatDate(memory.updated_at);
    heading.append(type, time);
    const select = document.createElement("button");
    select.type = "button";
    select.className = "memory-item-select";
    select.dataset.memorySelect = memory.id;
    select.setAttribute("aria-expanded", "false");
    select.textContent = memory.content;
    const detail = document.createElement("p");
    detail.className = "memory-item-detail";
    detail.hidden = true;
    detail.textContent = `创建于 ${formatDate(memory.created_at)}${memory.confidence == null ? "" : ` · 置信度 ${Math.round(memory.confidence * 100)}%`}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "memory-delete";
    remove.textContent = "删除";
    remove.title = "删除记忆";
    remove.dataset.memoryId = memory.id;
    article.append(heading, select, detail, remove);
    fragment.append(article);
  }
  $("#memoryList").replaceChildren(fragment);
}

async function loadMemories() {
  if (!state.authEnabled || !state.account) {
    $("#memoryArchive").hidden = true;
    $("#memoryGate").hidden = false;
    return;
  }
  $("#memoryGate").hidden = true;
  $("#memoryArchive").hidden = false;
  memoryEmpty("正在读取账户记忆...");
  try {
    const data = await jsonFetch("/api/v1/memories");
    state.memoryRecords = Array.isArray(data.memories) ? data.memories : [];
    const types = [...new Set(state.memoryRecords.map((memory) => memory.memory_type || "会话记忆"))];
    const filter = $("#memoryFilter");
    const currentFilter = filter.value;
    filter.replaceChildren(new Option("全部类型", "all"), ...types.map((type) => new Option(type, type)));
    filter.value = types.includes(currentFilter) ? currentFilter : "all";
    $("#memoryStatus").textContent = `当前账户记忆 · ${state.memoryRecords.length} 条`;
    renderMemoryList();
  } catch (error) {
    if (error.status === 401) return renderLocalAccountState("账户会话已失效，请重新登录。");
    memoryEmpty("记忆暂时无法读取，请稍后重试。");
  }
}

async function loadAccount() {
  try {
    const status = await jsonFetch("/api/v1/auth/status");
    state.authEnabled = Boolean(status.authentication_enabled);
    if (!state.authEnabled) return renderLocalAccountState("本地创作模式：人格草稿只保存在本机服务。");
    renderAccount(await jsonFetch("/api/v1/auth/me"));
    if (document.querySelector('[data-view="memory"].active')) await loadMemories();
  } catch (error) {
    if (error.status === 401) return renderLocalAccountState("登录后可读取账户记忆；本地人格草稿不会自动同步。");
    renderLocalAccountState("暂时无法确认账户状态；本地草稿不受影响。");
  }
}

$("#personaForm").addEventListener("submit", (event) => { event.preventDefault(); savePersona(); });
$("#clearDraft").addEventListener("click", clearDraft);
$("#sandboxForm").addEventListener("submit", openSandbox);
document.querySelectorAll("[data-preset]").forEach((button) => button.addEventListener("click", () => selectPreset(button.dataset.preset)));
document.querySelectorAll("[data-workshop-view]").forEach((button) => button.addEventListener("click", () => activateView(button.dataset.workshopView)));
document.querySelectorAll('[role="tablist"]').forEach((tablist) => tablist.addEventListener("keydown", handleTablistKeydown));
document.querySelectorAll("[data-agent-config]").forEach((control) => control.addEventListener("input", () => {
  $("#temperatureValue").textContent = Number($("#temperature").value).toFixed(1);
  $("#topPValue").textContent = Number($("#topP").value).toFixed(2).replace(/0$/, "");
  renderAgentAvatar(agentAvatarData, $("#agentName").value);
  scheduleAgentConfigSave();
}));
$("#localSaveNotices").addEventListener("change", scheduleAgentConfigSave);
$("#agentAvatarInput").addEventListener("change", (event) => selectAgentAvatar(event.currentTarget.files?.[0]));
$("#profileAuthAction").addEventListener("click", openAuthDialog);
$("#logoutAction").addEventListener("click", logoutAccount);
$("#personaList").addEventListener("click", (event) => {
  const duplicate = event.target.closest("[data-persona-duplicate]");
  if (duplicate) return duplicatePersona(duplicate.dataset.personaDuplicate);
  const remove = event.target.closest("[data-persona-delete]");
  if (remove) return deletePersona(remove.dataset.personaDelete);
  const button = event.target.closest("[data-persona-select]");
  if (button) selectDraft(button.dataset.personaSelect);
});
$("#modelFile").addEventListener("change", (event) => selectModelFile(event.currentTarget.files?.[0]));
$("#bindModel").addEventListener("change", (event) => setModelBinding(event.currentTarget.checked));
$("#openAuth").addEventListener("click", openAuthDialog);
$("#cloudAuthAction").addEventListener("click", () => { if (!state.account) openAuthDialog(); });
$("#memoryAuthAction").addEventListener("click", openAuthDialog);
$("#refreshMemories").addEventListener("click", loadMemories);
$("#memorySearch").addEventListener("input", renderMemoryList);
$("#memoryFilter").addEventListener("change", renderMemoryList);
$("#memoryList").addEventListener("click", (event) => {
  const select = event.target.closest("[data-memory-select]");
  if (select) {
    const detail = select.nextElementSibling;
    const expanded = select.getAttribute("aria-expanded") === "true";
    select.setAttribute("aria-expanded", String(!expanded));
    detail.hidden = expanded;
    select.closest(".memory-item")?.classList.toggle("is-selected", !expanded);
    return;
  }
  const button = event.target.closest("[data-memory-id]");
  if (!button) return;
  state.pendingMemoryId = button.dataset.memoryId;
  $("#deleteDialog").showModal();
});
$("#deleteDialog").addEventListener("close", async () => {
  if ($("#deleteDialog").returnValue !== "confirm" || !state.pendingMemoryId) return;
  const memoryId = state.pendingMemoryId;
  state.pendingMemoryId = null;
  try {
    const result = await jsonFetch(`/api/v1/memories/${encodeURIComponent(memoryId)}`, { method: "DELETE" });
    if (!result.deleted) throw new Error("memory not found");
    toast("长期记忆已删除。");
    await loadMemories();
  } catch (error) {
    toast(error.status === 401 ? "账户会话已失效。" : "删除没有完成，请稍后重试。", true);
  }
});
window.addEventListener("message", (event) => {
  if (event.origin !== location.origin || event.data?.type !== "personacore-auth-complete") return;
  $("#authDialog").close();
  loadAccount().then(async () => {
    if (state.account) {
      await migrateLegacyPersonas();
      await loadPersonas();
    }
  });
});

async function bootstrapWorkshop() {
  renderAgentConfig();
  const requestedView = new URLSearchParams(location.search).get("view");
  const availableViews = new Set(["persona", "profile", "security", "configuration", "models", "memory", "notifications", "billing"]);
  activateView(availableViews.has(requestedView) ? requestedView : "persona");
  renderModelDraft();
  await loadCapabilities();
  await loadAccount();
  if (!state.authEnabled || state.account) {
    await migrateLegacyPersonas();
    await loadPersonas();
  } else {
    renderPersonaList();
    renderDraftStatus();
  }
}

bootstrapWorkshop();
