/** Month picker ("YYYY-MM" value) — replaces the browser's native <input type="month">. */
import { useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { fmtMonth } from "../lib/dates.js";
import PickerPopover from "./PickerPopover.jsx";

const MONTHS = Array.from({ length: 12 }, (_, i) => new Intl.DateTimeFormat("ar-EG", { month: "long" }).format(new Date(2000, i, 1)));
const year = (n) => new Intl.NumberFormat("ar-EG", { useGrouping: false }).format(n);
const ym = (y, m) => `${y}-${String(m + 1).padStart(2, "0")}`;

export default function MonthPicker({ value, onChange, max, min, label = "الشهر" }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  const now = new Date();
  const m = /^(\d{4})-(\d{2})/.exec(value || "");
  const sel = m ? { y: Number(m[1]), m: Number(m[2]) - 1 } : null;
  const [viewYear, setViewYear] = useState(sel?.y ?? now.getFullYear());
  const close = () => { setOpen(false); triggerRef.current?.focus({ preventScroll: true }); };
  const disabled = (mi) => { const k = ym(viewYear, mi); return (max && k > max) || (min && k < min); };
  const thisMonth = ym(now.getFullYear(), now.getMonth());

  return (
    <>
      <button type="button" ref={triggerRef} className="inp dtp-trigger month-inp" aria-label={label}
        aria-haspopup="dialog" aria-expanded={open}
        onClick={() => { setViewYear(sel?.y ?? now.getFullYear()); setOpen(true); }}>
        <CalendarDays size={17} aria-hidden="true" />
        <span>{fmtMonth(value)}</span>
      </button>
      {open && (
        <PickerPopover triggerRef={triggerRef} label="اختيار الشهر" title="اختر الشهر" onClose={close} width={300} deps={[viewYear]}>
          <div className="dtp-quick">
            <button type="button" disabled={Boolean(max) && thisMonth > max} onClick={() => { onChange(thisMonth); close(); }}>هذا الشهر</button>
          </div>
          <div className="dtp-head">
            <button type="button" aria-label="السنة السابقة" onClick={() => setViewYear((y) => y - 1)}><ChevronRight size={18} /></button>
            <strong aria-live="polite">{year(viewYear)}</strong>
            <button type="button" aria-label="السنة التالية" onClick={() => setViewYear((y) => y + 1)}><ChevronLeft size={18} /></button>
          </div>
          <div className="dtp-months" role="group" aria-label="الشهور">
            {MONTHS.map((name, i) => {
              const isSel = sel && sel.y === viewYear && sel.m === i;
              const isNow = now.getFullYear() === viewYear && now.getMonth() === i;
              return (
                <button key={i} type="button" disabled={disabled(i)} aria-pressed={Boolean(isSel)}
                  className={(isSel ? "is-sel " : "") + (isNow ? "is-today" : "")}
                  onClick={() => { onChange(ym(viewYear, i)); close(); }}>{name}</button>
              );
            })}
          </div>
        </PickerPopover>
      )}
    </>
  );
}
