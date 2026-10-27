/**
 * After a deploy, a tab opened before it still runs the old build. When it
 * opens a page for the first time it asks for that page's code file, which the
 * new build no longer has, and the page would fail ("Something went wrong").
 * Vite reports exactly this as the `vite:preloadError` event; the tab then
 * reloads once to get the new build. At most one reload per minute, so a file
 * that is truly missing shows the error instead of reloading in a loop.
 */

const KEY = "mizan_stale_build_reload";
const WINDOW_MS = 60_000;

type Store = Pick<Storage, "getItem" | "setItem">;

function sessionStore(): Store | null {
  try {
    return window.sessionStorage;
  } catch {
    return null; // storage blocked: still reload once, without the guard
  }
}

export function shouldReload(now: number, store: Store | null): boolean {
  let last = Number.NEGATIVE_INFINITY;
  try {
    const saved = Number(store?.getItem(KEY));
    if (Number.isFinite(saved) && saved > 0) last = saved;
  } catch {
    // unreadable storage: treat as never reloaded
  }
  if (now - last < WINDOW_MS) return false;
  try {
    store?.setItem(KEY, String(now));
  } catch {
    // a reload without the guard is still better than a broken page
  }
  return true;
}

export function installStaleBuildReload(target: Window = window): void {
  target.addEventListener("vite:preloadError", (event) => {
    if (shouldReload(Date.now(), sessionStore())) {
      event.preventDefault();
      target.location.reload();
    }
  });
}
