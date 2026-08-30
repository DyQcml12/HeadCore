const STATUS_LABELS = {
  online: "正常",
  offline: "离线",
  degraded: "降级",
  missing: "缺失",
  not_configured: "未配置",
  loading: "读取中",
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status || "未知";
}

async function fetchJson(url) {
  const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function showGate(status, message) {
  const gate = document.querySelector("#accessGate");
  const content = document.querySelector("#consoleContent");
  const title = document.querySelector("#gateTitle");
  const detail = document.querySelector("#gateMessage");
  const badge = document.querySelector("#accessBadge");
  gate.hidden = false;
  content.hidden = true;
  title.textContent = status === 403 ? "当前账号没有权限" : "需要管理员身份";
  detail.textContent = message || (status === 403 ? "该账号不是项目所有者，控制中心不会返回运行数据。" : "请先登录项目所有者账号。 ");
  badge.textContent = status === 403 ? "已拒绝" : "未登录";
  badge.className = `badge ${status === 403 ? "badge-danger" : "badge-neutral"}`;
}

function renderAccess(data) {
  const webOwner = data.mode === "web_session";
  const badge = document.querySelector("#accessBadge");
  const name = document.querySelector("#identityName");
  const meta = document.querySelector("#identityMeta");
  const expiry = document.querySelector("#identityExpiry");
  badge.textContent = webOwner ? "已验证" : "本机开发模式";
  badge.className = `badge ${webOwner ? "badge-success" : "badge-neutral"}`;
  name.textContent = data.display_name || (webOwner ? "项目所有者" : "本机开发者");
  meta.textContent = data.email || "未启用公网账号服务";
  expiry.textContent = data.session_expires_at ? `会话有效至 ${formatDate(data.session_expires_at)}` : "默认仅绑定本机进程";
  document.querySelector("#identityScope").textContent = data.scope || "local_control_plane";
  document.querySelector("#metricAuth").textContent = webOwner ? "OWNER" : "LOCAL";
  document.querySelector("#metricAuthDetail").textContent = data.mode === "web_session" ? "网页登录会话" : "本机开发模式";
}

function formatDate(value) {
  try { return new Date(value).toLocaleString("zh-CN", { hour12: false }); } catch { return value; }
}

function renderHealth(data) {
  const grid = document.querySelector("#statusGrid");
  const capabilities = document.querySelector("#capabilityList");
  grid.replaceChildren(); capabilities.replaceChildren();
  grid.setAttribute("aria-busy", "false");
  capabilities.setAttribute("aria-busy", "false");
  for (const item of data.items || []) {
    const card = element("article", `status-card status-${item.status}`);
    const top = element("div", "card-topline");
    top.append(element("strong", "status-title", item.label), element("span", `badge badge-${item.status}`, statusLabel(item.status)));
    card.append(top, element("p", "status-detail", item.detail));
    if (item.url) {
      const link = element("a", "inline-link", item.action || "查看");
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      card.append(link);
    }
    (item.id === "hutao_core" ? grid : capabilities).append(card);
  }
  const core = (data.items || []).find((item) => item.id === "hutao_core");
  document.querySelector("#metricCore").textContent = statusLabel(core?.status || "unknown");
  document.querySelector("#metricCoreDetail").textContent = core?.detail || "未返回状态";
  const memory = (data.items || []).find((item) => item.id === "memory");
  document.querySelector("#metricMemory").textContent = statusLabel(memory?.status || "not_configured");
  document.querySelector("#metricMemoryDetail").textContent = memory?.detail || "由当前配置决定";
}

function renderOperations(data, reports, errors) {
  const overall = document.querySelector("#operationsOverall");
  overall.textContent = statusLabel(data.state);
  overall.className = `state ${data.state}`;
  const list = document.querySelector("#operationsComponents");
  list.replaceChildren();
  for (const component of Object.values(data.components || {})) {
    const row = element("div", "diagnostic-row");
    const title = element("strong", "diagnostic-name", component.label);
    const category = element("span", "diagnostic-category", component.category);
    const state = element("span", `badge badge-${component.state}`, statusLabel(component.state));
    const detail = element("p", "diagnostic-detail", component.detail || "已检查");
    row.append(title, category, state, detail);
    list.append(row);
  }
  renderSimpleList("#operationsReports", reports.reports || [], (item) => `${item.suite}: ${item.passed} 通过${item.failed ? `，${item.failed} 失败` : ""}`);
  renderSimpleList("#operationsErrors", errors.errors || [], (item) => `${item.category}: ${item.count}`);
  document.querySelector("#metricServices").textContent = `${Object.keys(data.components || {}).length}`;
  document.querySelector("#metricServicesDetail").textContent = data.state === "online" ? "全部探针正常" : "存在需要关注的组件";
}

function renderSimpleList(selector, items, format) {
  const box = document.querySelector(selector);
  box.replaceChildren();
  if (!items.length) { box.append(element("p", "empty-state", "暂无记录")); return; }
  for (const item of items) box.append(element("p", "simple-row", format(item)));
}

function showError(message) {
  const error = document.querySelector("#pageError");
  error.textContent = message;
  error.hidden = false;
}

async function refresh() {
  const button = document.querySelector("#refreshBtn");
  const error = document.querySelector("#pageError");
  button.disabled = true;
  error.hidden = true;
  try {
    const access = await fetchJson("/api/control/access");
    renderAccess(access);
    const [health, operations, reports, errors] = await Promise.all([
      fetchJson("/api/control/status"),
      fetchJson("/api/control/operations/status"),
      fetchJson("/api/control/operations/test-reports?limit=6"),
      fetchJson("/api/control/operations/errors"),
    ]);
    renderHealth(health);
    renderOperations(operations, reports, errors);
    document.querySelector("#overviewState").textContent = "核心已连接";
    document.querySelector("#overviewState").className = "state online";
    document.querySelector("#lastUpdated").textContent = `最后更新 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
  } catch (cause) {
    if (cause.status === 401 || cause.status === 403) {
      showGate(cause.status);
    } else {
      showError(`读取状态失败：${cause.message}`);
    }
  } finally {
    button.disabled = false;
  }
}

document.querySelector("#refreshBtn").addEventListener("click", refresh);
document.querySelectorAll(".side-nav a").forEach((link) => link.addEventListener("click", () => {
  document.querySelectorAll(".side-nav a").forEach((item) => item.classList.remove("is-active"));
  link.classList.add("is-active");
}));
refresh();
