import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Brain,
  Eye,
  Menu,
  MessageCircleMore,
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
    eyebrow: "Perception",
    title: "听见情绪，看见现场",
    description: "语音、视觉与文本进入同一条感知链路，在置信度边界内形成可用上下文。",
    icon: Eye,
    signal: "ASR · Vision · Emotion",
  },
  {
    eyebrow: "HeadCore",
    title: "每次回应，都经过思考",
    description: "人格、关系、世界证据与本地质量门禁共同约束回答，而不是简单转发模型输出。",
    icon: ShieldCheck,
    signal: "Persona · Evidence · Guardrail",
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

  const handlePointerMove = (event) => {
    if (reduceMotion || window.matchMedia("(pointer: coarse)").matches) return;
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

function MillionCounter({ reduceMotion }) {
  const counterRef = useRef(null);
  const [count, setCount] = useState(0);

  useEffect(() => {
    const target = counterRef.current;
    if (!target) return undefined;
    let frameId = 0;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        if (reduceMotion) {
          setCount(1_000_000);
          return;
        }
        const startedAt = performance.now();
        const duration = 1800;
        const tick = (now) => {
          const progress = Math.min((now - startedAt) / duration, 1);
          const eased = 1 - (1 - progress) ** 4;
          setCount(Math.round(eased * 1_000_000));
          if (progress < 1) frameId = window.requestAnimationFrame(tick);
        };
        frameId = window.requestAnimationFrame(tick);
      },
      { threshold: 0.45 },
    );
    observer.observe(target);
    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frameId);
    };
  }, [reduceMotion]);

  return (
    <div className="metric" ref={counterRef}>
      <span className="metric-value" aria-hidden="true">{count.toLocaleString("zh-CN")}</span>
      <span className="sr-only">一百万种角色可能</span>
      <span className="metric-label">种角色可能，从你的第一句话开始</span>
    </div>
  );
}

function App() {
  const rootRef = useRef(null);
  const menuButtonRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const reduceMotion = Boolean(useReducedMotion());
  useLandingAnimations(rootRef, reduceMotion);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === "Escape" && menuOpen) {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [menuOpen]);

  return (
    <div className="site-shell" ref={rootRef}>
      <a className="skip-link" href="#mainContent">跳到主要内容</a>

      <header className="site-header">
        <Brand />
        <nav className="desktop-navigation glass" aria-label="主导航">
          <a href="#capabilities">核心能力</a>
          <a href="#architecture">工作方式</a>
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
            <a href="#capabilities" onClick={() => setMenuOpen(false)}>核心能力</a>
            <a href="#architecture" onClick={() => setMenuOpen(false)}>工作方式</a>
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
              认知、记忆与多模态感知，在同一条链路上
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
            <span><i aria-hidden="true" /> Multimodal</span>
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
            <ol className="cognitive-path" data-scroll-reveal>
              <li><span>01</span><strong>感知输入</strong><small>文本、语音、视觉</small></li>
              <li><span>02</span><strong>上下文组织</strong><small>关系、记忆、人格</small></li>
              <li><span>03</span><strong>模型生成</strong><small>Provider 路由与容错</small></li>
              <li><span>04</span><strong>质量门禁</strong><small>评估、修复、持久化</small></li>
            </ol>
          </div>
        </section>

        <section className="closing-section section-band" aria-labelledby="closingTitle">
          <div className="section-inner closing-layout" data-scroll-reveal>
            <MillionCounter reduceMotion={reduceMotion} />
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
        <p>游客对话保留在当前浏览器；登录后可保存角色与长期记忆。</p>
        <div><a href="/auth">账户</a><a href="/credits">许可</a></div>
      </footer>
    </div>
  );
}

export default App;
