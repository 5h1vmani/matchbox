/* Dialog a11y, shared by both drawers (tracker Detail + discovery JD).
   Focuses the panel on open, traps Tab within it, closes on Escape, and restores
   focus to the trigger on close. Pair with role="dialog" aria-modal aria-label
   tabIndex={-1} on the returned ref's element. */
import { useEffect, useRef } from "react";

export function useDialog<T extends HTMLElement>(onClose: () => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const restoreTo = document.activeElement as HTMLElement | null;
    const node = ref.current;
    node?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !node) return;
      const f = node.querySelectorAll<HTMLElement>(
        'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])',
      );
      if (f.length === 0) return;
      const first = f[0];
      const last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      restoreTo?.focus?.();
    };
  }, [onClose]);
  return ref;
}
