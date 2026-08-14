function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statusLabel(status) {
  return { online: "正常", offline: "离线", degraded: "降级", missing: "缺失", not_configured: "未配置" }[status] || status;
}

function renderHealth(data) {
  const grid = document.querySelector("#statusGrid");
  const capabilities = document.querySelector("#capabilityList");
  grid.replaceChildren(); capabilities.replaceChildren();
  for (const item of data.items || []) {
    const card = element("article", `status-card ${item.status}`);
    card.append(element("strong", "", item.label), element("span", `badge ${item.status}`, statusLabel(item.status)), element("p", "", item.detail));
    if (item.url) { const link = element("a", "", item.action || "查看"); link.href = item.url; link.target = "_blank"; link.rel = "noreferrer"; card.append(link); }
    (item.id === "hutao_core" ? grid : capabilities).append(card);
  }
}

function renderOperations(data, reports, errors) {
  const overall = document.querySelector("#operationsOverall");
  overall.textContent = data.state === "online" ? "运行正常" : "需要关注";
  overall.className = `state ${data.state}`;
  const list = document.querySelector("#operationsComponents"); list.replaceChildren();
  for (const component of Object.values(data.components || {})) {
    const row = element("div", "diagnostic-row");
    row.append(element("strong", "", component.label), element("span", "muted", component.category), element("span", `badge ${component.state}`, statusLabel(component.state)), element("p", "", component.detail || "已检查"));
    list.append(row);
  }
  renderSimpleList("#operationsReports", reports.reports || [], item => `${item.suite}: ${item.passed} 通过${item.failed ? `，${item.failed} 失败` : ""}`);
  renderSimpleList("#operationsErrors", errors.errors || [], item => `${item.category}: ${item.count}`);
}

function renderSimpleList(selector, items, format) {
  const box = document.querySelector(selector); box.replaceChildren();
  if (!items.length) { box.append(element("p", "muted", "暂无记录")); return; }
  for (const item of items) box.append(element("p", "simple-row", format(item)));
}

async function refresh() {
  const button = document.querySelector("#refreshBtn"); const error = document.querySelector("#pageError");
  button.disabled = true; error.hidden = true;
  try {
    const [health, operations, reports, errors] = await Promise.all([
      fetch("/api/control/status").then(r => r.json()), fetch("/api/control/operations/status").then(r => r.json()),
      fetch("/api/control/operations/test-reports?limit=6").then(r => r.json()), fetch("/api/control/operations/errors").then(r => r.json()),
    ]);
    renderHealth(health); renderOperations(operations, reports, errors);
    document.querySelector("#overviewState").textContent = "核心已连接";
    document.querySelector("#overviewState").className = "state online";
    document.querySelector("#lastUpdated").textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  } catch (cause) { error.textContent = `读取状态失败：${cause.message}`; error.hidden = false; }
  finally { button.disabled = false; }
}

document.querySelector("#refreshBtn").addEventListener("click", refresh);
refresh();
