/** Time-of-day picker ("HH:mm" value) — replaces the browser's native <input type="time">. */
import { useId, useRef, useState } from "react";
import { Clock } from "lucide-react";
import { from12h, to12h } from "../lib/datePicker.js";
import { fmtClock } from "../lib/dates.js";
import PickerPopover from "./PickerPopover.jsx";

const HOURS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);
const num = (n) => new Intl.NumberFormat("ar-EG", { useGrouping: false }).format(n);
const num2 = (n) => new Intl.NumberFormat("ar-EG", { minimumIntegerDigits: 2, useGrouping: false }).format(n);
const pad = (n) => String(n).padStart(2, "0");

export function parseClock(value) {
  const m = /^(\d{1,2}):(\d{2})/.exec(String(value || ""));
  if (!m) return null;
  const h = Number(m[1]); const mi = Number(m[2]);
  return h > 23 || mi > 59 ? null : { h, mi };
}

export default function TimePicker({ value, onChange, id, required }) {
  const auto = useId();
  const fieldId = id || auto;
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  const parsed = parseClock(value);
  const cur = parsed || { h: 16, mi: 0 };
  const { hour12, pm } = to12h(cur.h);
  const emit = (patch) => { const n = { ...cur, ...patch }; onChange(`${pad(n.h)}:${pad(n.mi)}`); };
  const close = () => { setOpen(false); triggerRef.current?.focus({ preventScroll: true }); };

  return (
    <>
      <button type="button" id={fieldId} ref={triggerRef} className={"inp dtp-trigger" + (parsed ? "" : " is-empty")}
        aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
        <Clock size={17} aria-hidden="true" />
        <span>{parsed ? fmtClock(value) : "اختر الوقت"}</span>
      </button>
      {required && <input tabIndex={-1} aria-hidden="true" className="dtp-required" required value={value || ""} onChange={() => {}} />}

      {open && (
        <PickerPopover triggerRef={triggerRef} label="اختيار الوقت" title="اختر الوقت" onClose={close} width={320}>
          <div className="dtp-time dtp-time-solo">
            <div className="dtp-time-top">
              <span className="dtp-label"><Clock size={14} aria-hidden="true" /> {parsed ? fmtClock(value) : "الوقت"}</span>
              <div className="dtp-ampm" role="group" aria-label="صباحًا أو مساءً">
                <button type="button" className={!pm ? "is-sel" : ""} onClick={() => emit({ h: from12h(hour12, false) })}>ص</button>
                <button type="button" className={pm ? "is-sel" : ""} onClick={() => emit({ h: from12h(hour12, true) })}>م</button>
              </div>
            </div>
            <div className="dtp-sub">الساعة</div>
            <div className="dtp-chips" role="group" aria-label="الساعة">
              {HOURS.map((h) => <button key={h} type="button" className={parsed && hour12 === h ? "is-sel" : ""} onClick={() => emit({ h: from12h(h, pm) })}>{num(h)}</button>)}
            </div>
            <div className="dtp-sub">الدقيقة</div>
            <div className="dtp-chips dtp-min" role="group" aria-label="الدقيقة">
              {MINUTES.map((m) => <button key={m} type="button" className={parsed && cur.mi === m ? "is-sel" : ""} onClick={() => emit({ mi: m })}>{num2(m)}</button>)}
            </div>
          </div>
          <button type="button" className="abtn abtn-primary dtp-done" onClick={close}>تم</button>
        </PickerPopover>
      )}
    </>
  );
}
