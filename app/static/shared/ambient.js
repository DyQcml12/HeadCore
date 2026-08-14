(() => {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const canvas = document.querySelector("#ambientCanvas");
  let frame = 0;
  let particles = [];

  function setupCanvas() {
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = window.innerWidth;
    const height = window.innerHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const count = reducedMotion.matches ? 10 : Math.min(48, Math.max(18, Math.round(width * height / 34000)));
    particles = Array.from({ length: count }, (_, index) => ({
      x: Math.random() * width,
      y: Math.random() * height,
      size: 1.2 + Math.random() * 2.5,
      speed: .12 + Math.random() * .3,
      drift: (Math.random() - .5) * .18,
      phase: Math.random() * Math.PI * 2,
      petal: index % 4 === 0,
    }));
    drawFrame(context, width, height, 0);
  }

  function drawFrame(context, width, height, now) {
    context.clearRect(0, 0, width, height);
    for (const particle of particles) {
      if (!reducedMotion.matches) {
        particle.y += particle.speed;
        particle.x += particle.drift + Math.sin(now / 2200 + particle.phase) * .08;
        if (particle.y > height + 8) particle.y = -8;
        if (particle.x > width + 8) particle.x = -8;
        if (particle.x < -8) particle.x = width + 8;
      }
      context.save();
      context.translate(particle.x, particle.y);
      context.rotate(particle.phase + now / 6000);
      context.fillStyle = particle.petal ? "rgba(196, 73, 68, .34)" : "rgba(224, 188, 113, .28)";
      context.beginPath();
      if (particle.petal) {
        context.ellipse(0, 0, particle.size * 1.45, particle.size * .65, 0, 0, Math.PI * 2);
      } else {
        context.arc(0, 0, particle.size * .55, 0, Math.PI * 2);
      }
      context.fill();
      context.restore();
    }
  }

  function animate(now) {
    if (!canvas || reducedMotion.matches || document.hidden) return;
    const context = canvas.getContext("2d");
    if (context) drawFrame(context, window.innerWidth, window.innerHeight, now);
    frame = window.requestAnimationFrame(animate);
  }

  function restartAnimation() {
    window.cancelAnimationFrame(frame);
    setupCanvas();
    if (!reducedMotion.matches && !document.hidden) frame = window.requestAnimationFrame(animate);
  }

  if (canvas) {
    restartAnimation();
    window.addEventListener("resize", restartAnimation, { passive: true });
    reducedMotion.addEventListener?.("change", restartAnimation);
    document.addEventListener("visibilitychange", restartAnimation);
  }

  const PRESET_TRACK = Object.freeze({
    id: "1492276411",
    title: "环境纯音乐",
    artist: "网易云音乐",
  });
  const music = { drawer: null, loaded: false };

  function playerUrl() {
    return `https://music.163.com/outchain/player?type=2&id=${PRESET_TRACK.id}&auto=1&height=66`;
  }

  function updateMusicButtons() {
    const open = Boolean(music.drawer?.open);
    document.querySelectorAll("[data-music-toggle]").forEach((button) => {
      button.classList.add("has-track");
      button.classList.toggle("is-playing", music.loaded);
      button.setAttribute("aria-expanded", String(open));
      button.setAttribute("aria-controls", "musicDrawer");
      button.setAttribute("aria-label", open ? "关闭环境音乐" : "打开环境音乐");
      button.dataset.tooltip = open ? "关闭环境音乐" : "打开环境音乐";
    });
  }

  function loadPresetTrack() {
    const frameNode = music.drawer.querySelector("[data-music-frame]");
    if (music.loaded) return;
    frameNode.src = playerUrl();
    music.loaded = true;
  }

  function createMusicDrawer() {
    const drawer = document.createElement("dialog");
    drawer.id = "musicDrawer";
    drawer.className = "music-drawer";
    drawer.setAttribute("aria-labelledby", "musicDrawerTitle");
    drawer.innerHTML = `
      <header class="music-drawer-header">
        <div><p class="eyebrow">环境音乐</p><h2 id="musicDrawerTitle">纯音乐播放器</h2></div>
        <button class="music-close" type="button" data-music-close aria-label="关闭播放器">×</button>
      </header>
      <div class="music-drawer-body">
        <section class="music-player">
          <div class="music-track-copy">
            <span>正在播放</span>
            <h3>${PRESET_TRACK.title}</h3>
            <p>${PRESET_TRACK.artist}</p>
          </div>
          <iframe class="music-frame" data-music-frame title="网易云音乐纯音乐播放器" referrerpolicy="strict-origin-when-cross-origin" allow="autoplay; encrypted-media"></iframe>
          <div class="music-player-actions">
            <span>网站会自动尝试播放</span>
            <a class="music-external" href="https://music.163.com/#/song?id=${PRESET_TRACK.id}" target="_blank" rel="noopener noreferrer">网易云音乐</a>
          </div>
          <p class="music-provider-note">播放由网易云音乐提供；浏览器可能要求你在播放器内确认一次。</p>
        </section>
      </div>`;
    document.body.append(drawer);
    drawer.querySelector("[data-music-close]").addEventListener("click", () => drawer.close());
    drawer.addEventListener("click", (event) => {
      if (event.target === drawer) drawer.close();
    });
    drawer.addEventListener("close", updateMusicButtons);
    music.drawer = drawer;
    return drawer;
  }

  function openMusicDrawer() {
    const drawer = music.drawer || createMusicDrawer();
    if (!drawer.open) drawer.showModal();
    loadPresetTrack();
    updateMusicButtons();
  }

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-music-toggle]")) return;
    if (music.drawer?.open) {
      music.drawer.close();
      return;
    }
    openMusicDrawer();
  });
  createMusicDrawer();
  updateMusicButtons();
})();
