/**
 * Wrapper around the View Transitions API. The browser snapshots the DOM
 * before and after `update()` runs, then morphs between them using any
 * `view-transition-name` pairings. Browsers without support fall through to
 * a plain synchronous update — callers can ignore the difference.
 */
type DocumentWithViewTransition = Document & {
  startViewTransition?: (cb: () => void) => { finished: Promise<void> };
};

export function withViewTransition(update: () => void): void {
  if (typeof document === "undefined") {
    update();
    return;
  }
  const doc = document as DocumentWithViewTransition;
  if (!doc.startViewTransition) {
    update();
    return;
  }
  doc.startViewTransition(update);
}
