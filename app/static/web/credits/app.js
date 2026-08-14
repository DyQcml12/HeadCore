const creditsList = document.querySelector("#creditsList");
const registryCount = document.querySelector("#registryCount");
const registryStatus = document.querySelector("#registryStatus");

const STATUS_META = Object.freeze({
  confirmed: {
    className: "status-confirmed",
    label: "Confirmed",
    accessibleLabel: "已确认",
  },
  restricted: {
    className: "status-restricted",
    label: "Restricted",
    accessibleLabel: "受限",
  },
  reference: {
    className: "status-review",
    label: "Review",
    accessibleLabel: "待审查",
  },
  unknown: {
    className: "status-review",
    label: "Review",
    accessibleLabel: "待审查",
  },
});

function createElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function getStatusMeta(status) {
  return STATUS_META[String(status).toLowerCase()] || STATUS_META.unknown;
}

function getInitials(name) {
  const normalized = String(name || "").trim();
  const words = normalized.split(/[\s_-]+/).filter(Boolean);

  if (words.length > 1) {
    return words
      .slice(0, 2)
      .map((word) => word.charAt(0))
      .join("")
      .toUpperCase();
  }

  return normalized.replace(/[^a-z0-9]/gi, "").slice(0, 2).toUpperCase() || "HC";
}

function getSourceHost(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "上游来源";
  }
}

function buildEntry(entry, index) {
  const article = createElement("article", "registry-card");
  const titleId = `registry-item-${index}`;
  article.setAttribute("aria-labelledby", titleId);

  const logo = createElement("span", "registry-logo", getInitials(entry.name));
  logo.setAttribute("aria-hidden", "true");

  const content = createElement("div", "registry-content");
  const titleRow = createElement("div", "registry-title-row");
  const title = createElement("h3", "", entry.name || "未命名条目");
  title.id = titleId;
  const category = createElement("span", "registry-category", entry.category || "未分类");
  titleRow.append(title, category);

  const description = createElement("p", "registry-description", entry.usage || "暂无使用说明。");
  content.append(titleRow, description);

  if (entry.url) {
    const sourceLink = createElement("a", "source-link", `Source · ${getSourceHost(entry.url)}`);
    sourceLink.href = entry.url;
    sourceLink.target = "_blank";
    sourceLink.rel = "noopener noreferrer";
    sourceLink.setAttribute("aria-label", `查看 ${entry.name || "该条目"} 的上游来源（在新窗口打开）`);
    sourceLink.append(createElement("span", "source-arrow", "↗"));
    content.append(sourceLink);
  }

  const meta = createElement("div", "registry-meta");
  const license = createElement("div", "license-block");
  license.append(
    createElement("span", "license-label", "License"),
    createElement("strong", "license-value", entry.license || "Not specified"),
  );

  const statusMeta = getStatusMeta(entry.commercial_status);
  const status = createElement("span", `status-pill ${statusMeta.className}`);
  status.setAttribute("aria-label", `状态：${statusMeta.accessibleLabel}`);
  const statusDot = createElement("span", "status-dot");
  statusDot.setAttribute("aria-hidden", "true");
  status.append(statusDot, document.createTextNode(statusMeta.label));
  meta.append(license, status);

  article.append(logo, content, meta);
  return article;
}

function showErrorState() {
  const error = createElement("div", "registry-error");
  error.setAttribute("role", "alert");
  const copy = createElement("div", "");
  copy.append(
    createElement("strong", "", "登记数据暂时不可用"),
    createElement("p", "", "请确认本地服务正在运行，然后重新加载。"),
  );
  const retryButton = createElement("button", "retry-button", "重新加载");
  retryButton.type = "button";
  retryButton.addEventListener("click", loadCredits);
  error.append(copy, retryButton);
  creditsList.replaceChildren(error);
}

function showEmptyState() {
  const empty = createElement("p", "registry-empty", "当前没有已登记条目。");
  creditsList.replaceChildren(empty);
}

async function loadCredits() {
  creditsList.setAttribute("aria-busy", "true");
  registryCount.textContent = "--";
  registryStatus.textContent = "正在读取登记数据";
  creditsList.replaceChildren(createElement("p", "registry-loading", "正在读取登记数据..."));

  try {
    const response = await fetch("/credits/data.json", { credentials: "same-origin" });
    if (!response.ok) throw new Error("registry unavailable");

    const entries = await response.json();
    if (!Array.isArray(entries)) throw new TypeError("registry must be an array");

    if (entries.length === 0) {
      showEmptyState();
    } else {
      const fragment = document.createDocumentFragment();
      entries.forEach((entry, index) => fragment.append(buildEntry(entry, index)));
      creditsList.replaceChildren(fragment);
    }

    registryCount.textContent = String(entries.length);
    registryStatus.textContent = `已登记 ${entries.length} 项`;
  } catch {
    registryCount.textContent = "0";
    registryStatus.textContent = "读取失败";
    showErrorState();
  } finally {
    creditsList.setAttribute("aria-busy", "false");
  }
}

loadCredits();
