"use client";
import { useEffect } from "react";

/** Elements marked data-reveal rise in the first time they scroll into view.
 *  Only elements still below the fold are hidden, and only once JS runs, so nothing is ever stuck invisible. */
export function useReveal() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) return;
    const els = [...document.querySelectorAll<HTMLElement>("[data-reveal]")].filter((el) => el.getBoundingClientRect().top > window.innerHeight * 0.9);
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.classList.add("is-in");
        io.unobserve(e.target);
      }
    }, { rootMargin: "0px 0px -12% 0px" });
    for (const el of els) {
      el.classList.add("reveal-armed");
      io.observe(el);
    }
    return () => io.disconnect();
  }, []);
}
