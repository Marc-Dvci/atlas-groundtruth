/** Whether this browser can start WebGL, which the map needs. `?nowebgl` in the address forces the fallback. */
let ok: boolean | null = null;

export function webglAvailable(): boolean {
  if (ok === null) {
    try {
      const c = document.createElement("canvas");
      ok = !new URLSearchParams(window.location.search).has("nowebgl") && !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch {
      ok = false;
    }
  }
  return ok;
}

export function markWebglFailed(): void {
  ok = false;
}
