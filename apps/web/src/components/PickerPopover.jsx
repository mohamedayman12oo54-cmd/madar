/**
 * Shared shell for every date / time / month picker.
 *
 * - Desktop: a card anchored under the trigger (flips above when there is no
 *   room, stays inside the viewport). RTL-aware: its end edge lines up with
 *   the trigger's end edge.
 * - Phone (<= 600px): a bottom sheet with a grab handle and big tap targets.
 * - Rendered through a portal so a scrolling dialog can never clip it.
 * - Esc and an outside tap close ONLY the picker, never the dialog behind it.
 * - The sheet stays invisible until it has been measured, so it never flashes
 *   in the wrong place.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import "./date-time-picker.css";

export default function PickerPopover({
  triggerRef,
  label,
  title,
  onClose,
  deps = [],
  width = 340,
  children,
}) {
  const sheetRef = useRef(null);
  const [pos, setPos] = useState(null);
  const [placed, setPlaced] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        e.stopImmediatePropagation?.();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  useLayoutEffect(() => {
    const place = () => {
      const t = triggerRef.current?.getBoundingClientRect();
      const s = sheetRef.current;
      if (!t || !s || window.innerWidth <= 600) {
        setPos(null);
        setPlaced(true);
        return;
      }
      const w = Math.min(width, window.innerWidth - 24);
      const h = s.offsetHeight;
      const left = Math.min(Math.max(12, t.right - w), window.innerWidth - w - 12);
      let top = t.bottom + 8;
      if (top + h > window.innerHeight - 12) top = Math.max(12, t.top - h - 8);
      setPos({ top, left, width: w });
      setPlaced(true);
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return createPortal(
    <div
      className="dtp-layer"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={sheetRef}
        className="dtp-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={label}
        style={{
          ...(pos ? { top: pos.top, left: pos.left, width: pos.width } : {}),
          visibility: placed ? "visible" : "hidden",
        }}
      >
        <div className="dtp-grab" aria-hidden="true" />
        <div className="dtp-titlebar">
          <strong>{title || label}</strong>
          <button type="button" className="dtp-x" aria-label="إغلاق" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body
  );
}
