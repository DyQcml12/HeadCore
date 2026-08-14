import { useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export function useLandingAnimations(rootRef, reduceMotion) {
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;

    const context = gsap.context(() => {
      if (reduceMotion) {
        gsap.set(".hero-word, [data-hero-reveal], [data-scroll-reveal]", {
          clearProps: "all",
          opacity: 1,
        });
        return;
      }

      const entrance = gsap.timeline({ defaults: { ease: "power4.out" } });
      entrance
        .fromTo(
          ".hero-word",
          { opacity: 0, y: 80 },
          { opacity: 1, y: 0, duration: 1.05, stagger: 0.05 },
        )
        .fromTo(
          "[data-hero-reveal]",
          { opacity: 0, y: 24 },
          { opacity: 1, y: 0, duration: 0.75, stagger: 0.1 },
          "-=0.55",
        );

      ScrollTrigger.create({
        trigger: ".hero-pin",
        start: "top top",
        end: "+=45%",
        pin: true,
        pinSpacing: false,
        anticipatePin: 1,
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

    return () => context.revert();
  }, [rootRef, reduceMotion]);
}
