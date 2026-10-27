/** Smooth scroll driven by requestAnimationFrame and performance.now, so it follows the page clock
 * (the browser's native smooth scroll runs on its own timer, which a frozen-clock film capture cannot step). */
export function smoothScroll(el: HTMLElement | Window, top: number, ms = 900): void {
  const isWin = el === window;
  const from = isWin ? window.scrollY : (el as HTMLElement).scrollTop;
  const t0 = performance.now();
  const step = () => {
    const k = Math.min(1, (performance.now() - t0) / ms);
    const e = 1 - Math.pow(1 - k, 3);
    const y = from + (top - from) * e;
    if (isWin) window.scrollTo(0, y);
    else (el as HTMLElement).scrollTop = y;
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
