import { useEffect, useRef } from "react";

const PARTICLE_COUNT = 500;
const POINTER_PARALLAX = 0.02;

export default function ParticleField({ reduceMotion = false }) {
  const hostRef = useRef(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    let disposed = false;
    let teardownScene = () => {};

    import("three").then((THREE) => {
      if (disposed) return;

      let renderer;
      try {
        renderer = new THREE.WebGLRenderer({
          alpha: true,
          antialias: false,
          powerPreference: "high-performance",
        });
      } catch {
        host.dataset.webgl = "unavailable";
        return;
      }

      host.dataset.webgl = "ready";
      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.domElement.setAttribute("role", "presentation");
      host.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 80);
      camera.position.z = 14;

      const geometry = new THREE.BufferGeometry();
      const positions = new Float32Array(PARTICLE_COUNT * 3);
      const colors = new Float32Array(PARTICLE_COUNT * 3);

      for (let index = 0; index < PARTICLE_COUNT; index += 1) {
        const stride = index * 3;
        const radius = 4 + Math.random() * 10;
        const angle = Math.random() * Math.PI * 2;
        const vertical = (Math.random() - 0.5) * 10;
        positions[stride] = Math.cos(angle) * radius + (Math.random() - 0.5) * 2;
        positions[stride + 1] = vertical;
        positions[stride + 2] = Math.sin(angle) * radius - Math.random() * 8;

        const accent = Math.random() > 0.72;
        colors[stride] = accent ? 0.34 : 0.45;
        colors[stride + 1] = accent ? 1 : 0.42;
        colors[stride + 2] = accent ? 0.58 : 1;
      }

      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));

      const material = new THREE.PointsMaterial({
        size: 0.055,
        sizeAttenuation: true,
        transparent: true,
        opacity: 0.82,
        vertexColors: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const particles = new THREE.Points(geometry, material);
      scene.add(particles);

      const pointer = { x: 0, y: 0 };
      const target = { x: 0, y: 0 };
      let frameId = 0;
      let pageVisible = document.visibilityState === "visible";

      const resize = () => {
        const width = Math.max(host.clientWidth, 1);
        const height = Math.max(host.clientHeight, 1);
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.render(scene, camera);
      };

      const handlePointer = (event) => {
        target.x = (event.clientX / window.innerWidth - 0.5) * 2;
        target.y = (event.clientY / window.innerHeight - 0.5) * 2;
      };

      const renderFrame = () => {
        if (!pageVisible) return;
        pointer.x += (target.x - pointer.x) * 0.045;
        pointer.y += (target.y - pointer.y) * 0.045;
        particles.rotation.y += 0.00035;
        particles.rotation.x = pointer.y * POINTER_PARALLAX;
        particles.position.x = pointer.x * POINTER_PARALLAX * 12;
        particles.position.y = -pointer.y * POINTER_PARALLAX * 8;
        renderer.render(scene, camera);
        frameId = window.requestAnimationFrame(renderFrame);
      };

      const handleVisibility = () => {
        pageVisible = document.visibilityState === "visible";
        window.cancelAnimationFrame(frameId);
        if (pageVisible && !reduceMotion) frameId = window.requestAnimationFrame(renderFrame);
      };

      const resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(host);
      resize();

      if (reduceMotion) {
        renderer.render(scene, camera);
      } else {
        window.addEventListener("pointermove", handlePointer, { passive: true });
        document.addEventListener("visibilitychange", handleVisibility);
        frameId = window.requestAnimationFrame(renderFrame);
      }

      teardownScene = () => {
        window.cancelAnimationFrame(frameId);
        resizeObserver.disconnect();
        window.removeEventListener("pointermove", handlePointer);
        document.removeEventListener("visibilitychange", handleVisibility);
        scene.remove(particles);
        geometry.dispose();
        material.dispose();
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      };
    }).catch(() => {
      if (!disposed) host.dataset.webgl = "unavailable";
    });

    return () => {
      disposed = true;
      teardownScene();
    };
  }, [reduceMotion]);

  return <div ref={hostRef} className="particle-field" aria-hidden="true" />;
}
