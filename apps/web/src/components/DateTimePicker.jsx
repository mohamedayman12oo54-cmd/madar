/**
 * Date + time picker used instead of the browser's native <input
 * type="datetime-local">, whose popup cannot be styled and looks different
 * on every device.
 *
 * - Desktop: a card anchored under the field.
 * - Phone: a bottom sheet with large tap targets.
 * - Saturday-first Arabic calendar, 12-hour clock with ص / م.
 * It is rendered through a portal so a scrolling dialog can never clip it.
 */
import { useId, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Clock } from "lucide-react";
import { formatLocal, from12h, monthGrid, parseLocal, shiftMonth, to12h } from "../lib/datePicker.js";
import PickerPopover from "./PickerPopover.jsx";

const AR = "ar-EG";
const WEEKDAYS = ["س", "ح", "ن", "ث", "ر", "خ", "ج"]; // Sat..Fri
const HOURS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);
const num = (n) => new Intl.NumberFormat(AR, { useGrouping: false }).format(n);
const num2 = (n) => new Intl.NumberFormat(AR, { minimumIntegerDigits: 2, useGrouping: false }).format(n);
const monthName = (y, m) => new Intl.DateTimeFormat(AR, { month: "long", year: "numeric" }).format(new Date(y, m, 1));

function summary(v) {
  const p = parseLocal(v);
  if (!p) return "";
  const d = new Date(p.y, p.m, p.d, p.h, p.mi);
  const date = new Intl.DateTimeFormat(AR, { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(d);
  const time = new Intl.DateTimeFormat(AR, { hour: "numeric", minute: "2-digit" }).format(d);
  return `${date} • ${time}`;
}

export default function DateTimePicker({ value, onChange, id, required }) {
  const auto = useId();
  const fieldId = id || auto;
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);

  const parsed = useMemo(() => parseLocal(value), [value]);
  const now = new Date();
  const base = parsed || { y: now.getFullYear(), m: now.getMonth(), d: now.getDate(), h: 16, mi: 0 };
  const [view, setView] = useState({ year: base.y, month: base.m });

  const openPicker = () => { setView({ year: base.y, month: base.m }); setOpen(true); };
  const close = () => { setOpen(false); triggerRef.current?.focus({ preventScroll: true }); };

  const emit = (patch) => onChange(formatLocal({ ...base, ...patch }));
  const { hour12, pm } = to12h(base.h);
  const isSel = (d) => parsed && parsed.y === view.year && parsed.m === view.month && parsed.d === d;
  const isToday = (d) => now.getFullYear() === view.year && now.getMonth() === view.month && now.getDate() === d;
  const pickDay = (d) => emit({ y: view.year, m: view.month, d });
  const quick = (offset) => {
    const t = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset);
    setView({ year: t.getFullYear(), month: t.getMonth() });
    emit({ y: t.getFullYear(), m: t.getMonth(), d: t.getDate() });
  };

  return (
    <>
      <button type="button" id={fieldId} ref={triggerRef} className={"inp dtp-trigger" + (parsed ? "" : " is-empty")}
        aria-haspopup="dialog" aria-expanded={open} onClick={openPicker}>
        <CalendarDays size={17} aria-hidden="true" />
        <span>{summary(value) || "اختر التاريخ والوقت"}</span>
      </button>
      {required && <input tabIndex={-1} aria-hidden="true" className="dtp-required" required value={value || ""} onChange={() => {}} />}

      {open && (
        <PickerPopover triggerRef={triggerRef} label="اختيار التاريخ والوقت" title="اختر التاريخ والوقت" onClose={close} deps={[view]}>
            <div className="dtp-quick">
              <button type="button" onClick={() => quick(0)}>اليوم</button>
              <button type="button" onClick={() => quick(1)}>غدًا</button>
            </div>

            <div className="dtp-head">
              <button type="button" aria-label="الشهر السابق" onClick={() => setView((v) => shiftMonth(v.year, v.month, -1))}><ChevronRight size={18} /></button>
              <strong aria-live="polite">{monthName(view.year, view.month)}</strong>
              <button type="button" aria-label="الشهر التالي" onClick={() => setView((v) => shiftMonth(v.year, v.month, 1))}><ChevronLeft size={18} /></button>
            </div>

            <div className="dtp-grid" role="grid">
              {WEEKDAYS.map((w) => <span key={w} className="dtp-wd" aria-hidden="true">{w}</span>)}
              {monthGrid(view.year, view.month).flat().map((d, i) => d === null
                ? <span key={i} />
                : <button key={i} type="button" className={"dtp-day" + (isSel(d) ? " is-sel" : "") + (isToday(d) ? " is-today" : "")}
                    aria-pressed={isSel(d)} onClick={() => pickDay(d)}>{num(d)}</button>)}
            </div>

            <div className="dtp-time">
              <div className="dtp-time-top">
                <span className="dtp-label"><Clock size={14} aria-hidden="true" /> الوقت</span>
                <div className="dtp-ampm" role="group" aria-label="صباحًا أو مساءً">
                  <button type="button" className={parsed && !pm ? "is-sel" : ""} onClick={() => emit({ h: from12h(hour12, false) })}>ص</button>
                  <button type="button" className={parsed && pm ? "is-sel" : ""} onClick={() => emit({ h: from12h(hour12, true) })}>م</button>
                </div>
              </div>
              <div className="dtp-chips" role="group" aria-label="الساعة">
                {HOURS.map((h) => <button key={h} type="button" className={parsed && hour12 === h ? "is-sel" : ""} onClick={() => emit({ h: from12h(h, pm) })}>{num(h)}</button>)}
              </div>
              <div className="dtp-chips dtp-min" role="group" aria-label="الدقيقة">
                {MINUTES.map((m) => <button key={m} type="button" className={parsed && base.mi === m ? "is-sel" : ""} onClick={() => emit({ mi: m })}>{num2(m)}</button>)}
              </div>
            </div>

            <button type="button" className="abtn abtn-primary dtp-done" onClick={close}>تم</button>
        </PickerPopover>
      )}
    </>
  );
}
