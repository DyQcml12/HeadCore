const $ = (selector) => document.querySelector(selector);

let activeSessionId = "";
let activeSessionMode = "";
let capturePoll = 0;
let localStream = null;
let frameUploadTimer = 0;
let frameUploadBusy = false;
let frameCanvas = null;

const previewErrorMessages = {
  NotAllowedError: "浏览器未授予摄像头权限，请允许本机页面访问后重试",
  PermissionDeniedError: "浏览器未授予摄像头权限，请允许本机页面访问后重试",
  NotFoundError: "未发现可用摄像头设备，请检查摄像头连接",
  DevicesNotFoundError: "未发现可用摄像头设备，请检查摄像头连接",
  NotReadableError: "摄像头可能被其他程序占用，暂时无法读取",
  OverconstrainedError: "当前摄像头不支持请求的预览参数",
  SecurityError: "浏览器安全策略阻止了摄像头访问",
  AbortError: "摄像头访问被中止，请稍后重试",
};

const visionReasonMessages = {
  opencv_missing: "后端缺少 OpenCV，无法读取摄像头",
  mediapipe_missing: "未安装 MediaPipe，姿态与手势标签不可用",
  yolo_model_not_configured: "未配置 YOLO 模型，物体标签不可用",
  yolo_model_missing: "YOLO 模型路径不存在，物体标签不可用",
  ultralytics_missing: "未安装 Ultralytics，YOLO 模型无法加载",
  camera_device_unavailable: "后端找不到摄像头设备或设备已被占用",
  camera_frame_unavailable: "后端读取不到摄像头画面",
  camera_perception_disabled: "未开启 CAMERA_PERCEPTION_ENABLED",
  camera_local_capture_disabled: "未开启 CAMERA_LOCAL_CAPTURE_ENABLED",
  capture_dependency_missing: "本机图像解码依赖不可用",
  labeling_dependency_missing: "未配置可用的视觉识别模型",
};

const visualLabelNames = {
  person: "人物",
  backpack: "背包",
  book: "书",
  bottle: "瓶子",
  car: "车辆",
  cat: "猫",
  chair: "椅子",
  cup: "杯子",
  dog: "狗",
  keyboard: "键盘",
  laptop: "电脑",
  mouse: "鼠标",
  phone: "手机",
  screen: "屏幕",
  table: "桌子",
  desk: "桌面",
  indoor: "室内",
  room: "房间",
  outdoor: "室外",
  street: "街道",
  desk_work: "桌面工作",
  desk_setup: "桌面布置",
  street_vehicle: "街道车辆",
  person_present: "人物出现",
  unclassified: "未分类",
  standing: "站立",
  sitting: "坐姿",
  walking: "行走",
  leaning: "倚靠",
  head_down: "低头",
  pointing: "指向",
  raised_hand: "举手",
  waving: "挥手",
  writing: "书写",
  typing: "打字",
  head_down_detected: "检测到低头",
};

function localizeVisualLabel(label) {
  const value = String(label || "");
  return visualLabelNames[value] || value.replaceAll("_", " ");
}

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
  const gateNote = $("#gateNote");
  gateNote.textContent = enabled
    ? message || "等待管理员认证"
    : `${message || "本机工作台尚未配置"}。请在 .env 设置 VISUAL_WORKBENCH_ENABLED=true 和 VISUAL_WORKBENCH_ADMIN_SECRET 后重启本地服务。`;
  gateNote.dataset.state = enabled ? "ready" : "unavailable";
  // Keep the field editable so the page never looks like a broken form.
  for (const control of $("#loginForm").elements) control.disabled = false;
  $("#adminSecret").focus();
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

function setPreviewState(message, state = "idle") {
  const panel = $("#localPreviewPanel");
  const video = $("#localPreview");
  const status = $("#previewStatus");
  const badge = $("#previewBadge");
  panel.dataset.state = state;
  status.textContent = message;
  badge.textContent = state === "running" ? "预览中" : state === "demo" ? "演示数据" : state === "error" ? "不可用" : "等待采集";
  video.hidden = state !== "running";
}

function stopLocalPreview(message = "本地预览已停止", state = "idle") {
  stopFrameUpload();
  if (localStream) {
    for (const track of localStream.getTracks()) track.stop();
    localStream = null;
  }
  const video = $("#localPreview");
  video.pause();
  video.srcObject = null;
  setPreviewState(message, state);
}

function stopFrameUpload() {
  if (frameUploadTimer) window.clearInterval(frameUploadTimer);
  frameUploadTimer = 0;
  frameUploadBusy = false;
  frameCanvas = null;
}

function captureFrameBlob(video) {
  if (!frameCanvas || !video.videoWidth || !video.videoHeight) return Promise.resolve(null);
  const maxWidth = 960;
  const scale = Math.min(1, maxWidth / video.videoWidth);
  frameCanvas.width = Math.max(1, Math.round(video.videoWidth * scale));
  frameCanvas.height = Math.max(1, Math.round(video.videoHeight * scale));
  frameCanvas.getContext("2d", { alpha: false }).drawImage(video, 0, 0, frameCanvas.width, frameCanvas.height);
  return new Promise((resolve) => frameCanvas.toBlob(resolve, "image/jpeg", 0.72));
}

async function uploadCurrentFrame() {
  if (frameUploadBusy || !localStream || !activeSessionId || activeSessionMode === "demo") return;
  const video = $("#localPreview");
  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
  frameUploadBusy = true;
  try {
    const blob = await captureFrameBlob(video);
    if (!blob) return;
    const form = new FormData();
    form.append("frame", blob, "camera-frame.jpg");
    await request(`/api/workbench/camera/sessions/${encodeURIComponent(activeSessionId)}/frames`, {
      method: "POST",
      body: form,
    });
  } catch (error) {
    if ([409, 415, 422, 503].includes(error.status)) {
      stopFrameUpload();
      setPreviewState("本机分析未接受画面，请检查识别依赖", "error");
    }
  } finally {
    frameUploadBusy = false;
  }
}

function startFrameUpload() {
  stopFrameUpload();
  frameCanvas = document.createElement("canvas");
  uploadCurrentFrame();
  frameUploadTimer = window.setInterval(uploadCurrentFrame, 1000);
}

function previewErrorMessage(error) {
  return previewErrorMessages[error?.name] || "浏览器无法读取摄像头，请检查权限和设备后重试";
}

function captureStartErrorMessage(error) {
  if (error?.status === 401 || error?.status === 403) return "管理员会话已失效，请重新登录工作台";
  if (error?.status === 404) return "会话不存在，请重新创建摄像头会话";
  if (error?.status === 409) return "会话已失效或本地感知未就绪，请查看左侧诊断";
  if (error?.status === 503) return "本机识别服务不可用，请检查 OpenCV 和 MediaPipe";
  if (error?.status) return "工作台接口返回异常，请查看服务状态";
  if (previewErrorMessages[error?.name]) return previewErrorMessages[error.name];
  return "本地服务接口暂时不可达，请确认 127.0.0.1:8000 正在运行";
}

async function startLocalPreview() {
  stopLocalPreview("正在请求浏览器摄像头权限...");
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    const error = new Error("camera_preview_unavailable");
    error.name = "SecurityError";
    throw error;
  }
  try {
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    const video = $("#localPreview");
    video.srcObject = localStream;
    await video.play();
    setPreviewState("本地摄像头预览运行中", "running");
  } catch (error) {
    stopLocalPreview(previewErrorMessage(error), "error");
    throw error;
  }
}

function formatTime(value) {
  if (!value) return "--";
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
  const realAvailable = Boolean(camera.real_available);
  const demoReady = Boolean(camera.demo_available);
  const captureReady = Boolean(camera.capture_ready);
  const labelingReady = Boolean(camera.labeling_ready);
  const realReady = Boolean(camera.real_ready);
  const diagnostics = camera.diagnostics || {};
  const reasonCodes = Array.isArray(diagnostics.reason_codes) ? diagnostics.reason_codes : [];
  $("#cameraAvailability").textContent = !available
    ? "后端未启用"
    : demoReady && !realAvailable
      ? "本地演示可用"
      : captureReady
      ? "采集配置已启用"
      : "采集依赖缺失";
  $("#cameraAvailability").dataset.state = available ? "ready" : "disabled";
  const opencvAvailable = Boolean(diagnostics.opencv_available);
  $("#cameraBackend").textContent = !realAvailable
    ? "真实采集未启用"
    : opencvAvailable
      ? "本机解码可用"
      : "OpenCV 不可用";
  $("#cameraBackend").dataset.state = realAvailable && opencvAvailable ? "ready" : "disabled";
  $("#visionLabeling").textContent = !realAvailable
    ? "真实识别未启用"
    : labelingReady
      ? "识别链已就绪"
      : "识别模型未就绪";
  $("#visionLabeling").dataset.state = realAvailable && labelingReady ? "ready" : "disabled";
  $("#cameraDuration").textContent = `${camera.max_session_seconds || 0} 秒`;
  $("#frameRetention").textContent = camera.raw_frame_retention_seconds === 0 ? "不保留" : "已限制";
  $("#faceIdentification").textContent = camera.face_identification_enabled ? "已启用" : "未启用";
  $("#demoAvailability").textContent = demoReady ? "已启用" : "未启用";
  $("#demoAvailability").dataset.state = demoReady ? "ready" : "disabled";
  $("#visionDiagnostics").textContent = !available
    ? "视觉工作台默认关闭；启用本机配置后才会创建受限采集会话"
    : demoReady && !realAvailable
      ? "当前使用结构化演示数据，不访问摄像头、不保存原始画面"
      : !realReady
      ? [...(camera.real_blockers || []), ...reasonCodes]
        .filter((code, index, values) => values.indexOf(code) === index)
        .map((code) => visionReasonMessages[code] || `诊断：${code}`)
        .join("；")
      : reasonCodes.length
      ? reasonCodes.map((code) => visionReasonMessages[code] || `诊断：${code}`).join("；")
      : "采集依赖与识别链检查通过，可在明确同意后启动";
  $("#visionDiagnostics").dataset.state = reasonCodes.length || !available ? "restricted" : "ready";
  $("#sessionExpiry").textContent = `管理员会话至 ${formatTime(data.session_expires_at)}`;
  $("#createSessionButton").disabled = !realReady;
  $("#startDemoButton").disabled = !demoReady;
  if (!available || !realAvailable) stopLocalPreview(!available ? "后端未启用本地感知" : "演示模式不需要摄像头");
  setHeaderStatus(available ? (demoReady && !realAvailable ? "本地演示可用" : "本地感知可用") : "本地感知未启用", available ? "ready" : "restricted");
}

function renderSession(session) {
  activeSessionId = session.session_id;
  activeSessionMode = session.mode || "real";
  $("#sessionState").dataset.state = session.status;
  $("#sessionStateTitle").textContent = session.status === "active" ? "会话有效" : "会话已结束";
  $("#sessionStateDetail").textContent = activeSessionMode === "demo"
    ? `演示场景 ${session.demo_scenario || "desk_work"}，有效至 ${formatTime(session.expires_at)}`
    : `摄像头 ${session.camera_slot}，有效至 ${formatTime(session.expires_at)}`;
  $("#sessionIdValue").textContent = session.session_id;
  $("#sessionExpiryValue").textContent = formatTime(session.expires_at);
  $("#sessionDetail").hidden = false;
  $("#stopSessionButton").hidden = session.status !== "active";
  $("#captureControls").hidden = session.status !== "active";
  $("#startCaptureButton").hidden = session.status !== "active";
  if (session.status === "active") {
    setPreviewState(activeSessionMode === "demo" ? "启动后生成结构化演示观察，不访问摄像头" : "启动后由浏览器摄像头采集，并交给本机分析", "idle");
    startCapturePolling();
  } else {
    stopCapturePolling();
    stopLocalPreview("会话已结束，本地预览已停止");
  }
}

function renderLabelGroup(selector, labels, emptyText = "暂无") {
  const node = $(selector);
  node.replaceChildren();
  const values = [...new Set((labels || []).filter(Boolean).map((label) => String(label)))];
  if (!values.length) {
    const empty = document.createElement("em");
    empty.textContent = emptyText;
    node.append(empty);
    return;
  }
  for (const value of values) {
    const chip = document.createElement("span");
    chip.className = "label-chip";
    chip.textContent = localizeVisualLabel(value);
    node.append(chip);
  }
}

function formatVisualChange(change) {
  const value = String(change || "");
  const stateChange = value.match(/^state:([^:]+)->([^:]+)$/);
  if (stateChange) {
    return `场景：${localizeVisualLabel(stateChange[1])} → ${localizeVisualLabel(stateChange[2])}`;
  }
  const labelChange = value.match(/^(appeared|disappeared):([^:]+):(.+)$/);
  if (!labelChange) return localizeVisualLabel(value);
  const action = labelChange[1] === "appeared" ? "出现" : "消失";
  return `${action}：${localizeVisualLabel(labelChange[3])}`;
}

function summarizeObservation(data) {
  const objects = [...new Set((data.objects || []).filter(Boolean).map(String))];
  const poses = [...new Set((data.pose_labels || []).filter(Boolean).map(String))];
  const gestures = [...new Set((data.gesture_labels || []).filter(Boolean).map(String))];
  const parts = [];
  if (data.scene_state && data.scene_state !== "unclassified") {
    parts.push(`当前场景为${localizeVisualLabel(data.scene_state)}`);
  } else if (data.scene_label) {
    parts.push(`当前场景为${localizeVisualLabel(data.scene_label)}`);
  }
  if (objects.length) {
    parts.push(`画面中有${objects.map(localizeVisualLabel).join("、")}`);
  }
  if (poses.length) {
    parts.push(`姿态为${poses.map(localizeVisualLabel).join("、")}`);
  }
  if (gestures.length) {
    parts.push(`动作是${gestures.map(localizeVisualLabel).join("、")}`);
  }
  return parts.join("，") || "已确认画面，但暂未识别到可用标签";
}

function renderCapture(data) {
  const running = Boolean(data.running);
  const reasonCode = data.last_error || data.reason_code || "";
  const failed = Boolean(data.last_error) || data.state === "failed";
  const isDemo = data.mode === "demo" || activeSessionMode === "demo";
  const framesReceived = Number(data.frames_received || 0);
  const observationsEmitted = Number(data.observations_emitted || 0);
  $("#frameCount").textContent = Number.isFinite(framesReceived) ? String(framesReceived) : "0";
  $("#observationCount").textContent = Number.isFinite(observationsEmitted) ? String(observationsEmitted) : "0";
  $("#analysisLastFrame").textContent = formatTime(data.last_frame_at);
  $("#analysisState").textContent = failed
    ? (visionReasonMessages[reasonCode] || "分析失败")
    : running
      ? (isDemo ? "演示分析中" : "本机分析中")
      : "等待采集";
  $("#analysisState").dataset.state = failed ? "failed" : running ? "running" : "idle";
  $("#captureState").dataset.state = running ? "running" : failed ? "failed" : "idle";
  $("#captureStateText").textContent = running
    ? (isDemo ? "演示数据生成中" : "本地采集中")
    : failed
      ? (visionReasonMessages[reasonCode] || `后端采集失败：${reasonCode}`)
      : (isDemo ? "演示采集未启动" : "本地采集未启动");
  $("#startCaptureButton").hidden = running;
  $("#stopCaptureButton").hidden = !running;
  if (!running) {
    if (failed) {
      setPreviewState(visionReasonMessages[reasonCode] || "后端采集失败，请检查设备与依赖", "error");
      return;
    }
    if (localStream) stopLocalPreview("本地采集已停止");
    else if ($("#localPreviewPanel").dataset.state !== "error") {
      setPreviewState(isDemo ? "启动后生成结构化演示观察，不访问摄像头" : "启动后由浏览器摄像头采集，并交给本机分析", "idle");
    }
    return;
  }
  if (isDemo) setPreviewState("演示数据生成中，未访问摄像头", "demo");
  else if (localStream) setPreviewState("本地摄像头预览与本机分析运行中", "running");
  else setPreviewState("本地摄像头预览未连接", "error");
}

function renderObservation(data) {
  const available = Boolean(data.available);
  $("#recognitionStatus").textContent = available ? (data.mode === "demo" ? "演示已确认" : "已确认") : "等待确认";
  $("#recognitionStatus").dataset.state = available ? "ready" : "idle";
  if (!data.available) {
    const waitingText = data.mode === "demo" ? "演示正在等待时序确认" : "尚无稳定观察结果";
    $("#visualSummary").textContent = waitingText;
    $("#observationText").textContent = waitingText;
    renderLabelGroup("#sceneLabels", [], "等待稳定结果");
    renderLabelGroup("#objectLabels", [], "等待稳定结果");
    renderLabelGroup("#poseLabels", [], "等待稳定结果");
    renderLabelGroup("#gestureLabels", [], "等待稳定结果");
    renderLabelGroup("#facialLabels", [], "仅显示直接视觉提示");
    renderLabelGroup("#changeLabels", [], "等待下一次确认");
    $("#observationUpdated").textContent = data.mode === "demo" ? "演示正在等待时序确认" : "时序确认达到要求后显示结果";
    return;
  }
  renderLabelGroup("#sceneLabels", [data.scene_state, data.scene_label, ...(data.scene_facts || [])], "未识别场景");
  renderLabelGroup("#objectLabels", data.objects, "未识别目标");
  renderLabelGroup("#poseLabels", data.pose_labels, "未识别姿态");
  renderLabelGroup("#gestureLabels", data.gesture_labels, "未识别动作");
  renderLabelGroup("#facialLabels", data.facial_cues, "没有直接提示");
  renderLabelGroup("#changeLabels", (data.changes || []).map(formatVisualChange), "暂无新变化");
  const summary = summarizeObservation(data);
  $("#visualSummary").textContent = summary;
  const prefix = data.mode === "demo" ? "演示数据 · " : "";
  $("#observationText").textContent = prefix + summary;
  $("#observationUpdated").textContent = data.observed_at
    ? `最近确认：${formatTime(data.observed_at)}${data.scene_confidence ? ` · 置信度 ${(Number(data.scene_confidence) * 100).toFixed(0)}%` : ""}`
    : "已完成时序确认";
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
    if (error.status === 401 || error.status === 403) {
      activeSessionId = "";
      activeSessionMode = "";
      stopCapturePolling();
      stopLocalPreview("管理员会话已失效，请重新登录", "error");
      $("#captureControls").hidden = true;
      $("#sessionDetail").hidden = true;
      setHeaderStatus("访问受限", "restricted");
      showAccess("管理员会话已失效，请重新登录");
      return;
    }
    if (error.status === 404) {
      activeSessionId = "";
      stopCapturePolling();
      stopLocalPreview("会话已失效，本地预览已停止");
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

$("#demoSessionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const button = $("#startDemoButton");
  button.disabled = true;
  showError("#sessionError");
  try {
    const session = await request("/api/workbench/camera/demo/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: $("#demoScenario").value }),
    });
    renderSession(session);
  } catch (error) {
    showError("#sessionError", error.status === 409 ? "本地演示未启用或已有活动会话" : "演示会话未创建");
  } finally {
    button.disabled = false;
  }
});

$("#stopSessionButton").addEventListener("click", async () => {
  if (!activeSessionId) return;
  const button = $("#stopSessionButton");
  button.disabled = true;
  stopLocalPreview("正在结束会话...");
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
  showError("#sessionError");
  try {
    if (activeSessionMode !== "demo") await startLocalPreview();
    await request(`/api/workbench/camera/sessions/${encodeURIComponent(activeSessionId)}/capture/start`, { method: "POST" });
    if (activeSessionMode !== "demo") startFrameUpload();
    await refreshCapture();
  } catch (error) {
    const backendError = Boolean(error.status);
    if (activeSessionMode !== "demo") {
      stopLocalPreview(
        backendError ? "后端采集未启动，本地预览已关闭" : previewErrorMessage(error),
        "error",
      );
    }
    showError(
      "#sessionError",
      captureStartErrorMessage(error),
    );
  } finally {
    button.disabled = false;
  }
});

$("#stopCaptureButton").addEventListener("click", async () => {
  if (!activeSessionId) return;
  const button = $("#stopCaptureButton");
  button.disabled = true;
  stopLocalPreview("正在停止本地预览...");
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
    activeSessionMode = "";
    stopCapturePolling();
    stopLocalPreview();
    setHeaderStatus("访问受限", "restricted");
    showAccess();
  }
});

window.addEventListener("beforeunload", () => stopLocalPreview());

refreshStatus();
