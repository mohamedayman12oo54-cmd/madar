import { useEffect, useState } from "react";
import { CircleHelp } from "lucide-react";
import { Btn, Modal } from "../auth/ui.jsx";
import { PAGE_INFO } from "./pageInfo.js";

export function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

const seenKey = (k) => `madar.pageInfo.seen.${k}`;
function wasSeen(k) { try { return localStorage.getItem(seenKey(k)) === "1"; } catch { return true; } }
function markSeen(k) { try { localStorage.setItem(seenKey(k), "1"); } catch { /* UI preference only */ } }

/** "What does this page do?" window. Opens by itself the first time a page is
 *  visited (a UI preference kept in this browser, not account data) and any
 *  time via the "?" button. */
export function InfoModal({ infoKey, onClose }) {
  const info = PAGE_INFO[infoKey];
  if (!info) return null;
  return (
    <Modal title={info.title} text={info.what} onClose={onClose}>
      <div className="info-body">
        <h4>ماذا يمكنك أن تفعل هنا؟</h4>
        <ul>{info.can.map((t) => <li key={t}>{t}</li>)}</ul>
        <h4>قواعد مهمة</h4>
        <ul>{info.rules.map((t) => <li key={t}>{t}</li>)}</ul>
        <Btn onClick={onClose}>فهمت</Btn>
      </div>
    </Modal>
  );
}

export function PageHeader({ infoKey, title, count, children }) {
  const [open, setOpen] = useState(false);
  useEffect(() => { if (!wasSeen(infoKey)) setOpen(true); }, [infoKey]);
  const close = () => { markSeen(infoKey); setOpen(false); };
  return (
    <>
      <div className="dash-section-head">
        <h2>
          {title}{count ? ` (${count})` : ""}
          <button type="button" className="info-btn" onClick={() => setOpen(true)} aria-label="ما وظيفة هذه الصفحة؟" title="ما وظيفة هذه الصفحة؟">
            <CircleHelp size={18} />
          </button>
        </h2>
        <div className="dash-head-actions">{children}</div>
      </div>
      {open && <InfoModal infoKey={infoKey} onClose={close} />}
    </>
  );
}

export function Empty({ title, text }) {
  return (
    <div className="dash-empty"><h2>{title}</h2>{text && <p>{text}</p>}</div>
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
  return (
    <input type="month" className="inp month-inp" value={value} max={max} onChange={(e) => e.target.value && onChange(e.target.value)} aria-label="الشهر" />
  );
}

export const fmtDateTime = (iso) => new Date(iso).toLocaleString("ar-EG", { dateStyle: "medium", timeStyle: "short" });
export const fmtMoney = (v) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 2 })} ج.م`;

export function errMessage(e, fallback) {
  return e?.message && e?.status ? e.message : fallback;
}

/** Confirm window for actions with consequences. */
export function Confirm({ title, text, confirmLabel = "تأكيد", danger, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={title} text={text} onClose={onClose}
      footer={<>
        <Btn variant="ghost" onClick={onClose}>إلغاء</Btn>
        <Btn variant={danger ? "danger" : "primary"} loading={busy} onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } }}>{confirmLabel}</Btn>
      </>} />
  );
}

export function CheckList({ items, selected, onToggle, empty = "لا توجد عناصر." }) {
  if (!items.length) return <p className="field-msg">{empty}</p>;
  return (
    <div className="check-grid">
      {items.map((it) => (
        <label key={it.id} className="check-item">
          <input type="checkbox" checked={selected.includes(it.id)} onChange={() => onToggle(it.id)} /> <span>{it.name}</span>
        </label>
      ))}
    </div>
  );
}

export const toggleId = (list, id) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
