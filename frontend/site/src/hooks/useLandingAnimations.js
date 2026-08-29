import { useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export function useLandingAnimations(rootRef, reduceMotion) {
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;

    let media;
    const context = gsap.context(() => {
      if (reduceMotion) {
        gsap.set(".hero-word, [data-hero-reveal], .hero-status, .scroll-cue, [data-scroll-reveal]", {
          clearProps: "all",
          opacity: 1,
          scale: 1,
          y: 0,
        });
        return;
      }

      const entrance = gsap.timeline({ defaults: { ease: "power4.out" } });
      entrance
        .fromTo(
          ".hero-word",
          { opacity: 0, y: 38 },
          { opacity: 1, y: 0, duration: 0.68, stagger: 0.026 },
        )
        .fromTo(
          ".hero-kicker, .hero-description, .hero-actions, .hero-status, .scroll-cue",
          { opacity: 0, y: 18 },
          { opacity: 1, y: 0, duration: 0.52, stagger: 0.08 },
          "-=0.48",
        );

      media = gsap.matchMedia();
      media.add("(min-width: 768px)", () => {
        ScrollTrigger.create({
          trigger: ".hero-pin",
          start: "top top",
          end: "+=34%",
          pin: true,
          pinSpacing: true,
          anticipatePin: 1,
        });
      });

      gsap.utils.toArray("[data-scroll-reveal]").forEach((element) => {
        gsap.fromTo(
          element,
          { opacity: 0, scale: 0.94, y: 40 },
          {
            opacity: 1,
            scale: 1,
            y: 0,
            duration: 0.85,
            immediateRender: false,
            ease: "power3.out",
            scrollTrigger: {
              trigger: element,
              start: "top 86%",
              once: true,
            },
          },
        );
      });

    }, root);

    return () => {
      media?.revert();
      context.revert();
    };
  }, [rootRef, reduceMotion]);
}
