import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, CircleHelp, Inbox } from "lucide-react";
import { Btn, Modal } from "../auth/ui.jsx";
import { PAGE_INFO } from "./pageInfo.js";
import MonthPicker from "../components/MonthPicker.jsx";

export function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

const seenKey = (k) => `madar.pageInfo.seen.${k}`;
function wasSeen(k) {
  try {
    return localStorage.getItem(seenKey(k)) === "1";
  } catch {
    return true;
  }
}
function markSeen(k) {
  try {
    localStorage.setItem(seenKey(k), "1");
  } catch {
    /* UI preference only */
  }
}

/** "What does this page do?" window. Opens by itself the first time a page is
 *  visited (a UI preference kept in this browser, not account data) and any
 *  time via the "?" button. */
export function InfoModal({ infoKey, onClose }) {
  const info = PAGE_INFO[infoKey];
  if (!info) return null;
  return (
    <Modal
      title={info.title}
      text={info.what}
      onClose={onClose}
      footer={<Btn onClick={onClose}>فهمت</Btn>}
    >
      <div className="info-body">
        <h4>ماذا يمكنك أن تفعل هنا؟</h4>
        <ul>
          {info.can.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
        <h4>قواعد مهمة</h4>
        <ul>
          {info.rules.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      </div>
    </Modal>
  );
}

export function PageHeader({ infoKey, title, count, sub, children }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!wasSeen(infoKey)) setOpen(true);
  }, [infoKey]);
  const close = () => {
    markSeen(infoKey);
    setOpen(false);
  };
  return (
    <>
      <div className="dash-section-head">
        <h2>
          {title}
          {count ? ` (${count})` : ""}
          <button
            type="button"
            className="info-btn"
            onClick={() => setOpen(true)}
            aria-label="ما وظيفة هذه الصفحة؟"
            title="ما وظيفة هذه الصفحة؟"
          >
            <CircleHelp size={18} />
          </button>
        </h2>
        <div className="dash-head-actions">{children}</div>
      </div>
      {open && <InfoModal infoKey={infoKey} onClose={close} />}
      {sub && <p className="dash-sub">{sub}</p>}
    </>
  );
}

export function Empty({ title, text, icon: Icon = Inbox }) {
  return (
    <div className="dash-empty">
      <span className="ic" aria-hidden="true">
        <Icon size={22} strokeWidth={1.8} />
      </span>
      <h2>{title}</h2>
      {text && <p>{text}</p>}
    </div>
  );
}

export function currentMonthValue() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function MonthInput({ value, onChange }) {
  const d = new Date();
  const next = new Date(d.getFullYear(), d.getMonth() + 1, 1);
  const max = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`;
  return <MonthPicker value={value} max={max} onChange={(v) => v && onChange(v)} />;
}

export { fmtDate, fmtTime, fmtDateTime, fmtMonth } from "../lib/dates.js";
export const fmtMoney = (v) =>
  `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 2 })} ج.م`;

export function errMessage(e, fallback) {
  return e?.message && e?.status ? e.message : fallback;
}

/** Confirm window for actions with consequences. */
export function Confirm({ title, text, confirmLabel = "تأكيد", danger, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      title={title}
      text={text}
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            إلغاء
          </Btn>
          <Btn
            variant={danger ? "danger" : "primary"}
            loading={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm();
              } finally {
                setBusy(false);
              }
            }}
          >
            {confirmLabel}
          </Btn>
        </>
      }
    />
  );
}

export function CheckList({ items, selected, onToggle, empty = "لا توجد عناصر." }) {
  if (!items.length) return <p className="field-msg">{empty}</p>;
  return (
    <div className="check-grid">
      {items.map((it) => (
        <label key={it.id} className="check-item">
          <input
            type="checkbox"
            checked={selected.includes(it.id)}
            onChange={() => onToggle(it.id)}
          />{" "}
          <span>{it.name}</span>
        </label>
      ))}
    </div>
  );
}

/**
 * Searchable dropdown. `multiple` => checkbox-style multi-select with removable chips;
 * otherwise a single choice. `items` are `{ id, name, hint? }`.
 * Keyboard: ArrowUp/Down move, Enter picks, Esc closes. Renders inside the form flow (no portal),
 * so it works inside modals without focus-trap surprises.
 */
export function SearchSelect({
  items,
  value,
  onChange,
  multiple = false,
  placeholder = "اختر…",
  searchPlaceholder = "ابحث…",
  empty = "لا توجد عناصر.",
  disabled = false,
  id,
}) {
  const uid = useId();
  const boxRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);

  const selected = multiple ? value || [] : value === "" || value == null ? [] : [value];
  const norm = (t) => String(t || "").toLowerCase().replace(/[\u064b-\u065f\u0640]/g, "");
  const shown = items.filter((it) => !q.trim() || norm(it.name).includes(norm(q)));

  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);

  useEffect(() => setCursor(0), [q, open]);

  const pick = (it) => {
    if (multiple) {
      onChange(selected.includes(it.id) ? selected.filter((x) => x !== it.id) : [...selected, it.id]);
    } else {
      onChange(it.id);
      setOpen(false);
      setQ("");
    }
  };

  const onKey = (e) => {
    if (e.key === "Escape") {
      if (open) e.stopPropagation();
      setOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setCursor((c) => Math.min(c + 1, Math.max(shown.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      if (shown[cursor]) pick(shown[cursor]);
    }
  };

  const label = (idv) => items.find((it) => it.id === idv)?.name || "";
  const summary = multiple
    ? selected.length
      ? `${selected.length} محدد`
      : placeholder
    : selected.length
    ? label(selected[0]) || placeholder
    : placeholder;

  return (
    <div className="ss" ref={boxRef}>
      <button
        type="button"
        id={id}
        className={"inp ss-trigger" + (selected.length ? "" : " is-empty")}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${uid}-list`}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onKey}
      >
        <span className="ss-value">{summary}</span>
        <ChevronDown size={16} aria-hidden="true" />
      </button>

      {multiple && selected.length > 0 && (
        <div className="ss-chips">
          {selected.map((idv) => (
            <span key={idv} className="ss-chip">
              {label(idv)}
              <button
                type="button"
                aria-label={`إزالة ${label(idv)}`}
                onClick={() => onChange(selected.filter((x) => x !== idv))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {open && (
        <div className="ss-pop">
          <input
            className="inp ss-search"
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKey}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            role="combobox"
            aria-expanded="true"
            aria-controls={`${uid}-list`}
            aria-activedescendant={shown[cursor] ? `${uid}-o${shown[cursor].id}` : undefined}
          />
          <ul id={`${uid}-list`} className="ss-list" role="listbox" aria-multiselectable={multiple}>
            {items.length === 0 && <li className="ss-none">{empty}</li>}
            {items.length > 0 && shown.length === 0 && <li className="ss-none">لا نتائج مطابقة.</li>}
            {shown.map((it, i) => {
              const on = selected.includes(it.id);
              return (
                <li
                  key={it.id}
                  id={`${uid}-o${it.id}`}
                  role="option"
                  aria-selected={on}
                  className={"ss-opt" + (on ? " is-on" : "") + (i === cursor ? " is-cur" : "")}
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => pick(it)}
                >
                  <span className="ss-tick" aria-hidden="true">
                    {on ? "✓" : ""}
                  </span>
                  <span>{it.name}</span>
                  {it.hint ? <span className="ss-hint">{it.hint}</span> : null}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

export const toggleId = (list, id) =>
  list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
