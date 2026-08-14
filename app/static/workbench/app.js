const $ = (selector) => document.querySelector(selector);

let activeSessionId = "";
let capturePoll = 0;

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )hutao_workbench_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function setHeaderStatus(text, state = "restricted") {
  const node = $("#headerStatus");
  node.textContent = text;
  node.dataset.state = state;
}

function showAccess(message = "", enabled = true) {
  $("#accessGate").hidden = false;
  $("#workbenchPanel").hidden = true;
  $("#logoutButton").hidden = true;
  $("#gateNote").textContent = message || "等待管理员认证";
  for (const control of $("#loginForm").elements) control.disabled = !enabled;
  if (enabled) $("#adminSecret").focus();
}

function showWorkspace() {
  $("#accessGate").hidden = true;
  $("#workbenchPanel").hidden = false;
  $("#logoutButton").hidden = false;
}

function showError(selector, message = "") {
  const node = $(selector);
  node.textContent = message;
  node.hidden = !message;
}

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "--" : date.toLocaleString("zh-CN", { hour12: false });
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== "GET") {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", token);
  }
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : "";
    const error = new Error(detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function renderStatus(data) {
  const camera = data.camera || {};
  const available = Boolean(camera.available);
  $("#cameraAvailability").textContent = available ? "已就绪" : "未启用";
  $("#cameraAvailability").dataset.state = available ? "ready" : "disabled";
  $("#cameraDuration").textContent = `${camera.max_session_seconds || 0} 秒`;
  $("#frameRetention").textContent = camera.raw_frame_retention_seconds === 0 ? "不保留" : "已限制";
  $("#faceIdentification").textContent = camera.face_identification_enabled ? "已启用" : "未启用";
  $("#sessionExpiry").textContent = `管理员会话至 ${formatTime(data.session_expires_at)}`;
  $("#createSessionButton").disabled = !available;
  setHeaderStatus(available ? "本地感知可用" : "本地感知未启用", available ? "ready" : "restricted");
}

function renderSession(session) {
  activeSessionId = session.session_id;
  $("#sessionState").dataset.state = session.status;
  $("#sessionStateTitle").textContent = session.status === "active" ? "会话有效" : "会话已结束";
  $("#sessionStateDetail").textContent = `摄像头 ${session.camera_slot}，有效至 ${formatTime(session.expires_at)}`;
  $("#sessionIdValue").textContent = session.session_id;
  $("#sessionExpiryValue").textContent = formatTime(session.expires_at);
  $("#sessionDetail").hidden = false;
  $("#stopSessionButton").hidden = session.status !== "active";
  $("#captureControls").hidden = session.status !== "active";
  $("#startCaptureButton").hidden = session.status !== "active";
  if (session.status === "active") startCapturePolling();
  else stopCapturePolling();
}

function renderCapture(data) {
  const running = Boolean(data.running);
  $("#captureState").dataset.state = running ? "running" : "idle";
  $("#captureStateText").textContent = running ? "本地采集中" : "本地采集未启动";
  $("#startCaptureButton").hidden = running;
  $("#stopCaptureButton").hidden = !running;
}

function renderObservation(data) {
  if (!data.available) {
    $("#observationText").textContent = "尚无稳定观察结果";
    return;
  }
  const labels = [data.scene_label, ...(data.objects || []), ...(data.pose_labels || []), ...(data.gesture_labels || []), ...(data.facial_cues || [])].filter(Boolean);
  $("#observationText").textContent = labels.length ? labels.join(" · ") : "尚无稳定观察结果";
}

async function refreshCapture() {
  if (!activeSessionId) return;
  try {
    const [capture, observation] = await Promise.all([
      request(`/api/workbench/camera/sessions/${encodeURIComponent(activeSessionId)}/capture/status`),
      request(`/api/workbench/camera/sessions/${encodeURIComponent(activeSessionId)}/perception/status`),
    ]);
    renderCapture(capture);
    renderObservation(observation);
  } catch (error) {
    if (error.status === 404) {
      activeSessionId = "";
      stopCapturePolling();
      $("#captureControls").hidden = true;
    }
  }
}

function startCapturePolling() {
  stopCapturePolling();
  refreshCapture();
  capturePoll = window.setInterval(refreshCapture, 3000);
}

function stopCapturePolling() {
  if (!capturePoll) return;
  window.clearInterval(capturePoll);
  capturePoll = 0;
}

async function refreshStatus() {
  try {
    const data = await request("/api/workbench/status");
    showWorkspace();
    renderStatus(data);
  } catch (error) {
    if (error.status === 401) {
      setHeaderStatus("访问受限", "restricted");
      showAccess();
      return;
    }
    const unavailable = error.status === 404;
    setHeaderStatus(unavailable ? "工作台未启用" : "连接失败", "restricted");
    showAccess(unavailable ? "本机工作台尚未配置" : "无法确认管理员会话", false);
  }
}

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const button = form.querySelector("button");
  button.disabled = true;
  showError("#loginError");
  try {
    await request("/api/workbench/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ secret: $("#adminSecret").value }),
    });
    form.reset();
    await refreshStatus();
  } catch (error) {
    showError("#loginError", error.status === 401 ? "口令不正确" : "当前无法进入工作台");
  } finally {
    button.disabled = false;
  }
});

$("#sessionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const button = $("#createSessionButton");
  button.disabled = true;
  showError("#sessionError");
  try {
    const session = await request("/api/workbench/camera/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        consent_granted: $("#cameraConsent").checked,
        camera_slot: Number($("#cameraSlot").value),
      }),
    });
    renderSession(session);
  } catch (error) {
    showError("#sessionError", error.status === 409 ? "本地感知未启用" : "会话未创建");
  } finally {
    button.disabled = false;
  }
});

$("#stopSessionButton").addEventListener("click", async () => {
  if (!activeSessionId) return;
  const button = $("#stopSessionButton");
  button.disabled = true;
  try {
    const session = await request(`/api/workbench/camera/sessions/${encodeURIComponent(activeSessionId)}/stop`, { method: "POST" });
    renderSession(session);
  } catch (error) {
    showError("#sessionError", "会话未能结束");
  } finally {
    button.disabled = false;
  }
});

$("#startCaptureButton").addEventListener("click", async () => {
  if (!activeSessionId) return;
  const button = $("#startCaptureButton");
  button.disabled = true;
  try {
    await request(`/api/workbench/camera/sessions/${encodeURIComponent(activeSessionId)}/capture/start`, { method: "POST" });
    await refreshCapture();
  } catch (error) {
    showError("#sessionError", error.status === 409 ? "会话已失效或本地感知未启用" : "本地采集未启动");
  } finally {
    button.disabled = false;
  }
});

$("#stopCaptureButton").addEventListener("click", async () => {
  if (!activeSessionId) return;
  const button = $("#stopCaptureButton");
  button.disabled = true;
  try {
    await request(`/api/workbench/camera/sessions/${encodeURIComponent(activeSessionId)}/capture/stop`, { method: "POST" });
    await refreshCapture();
  } catch (error) {
    showError("#sessionError", "本地采集未能停止");
  } finally {
    button.disabled = false;
  }
});

$("#logoutButton").addEventListener("click", async () => {
  try {
    await request("/api/workbench/logout", { method: "POST" });
  } finally {
    activeSessionId = "";
    stopCapturePolling();
    setHeaderStatus("访问受限", "restricted");
    showAccess();
  }
});

refreshStatus();
