const $ = (selector) => document.querySelector(selector);
const views = [...document.querySelectorAll("#authViews [data-view]")];
const tabs = [...document.querySelectorAll('.auth-mode-tabs [role="tab"]')];
const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
const THEME_STORAGE_KEY = "hutao_auth_theme";
const REMEMBERED_EMAIL_STORAGE_KEY = "hutao_remembered_email";
const authParams = new URLSearchParams(location.search);
const isEmbedded = authParams.get("embed") === "1";
document.body.classList.toggle("auth-embedded", isEmbedded);
const requestedReturnTo = authParams.get("return_to");
function resolveSafeReturnTo(value) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "";
  try {
    const target = new URL(value, location.origin);
    if (target.origin !== location.origin) return "";
    if (!(target.pathname === "/desk" || target.pathname === "/me")) return "";
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return "";
  }
}
const safeReturnTo = resolveSafeReturnTo(requestedReturnTo);
const serviceState = {
  authenticationEnabled: null,
  registrationEnabled: false,
  passwordResetEnabled: false,
};
const modeCopy = {
  login: ["欢迎回来", "登录后继续上次的对话。"],
  register: ["创建账户", "建立独立的对话与记忆空间。"],
  verify: ["验证邮箱", "输入邮件中的完整验证码。"],
  verified: ["验证完成", "你的私人空间已经准备好了。"],
  resetRequest: ["找回密码", "我们会将重置步骤发送至你的注册邮箱。"],
  resetConfirm: ["设置新密码", "验证重置码后，所有旧登录会话都会失效。"],
};

function applyTheme(theme) {
  const nextTheme = theme === "light" ? "light" : "dark";
  const isLight = nextTheme === "light";
  const button = $("#themeToggle");
  const nextLabel = isLight ? "深色" : "浅色";
  document.body.dataset.theme = nextTheme;
  document.documentElement.style.colorScheme = nextTheme;
  button.setAttribute("aria-pressed", String(isLight));
  button.setAttribute("aria-label", "切换到" + nextLabel + "模式");
  button.title = "切换到" + nextLabel + "模式";
  $(".theme-toggle-label").textContent = nextLabel;
  const icon = $(".theme-toggle-icon");
  if (icon) icon.dataset.theme = isLight ? "light" : "dark";
  document.querySelector('meta[name="theme-color"]').setAttribute("content", isLight ? "#f5f7f6" : "#0b111c");
}

function shakeForm(form) {
  form.classList.remove("is-shaking");
  void form.offsetWidth;
  form.classList.add("is-shaking");
  form.addEventListener("animationend", () => form.classList.remove("is-shaking"), { once: true });
}

function syncPasswordConfirmation() {
  const password = $("#registerPassword");
  const confirmation = $("#registerPasswordConfirm");
  const mismatched = Boolean(confirmation.value) && confirmation.value !== password.value;
  confirmation.setCustomValidity(mismatched ? "两次输入的密码不一致。" : "");
}

function updatePasswordStrength() {
  const password = $("#registerPassword").value;
  const score = [
    password.length >= 12,
    /[a-z]/.test(password) && /[A-Z]/.test(password),
    /[0-9]/.test(password),
    [...password].some((character) => !/[A-Za-z0-9]/.test(character) && Boolean(character.trim())),
  ].filter(Boolean).length;
  const labels = ["很弱", "较弱", "一般", "良好", "很强"];
  const label = password ? labels[score] : "尚未输入";
  const meter = $("#registerPasswordStrength");
  meter.value = score;
  meter.dataset.level = String(score);
  $("#registerPasswordStrengthLabel").textContent = "密码强度：" + label;
}

const testimonialCarousel = $("[data-carousel]");
const testimonialSlides = [...document.querySelectorAll("[data-testimonial]")];
const testimonialDots = [...document.querySelectorAll("[data-testimonial-index]")];
let testimonialIndex = 0;
let testimonialTimer = 0;
let testimonialPaused = reducedMotionQuery.matches || isEmbedded;

function showTestimonial(index, announce = true) {
  testimonialIndex = (index + testimonialSlides.length) % testimonialSlides.length;
  testimonialSlides.forEach((slide, slideIndex) => {
    const active = slideIndex === testimonialIndex;
    slide.hidden = !active;
    slide.classList.toggle("is-active", active);
    slide.setAttribute("aria-hidden", String(!active));
  });
  testimonialDots.forEach((dot, dotIndex) => {
    dot.setAttribute("aria-pressed", String(dotIndex === testimonialIndex));
  });
  const position = String(testimonialIndex + 1).padStart(2, "0");
  $("#testimonialCount").textContent = position + " / " + String(testimonialSlides.length).padStart(2, "0");
  if (announce) {
    $("#testimonialStatus").textContent = "正在显示第 " + (testimonialIndex + 1) + " 条反馈，共 " + testimonialSlides.length + " 条";
  }
}

function stopTestimonialCarousel() {
  window.clearInterval(testimonialTimer);
  testimonialTimer = 0;
}

function startTestimonialCarousel() {
  stopTestimonialCarousel();
  const interactionActive = testimonialCarousel.matches(":hover")
    || testimonialCarousel.contains(document.activeElement);
  if (testimonialPaused || document.hidden || interactionActive || testimonialSlides.length < 2) return;
  testimonialTimer = window.setInterval(() => showTestimonial(testimonialIndex + 1), 4000);
}

function setTestimonialPaused(paused) {
  testimonialPaused = paused;
  const toggle = $("#testimonialToggle");
  const label = paused ? "继续自动轮播" : "暂停自动轮播";
  toggle.setAttribute("aria-pressed", String(paused));
  toggle.setAttribute("aria-label", label);
  toggle.title = label;
  toggle.querySelector("span").textContent = paused ? "▶" : "Ⅱ";
  startTestimonialCarousel();
}
function setFormsAvailability() {
  const states = [
    [$("#loginForm"), serviceState.authenticationEnabled === true],
    [$("#registerForm"), serviceState.registrationEnabled],
    [$("#verifyForm"), serviceState.registrationEnabled],
    [$("#resetRequestForm"), serviceState.passwordResetEnabled],
    [$("#resetConfirmForm"), serviceState.passwordResetEnabled],
  ];
  for (const [form, enabled] of states) {
    const submit = form.querySelector('[type="submit"]');
    if (submit) submit.disabled = !enabled;
    form.dataset.submission = enabled ? "enabled" : "unavailable";
  }
}

function csrfToken() {
  const stored = sessionStorage.getItem("hutao_csrf_token");
  if (stored) return stored;
  const match = document.cookie.match(/(?:^|; )hutao_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function notice(message, error = false) {
  const node = $("#notice");
  node.textContent = message;
  node.hidden = false;
  node.setAttribute("role", error ? "alert" : "status");
  node.setAttribute("aria-live", error ? "assertive" : "polite");
  node.className = `notice${error ? " error" : ""}`;
}

function clearErrors(form) {
  form.querySelectorAll(".field-error").forEach((node) => { node.textContent = ""; });
  form.querySelectorAll("[aria-invalid]").forEach((node) => node.removeAttribute("aria-invalid"));
}

function validate(form) {
  clearErrors(form);
  if (form === $("#registerForm")) syncPasswordConfirmation();
  let firstInvalid = null;
  for (const input of form.querySelectorAll("input")) {
    if (input.checkValidity()) continue;
    input.setAttribute("aria-invalid", "true");
    const error = form.querySelector(`[data-error-for="${input.id}"]`);
    if (error) {
      error.textContent = input.validity.customError ? input.validationMessage : input.validity.valueMissing
        ? "请填写这一项。"
        : input.validity.typeMismatch
          ? "请输入有效的邮箱地址。"
          : input.validity.tooShort
            ? `至少需要 ${input.minLength} 个字符。`
            : input.validity.patternMismatch
              ? "密码需要包含大小写字母、数字和符号。"
              : "请检查输入内容。";
    }
    firstInvalid ||= input;
  }
  if (firstInvalid) shakeForm(form);
  firstInvalid?.focus();
  return !firstInvalid;
}

function setBusy(form, busy, label) {
  for (const control of form.elements) control.disabled = busy;
  const submit = form.querySelector('[type="submit"]');
  if (!submit) return;
  if (busy) {
    submit.dataset.label = submit.textContent;
    submit.textContent = label;
  } else if (submit.dataset.label) {
    for (const control of form.elements) control.disabled = false;
    submit.textContent = submit.dataset.label;
    setFormsAvailability();
  }
}

function showMode(next, message = "", focusInput = false) {
  let mode = modeCopy[next] ? next : "login";
  if (["verify", "verified"].includes(mode) && !serviceState.registrationEnabled) {
    mode = "login";
    message = "邮箱验证服务尚未启用。";
  } else if (["resetRequest", "resetConfirm"].includes(mode) && !serviceState.passwordResetEnabled) {
    mode = "login";
    message = "找回密码服务尚未启用。";
  } else if (mode === "register" && !serviceState.registrationEnabled) {
    message ||= "新账户注册尚未启用，当前表单仅供预览。";
  }
  views.forEach((view) => { view.hidden = view.dataset.view !== mode; });
  const activeTabMode = ["register", "verify", "verified"].includes(mode) ? "register" : "login";
  const activeView = document.querySelector('[data-view="' + mode + '"]');
  tabs.forEach((tab) => {
    const selected = tab.dataset.mode === activeTabMode;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    const defaultPanel = tab.dataset.mode === "register" ? "registerForm" : "loginForm";
    tab.setAttribute("aria-controls", selected && activeView ? activeView.id : defaultPanel);
  });
  const showNotice = Boolean(message) && $("#localMode").hidden;
  $("#notice").hidden = !showNotice;
  if (showNotice) notice(message);
  $("#formTitle").textContent = modeCopy[mode][0];
  $("#formLead").textContent = modeCopy[mode][1];
  const params = new URLSearchParams();
  if (mode !== "login") params.set("mode", mode);
  if (isEmbedded) params.set("embed", "1");
  if (safeReturnTo) params.set("return_to", safeReturnTo);
  history.replaceState({}, "", `/auth${params.size ? `?${params}` : ""}`);
  if (focusInput) document.querySelector(`[data-view="${mode}"] input`)?.focus();
}

async function post(path, payload) {
  const headers = { "Content-Type": "application/json" };
  const token = csrfToken();
  if (token) headers["X-CSRF-Token"] = token;
  const response = await fetch(`/api/v1/auth/${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    credentials: "same-origin",
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "";
    const message = response.status === 404
      ? "账户服务暂未开启。"
      : response.status === 429
        ? "操作过于频繁，请稍后再试。"
        : detail || "请求没有完成，请稍后重试。";
    throw new Error(message);
  }
  return body;
}

async function loadAuthStatus() {
  document.body.dataset.authState = "checking";
  $("#authLoading").hidden = false;
  $("#statusError").hidden = true;
  $("#localMode").hidden = true;
  $("#authViews").hidden = true;
  try {
    const response = await fetch("/api/v1/auth/status", { credentials: "same-origin" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const status = await response.json();
    serviceState.authenticationEnabled = Boolean(status.authentication_enabled);
    serviceState.registrationEnabled = Boolean(status.registration_enabled);
    serviceState.passwordResetEnabled = Boolean(status.password_reset_enabled);
    $("#authLoading").hidden = true;
    $("#authViews").hidden = false;
    setFormsAvailability();
    const initialMode = new URLSearchParams(location.search).get("mode") || "login";
    if (!serviceState.authenticationEnabled) {
      document.body.dataset.authState = "local";
      $("#localMode").hidden = false;
      showMode(initialMode, "账户服务尚未启用，当前表单仅供填写检查。");
      return;
    }
    document.body.dataset.authState = "enabled";
    $("#localMode").hidden = true;
    showMode(initialMode);
  } catch {
    serviceState.authenticationEnabled = null;
    document.body.dataset.authState = "error";
    $("#authLoading").hidden = true;
    $("#statusError").hidden = false;
  }
}

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!validate(form)) return;
  const payload = {
    email: $("#loginEmail").value.trim(),
    password: $("#loginPassword").value,
  };
  if ($("#rememberEmail").checked) {
    sessionStorage.setItem(REMEMBERED_EMAIL_STORAGE_KEY, payload.email);
  } else {
    sessionStorage.removeItem(REMEMBERED_EMAIL_STORAGE_KEY);
  }
  setBusy(form, true, "正在登录");
  try {
    const data = await post("login", payload);
    sessionStorage.setItem("hutao_csrf_token", data.csrf_token);
    if (isEmbedded && window.parent !== window) {
      window.parent.postMessage({ type: "personacore-auth-complete" }, location.origin);
      window.parent.location.assign(safeReturnTo || "/desk");
    } else {
      location.assign(safeReturnTo || "/desk");
    }
  } catch (error) {
    notice(error.message, true);
  } finally {
    setBusy(form, false);
  }
});

$("#resetRequestForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!serviceState.passwordResetEnabled || !validate(form)) return;
  const payload = Object.fromEntries(new FormData(form));
  setBusy(form, true, "正在发送");
  try {
    await post("password-reset/request", payload);
    form.reset();
    showMode("resetConfirm", "如果该邮箱可以重置，重置码已发送。请检查收件箱和垃圾邮件。", true);
  } catch (error) {
    notice(error.message, true);
  } finally {
    setBusy(form, false);
  }
});

$("#resetConfirmForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!serviceState.passwordResetEnabled || !validate(form)) return;
  const payload = Object.fromEntries(new FormData(form));
  setBusy(form, true, "正在更新");
  try {
    await post("password-reset/confirm", payload);
    form.reset();
    showMode("login", "密码已更新，请使用新密码登录。旧设备已退出登录。", true);
  } catch (error) {
    notice(error.message, true);
  } finally {
    setBusy(form, false);
  }
});

$("#registerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!serviceState.registrationEnabled || !validate(form)) return;
  setBusy(form, true, "正在创建");
  try {
    const payload = {
      display_name: $("#displayName").value.trim(),
      email: $("#registerEmail").value.trim(),
      password: $("#registerPassword").value,
    };
    await post("register", payload);
    sessionStorage.setItem("hutao_pending_email", payload.email);
    $("#verificationEmail").textContent = payload.email;
    showMode("verify", "", true);
  } catch (error) {
    notice(error.message, true);
  } finally {
    setBusy(form, false);
  }
});

$("#verifyForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!serviceState.registrationEnabled || !validate(form)) return;
  const payload = Object.fromEntries(new FormData(form));
  setBusy(form, true, "正在验证");
  try {
    await post("verify-email", payload);
    sessionStorage.removeItem("hutao_pending_email");
    showMode("verified");
  } catch (error) {
    notice(error.message, true);
  } finally {
    setBusy(form, false);
  }
});

document.addEventListener("click", (event) => {
  const modeButton = event.target.closest("[data-mode]");
  if (modeButton && serviceState.authenticationEnabled !== null) showMode(modeButton.dataset.mode, "", true);

  const reveal = event.target.closest("[data-reveal]");
  if (!reveal) return;
  const input = reveal.previousElementSibling;
  const hidden = input.type === "password";
  input.type = hidden ? "text" : "password";
  reveal.textContent = hidden ? "隐藏" : "显示";
  reveal.setAttribute("aria-label", hidden ? "隐藏密码" : "显示密码");
});

$("#themeToggle").addEventListener("click", () => {
  const nextTheme = document.body.dataset.theme === "light" ? "dark" : "light";
  sessionStorage.setItem(THEME_STORAGE_KEY, nextTheme);
  applyTheme(nextTheme);
});

tabs.forEach((tab, index) => {
  tab.addEventListener("keydown", (event) => {
    let targetIndex = null;
    if (event.key === "ArrowRight") targetIndex = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") targetIndex = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") targetIndex = 0;
    if (event.key === "End") targetIndex = tabs.length - 1;
    if (targetIndex === null) return;
    event.preventDefault();
    tabs[targetIndex].focus();
    showMode(tabs[targetIndex].dataset.mode);
  });
});

$("#registerPassword").addEventListener("input", () => {
  updatePasswordStrength();
  syncPasswordConfirmation();
});
$("#registerPasswordConfirm").addEventListener("input", syncPasswordConfirmation);

const rememberedEmail = sessionStorage.getItem(REMEMBERED_EMAIL_STORAGE_KEY);
if (rememberedEmail) {
  $("#loginEmail").value = rememberedEmail;
  $("#rememberEmail").checked = true;
}
$("#rememberEmail").addEventListener("change", () => {
  if (!$("#rememberEmail").checked) {
    sessionStorage.removeItem(REMEMBERED_EMAIL_STORAGE_KEY);
  } else if ($("#loginEmail").value.trim()) {
    sessionStorage.setItem(REMEMBERED_EMAIL_STORAGE_KEY, $("#loginEmail").value.trim());
  }
});
$("#loginEmail").addEventListener("input", () => {
  if ($("#rememberEmail").checked) {
    sessionStorage.setItem(REMEMBERED_EMAIL_STORAGE_KEY, $("#loginEmail").value.trim());
  }
});

testimonialDots.forEach((dot) => {
  dot.addEventListener("click", () => {
    showTestimonial(Number(dot.dataset.testimonialIndex));
    startTestimonialCarousel();
  });
});
$("#testimonialToggle").addEventListener("click", () => setTestimonialPaused(!testimonialPaused));
testimonialCarousel.addEventListener("mouseenter", stopTestimonialCarousel);
testimonialCarousel.addEventListener("mouseleave", startTestimonialCarousel);
testimonialCarousel.addEventListener("focusin", stopTestimonialCarousel);
testimonialCarousel.addEventListener("focusout", (event) => {
  if (!testimonialCarousel.contains(event.relatedTarget)) startTestimonialCarousel();
});
document.addEventListener("visibilitychange", startTestimonialCarousel);
if (typeof reducedMotionQuery.addEventListener === "function") {
  reducedMotionQuery.addEventListener("change", (event) => {
    if (event.matches) setTestimonialPaused(true);
  });
}

applyTheme(sessionStorage.getItem(THEME_STORAGE_KEY) || "dark");
updatePasswordStrength();
showTestimonial(0, false);
setTestimonialPaused(testimonialPaused);
$("#retryStatus").addEventListener("click", loadAuthStatus);
const pendingEmail = sessionStorage.getItem("hutao_pending_email");
if (pendingEmail) $("#verificationEmail").textContent = pendingEmail;
loadAuthStatus();
