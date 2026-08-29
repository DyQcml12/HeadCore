import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUp,
  Brain,
  Check,
  ChevronRight,
  Menu,
  MessageCircleMore,
  Pause,
  Play,
  Radio,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  AnimatePresence,
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "motion/react";
import ParticleField from "./components/ParticleField";
import { useLandingAnimations } from "./hooks/useLandingAnimations";

const HERO_LINES = ["HutaoChatCore", "让角色记得你，也理解此刻。"];
const FEATURES = [
  {
    eyebrow: "Memory",
    title: "记忆，不止于上一句话",
    description: "从短期会话到可审核的长期记忆，让关系上下文在一次次对话里延续。",
    icon: Brain,
    signal: "关系 · 会话 · 长期记忆",
  },
  {
    eyebrow: "Conversation",
    title: "文字与语音，都留在对话里",
    description: "文字与语音输入进入同一条对话链路，在本地沙盒里验证上下文和表达方式。",
    icon: MessageCircleMore,
    signal: "Text · Voice · Session",
  },
  {
    eyebrow: "HeadCore",
    title: "每次回应，都经过思考",
    description: "人格、关系、世界证据与本地质量门禁共同约束回答，而不是简单转发模型输出。",
    icon: ShieldCheck,
    signal: "Persona · Evidence · Guardrail",
  },
];

const COGNITIVE_STEPS = [
  {
    label: "感知输入",
    meta: "文本、语音",
    detail: "先确认输入通道和会话边界，再进入同一条可追踪的处理链路。",
    signal: "INPUT",
  },
  {
    label: "上下文组织",
    meta: "关系、记忆、人格",
    detail: "把当前会话、已确认记忆和人格约束分层组合，避免把所有内容混成提示词。",
    signal: "CONTEXT",
  },
  {
    label: "模型生成",
    meta: "Provider 路由与容错",
    detail: "按配置选择模型提供方，流式输出优先返回可用内容，同时保留失败原因。",
    signal: "GENERATE",
  },
  {
    label: "质量门禁",
    meta: "评估、修复、持久化",
    detail: "输出先经过质量检查，再决定是否保存为会话内容或长期记忆。",
    signal: "GUARDRAIL",
  },
];

function SplitLine({ children }) {
  return (
    <span className="hero-title-line" aria-hidden="true">
      {Array.from(children).map((character, index) => (
        <span className="hero-word" key={`${character}-${index}`}>
          {character === " " ? "\u00A0" : character}
        </span>
      ))}
    </span>
  );
}

function Brand() {
  return (
    <a className="brand" href="/" aria-label="HutaoChatCore 首页">
      <span className="brand-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="brand-copy">
        <strong>HutaoChatCore</strong>
        <small>认知角色引擎</small>
      </span>
    </a>
  );
}

function FeatureCard({ feature, index, reduceMotion }) {
  const rotateXRaw = useMotionValue(0);
  const rotateYRaw = useMotionValue(0);
  const rotateX = useSpring(rotateXRaw, { stiffness: 220, damping: 24 });
  const rotateY = useSpring(rotateYRaw, { stiffness: 220, damping: 24 });
  const glowX = useMotionValue(50);
  const glowY = useMotionValue(50);
  const glow = useTransform(
    [glowX, glowY],
    ([x, y]) => `radial-gradient(circle at ${x}% ${y}%, oklch(78% 0.2 145 / 0.22), transparent 38%)`,
  );
  const [coarsePointer] = useState(() => window.matchMedia("(pointer: coarse)").matches);

  const handlePointerMove = (event) => {
    if (reduceMotion || coarsePointer) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width;
    const y = (event.clientY - bounds.top) / bounds.height;
    rotateXRaw.set((0.5 - y) * 7);
    rotateYRaw.set((x - 0.5) * 7);
    glowX.set(x * 100);
    glowY.set(y * 100);
  };

  const resetTilt = () => {
    rotateXRaw.set(0);
    rotateYRaw.set(0);
    glowX.set(50);
    glowY.set(50);
  };

  const Icon = feature.icon;
  return (
    <div className="feature-card-shell" data-scroll-reveal>
      <motion.article
        className="feature-card glass neon-border"
        style={reduceMotion ? undefined : { rotateX, rotateY, backgroundImage: glow }}
        onPointerMove={handlePointerMove}
        onPointerLeave={resetTilt}
        whileHover={reduceMotion ? undefined : { y: -6, scale: 1.02 }}
        whileTap={reduceMotion ? undefined : { scale: 0.98 }}
        transition={{ type: "spring", stiffness: 400, damping: 17 }}
      >
        <div className="feature-card-topline">
          <span className="feature-index">0{index + 1}</span>
        </div>
        <div className="feature-icon-halo" aria-hidden="true">
          <Icon size={38} strokeWidth={1.45} />
        </div>
        <h3>{feature.eyebrow}</h3>
        <p className="feature-title">{feature.title}</p>
        <p className="feature-description">{feature.description}</p>
        <p className="feature-signal">{feature.signal}</p>
      </motion.article>
    </div>
  );
}

function CognitivePath({ reduceMotion }) {
  const [activeStep, setActiveStep] = useState(0);
  const [autoPlay, setAutoPlay] = useState(!reduceMotion);

  useEffect(() => {
    if (reduceMotion || !autoPlay) return undefined;
    const timer = window.setTimeout(() => {
      setActiveStep((step) => (step + 1) % COGNITIVE_STEPS.length);
    }, 4200);
    return () => window.clearTimeout(timer);
  }, [activeStep, autoPlay, reduceMotion]);

  const activateStep = (index) => {
    setActiveStep(index);
    setAutoPlay(false);
  };

  return (
    <div className="cognitive-path-shell" data-scroll-reveal>
      <button
        className="path-motion-toggle glass"
        type="button"
        title={autoPlay ? "暂停步骤演示" : "播放步骤演示"}
        aria-label={autoPlay ? "暂停步骤演示" : "播放步骤演示"}
        aria-pressed={!autoPlay}
        onClick={() => setAutoPlay((playing) => !playing)}
      >
        {autoPlay ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}
      </button>
      <ol className="cognitive-path">
        {COGNITIVE_STEPS.map((step, index) => {
          const isActive = activeStep === index;
          const buttonId = `cognitive-step-${index}`;
          const detailId = `cognitive-detail-${index}`;
          return (
            <li className={isActive ? "is-active" : ""} key={step.signal}>
              <button
                id={buttonId}
                className="cognitive-step"
                type="button"
                aria-expanded={isActive}
                aria-controls={detailId}
                onClick={() => activateStep(index)}
                onMouseEnter={() => activateStep(index)}
                onFocus={() => activateStep(index)}
              >
                <span className="cognitive-step-index">0{index + 1}</span>
                <span className="cognitive-step-copy">
                  <strong>{step.label}</strong>
                  <small>{step.meta}</small>
                </span>
                <ChevronRight className="cognitive-step-arrow" size={17} aria-hidden="true" />
              </button>
              <AnimatePresence initial={false}>
                {isActive ? (
                  <motion.div
                    id={detailId}
                    className="cognitive-step-detail"
                    role="region"
                    aria-labelledby={buttonId}
                    initial={reduceMotion ? false : { opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={reduceMotion ? undefined : { opacity: 0, height: 0 }}
                    transition={{ duration: reduceMotion ? 0 : 0.28, ease: "easeOut" }}
                  >
                    <p>{step.detail}</p>
                    <div className="cognitive-step-signal">
                      <span><Radio size={12} aria-hidden="true" /> {step.signal}</span>
                      <span className="cognitive-step-meter" aria-hidden="true"><i /></span>
                      <Check size={14} aria-hidden="true" />
                      <span className="sr-only">已纳入处理链路</span>
                    </div>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function App() {
  const rootRef = useRef(null);
  const menuButtonRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeSection, setActiveSection] = useState("");
  const [headerCompact, setHeaderCompact] = useState(false);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [showBackToTop, setShowBackToTop] = useState(false);
  const reduceMotion = Boolean(useReducedMotion());
  useLandingAnimations(rootRef, reduceMotion);

  useEffect(() => {
    const updateScrollState = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      const progress = scrollable > 0 ? Math.min(window.scrollY / scrollable, 1) : 0;
      const remaining = document.documentElement.scrollHeight - (window.scrollY + window.innerHeight);
      setScrollProgress(progress);
      setHeaderCompact(window.scrollY > 24);
      setShowBackToTop(window.scrollY > 520 && remaining > 120);
    };
    let frameId = 0;
    const scheduleScrollUpdate = () => {
      if (frameId) return;
      frameId = window.requestAnimationFrame(() => {
        frameId = 0;
        updateScrollState();
      });
    };
    updateScrollState();
    window.addEventListener("scroll", scheduleScrollUpdate, { passive: true });
    window.addEventListener("resize", scheduleScrollUpdate, { passive: true });
    window.addEventListener("orientationchange", scheduleScrollUpdate, { passive: true });

    const sections = ["capabilities", "architecture"]
      .map((id) => document.getElementById(id))
      .filter(Boolean);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        setActiveSection(visible?.target.id || "");
      },
      { rootMargin: "-36% 0px -54%", threshold: [0, 0.35, 0.7] },
    );
    sections.forEach((section) => observer.observe(section));

    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("scroll", scheduleScrollUpdate);
      window.removeEventListener("resize", scheduleScrollUpdate);
      window.removeEventListener("orientationchange", scheduleScrollUpdate);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const menu = document.querySelector("#mobileNavigation");
    const focusable = Array.from(menu?.querySelectorAll("a[href], button:not([disabled])") || []);
    document.body.style.overflow = "hidden";
    focusable[0]?.focus();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
        return;
      }
      if (event.key !== "Tab" || !focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  return (
    <div className={`site-shell${headerCompact ? " header-compact" : ""}`} ref={rootRef}>
      <a className="skip-link" href="#mainContent">跳到主要内容</a>

      <div className="page-progress" style={{ transform: `scaleX(${scrollProgress})` }} aria-hidden="true" />

      <header className={`site-header${headerCompact ? " is-scrolled" : ""}`}>
        <Brand />
        <nav className="desktop-navigation glass" aria-label="主导航">
          <a className={activeSection === "capabilities" ? "is-active" : ""} href="#capabilities" aria-current={activeSection === "capabilities" ? "location" : undefined}>核心能力</a>
          <a className={activeSection === "architecture" ? "is-active" : ""} href="#architecture" aria-current={activeSection === "architecture" ? "location" : undefined}>工作方式</a>
          <a href="/credits">来源与许可</a>
          <motion.a
            className="navigation-cta"
            href="/desk"
            whileHover={reduceMotion ? undefined : { y: -2 }}
            whileTap={reduceMotion ? undefined : { scale: 0.97 }}
          >
            进入对话 <ArrowRight size={15} aria-hidden="true" />
          </motion.a>
        </nav>
        <button
          ref={menuButtonRef}
          className="menu-button glass"
          type="button"
          aria-label={menuOpen ? "关闭导航" : "打开导航"}
          aria-expanded={menuOpen}
          aria-controls="mobileNavigation"
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </button>
      </header>

      <AnimatePresence>
        {menuOpen ? (
          <motion.nav
            id="mobileNavigation"
            className="mobile-navigation glass"
            aria-label="移动端主导航"
            initial={reduceMotion ? false : { opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, y: -12 }}
          >
            <a className={activeSection === "capabilities" ? "is-active" : ""} href="#capabilities" onClick={() => setMenuOpen(false)}>核心能力</a>
            <a className={activeSection === "architecture" ? "is-active" : ""} href="#architecture" onClick={() => setMenuOpen(false)}>工作方式</a>
            <a href="/credits">来源与许可</a>
            <a className="mobile-navigation-cta" href="/desk">进入对话</a>
          </motion.nav>
        ) : null}
      </AnimatePresence>

      <main id="mainContent">
        <section className="hero-pin" aria-labelledby="heroTitle">
          <ParticleField reduceMotion={reduceMotion} />
          <div className="hero-atmosphere" aria-hidden="true" />
          <div className="noise-overlay" aria-hidden="true" />
          <div className="hero-grid" aria-hidden="true" />

          <div className="hero-content">
            <p className="hero-kicker" data-hero-reveal>
              <span className="status-dot" aria-hidden="true" />
              认知、记忆与连续对话，在同一条链路上
            </p>
            <h1 id="heroTitle" aria-label="HutaoChatCore，让角色记得你，也理解此刻。">
              {HERO_LINES.map((line) => <SplitLine key={line}>{line}</SplitLine>)}
            </h1>
            <p className="hero-description" data-hero-reveal>
              不只生成一句回答。它把人格、关系、记忆与现实证据组织成连续的角色体验。
            </p>
            <div className="hero-actions" data-hero-reveal>
              <motion.a
                className="button button-primary"
                href="/desk"
                whileHover={reduceMotion ? undefined : { y: -3, scale: 1.015 }}
                whileTap={reduceMotion ? undefined : { scale: 0.98 }}
              >
                开始对话 <ArrowRight size={18} aria-hidden="true" />
              </motion.a>
              <motion.a
                className="button button-secondary glass"
                href="/auth"
                whileHover={reduceMotion ? undefined : { y: -3 }}
                whileTap={reduceMotion ? undefined : { scale: 0.98 }}
              >
                登录并保存角色
              </motion.a>
            </div>
          </div>

          <div className="hero-status" data-hero-reveal aria-label="核心系统状态">
            <span><i aria-hidden="true" /> HeadCore</span>
            <span><i aria-hidden="true" /> Memory</span>
            <span><i aria-hidden="true" /> Text + Voice</span>
          </div>
          <a className="scroll-cue" href="#capabilities" aria-label="查看核心能力">
            <span>向下</span><i aria-hidden="true" />
          </a>
        </section>

        <section className="capabilities section-band" id="capabilities" aria-labelledby="capabilitiesTitle">
          <div className="section-inner">
            <div className="capabilities-preview" aria-hidden="true">
              <span>Core capabilities</span>
            </div>
            <header className="section-heading" data-scroll-reveal>
              <h2 id="capabilitiesTitle">不是更多功能。<br />是更完整的理解。</h2>
              <p>每一层都服务于同一件事：让回应有上下文、有边界，也有连续性。</p>
            </header>
            <div className="feature-grid">
              {FEATURES.map((feature, index) => (
                <FeatureCard
                  key={feature.title}
                  feature={feature}
                  index={index}
                  reduceMotion={reduceMotion}
                />
              ))}
            </div>
          </div>
        </section>

        <section className="architecture section-band" id="architecture" aria-labelledby="architectureTitle">
          <div className="section-inner architecture-layout">
            <div className="architecture-copy" data-scroll-reveal>
              <p className="eyebrow">One cognitive path</p>
              <h2 id="architectureTitle">从感知，到真正有分寸的回应。</h2>
              <p>输入不会直接抵达模型。HeadCore 先组织关系、人格与证据，再由质量门禁校验输出。</p>
              <a className="text-link" href="/credits">查看来源与许可 <ArrowRight size={16} aria-hidden="true" /></a>
            </div>
            <CognitivePath reduceMotion={reduceMotion} />
          </div>
        </section>

        <section className="closing-section section-band" aria-labelledby="closingTitle">
          <div className="section-inner closing-layout" data-scroll-reveal>
            <div className="closing-scope" aria-label="本机演示范围">
              <span className="closing-scope-label">当前验证范围</span>
              <strong>文字 · 语音 · 连续会话</strong>
              <small>只在本机服务中运行，不代表公网可用。</small>
            </div>
            <div className="closing-copy">
              <MessageCircleMore size={28} strokeWidth={1.5} aria-hidden="true" />
              <h2 id="closingTitle">先说第一句话。<br />其余的，让关系慢慢发生。</h2>
              <a className="button button-primary" href="/desk">进入角色空间 <ArrowRight size={18} aria-hidden="true" /></a>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <Brand />
        <p>游客对话保留在本机服务；登录后可管理账户记忆。</p>
        <div><a href="/auth">账户</a><a href="/credits">许可</a></div>
      </footer>

      <AnimatePresence>
        {showBackToTop ? (
          <motion.button
            className="back-to-top glass"
            type="button"
            aria-label="返回顶部"
            initial={reduceMotion ? false : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, y: 16 }}
            whileHover={reduceMotion ? undefined : { y: -3 }}
            whileTap={reduceMotion ? undefined : { scale: 0.92 }}
            onClick={() => window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" })}
          >
            <ArrowUp size={18} aria-hidden="true" />
          </motion.button>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

export default App;
