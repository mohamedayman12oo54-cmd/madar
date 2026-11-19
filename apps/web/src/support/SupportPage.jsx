// "Help & support" for teachers and students: open a ticket or complaint, follow it, answer the team, rate the
// result. The server returns ONLY the caller's own tickets and never includes internal team notes.
import { useEffect, useRef, useState } from "react";
import { ArrowRight, LifeBuoy, Paperclip, Plus, Send, Star, X } from "lucide-react";
import { Btn, Field, Modal, TextInput } from "../auth/ui.jsx";
import { supportApi } from "../lib/controlApi.js";
import { TICKET_STATUS, RESPONSE } from "../team/labels.js";
import {
  Async,
  Card,
  ControlProvider,
  DataTable,
  EmptyState,
  ErrorState,
  Select,
  Skeleton,
  StatusBadge,
  TextArea,
  dt,
  errText,
  fieldErrors,
  useAction,
  useApi,
  useToast,
} from "../team/kit.jsx";
import "../team/control.css";

function Files({ files, setFiles }) {
  const ref = useRef(null);
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <input ref={ref} type="file" multiple hidden accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt" onChange={(e) => { setFiles([...files, ...e.target.files].slice(0, 3)); e.target.value = ""; }} />
      <div className="atts">
        {files.map((f, i) => (
          <span className="cc-att" key={i}>{f.name}<button type="button" aria-label="إزالة" onClick={() => setFiles(files.filter((_, j) => j !== i))} style={{ all: "unset", cursor: "pointer" }}><X size={13} /></button></span>
        ))}
        {files.length < 3 && <button type="button" className="cc-att" onClick={() => ref.current.click()}><Paperclip size={14} /> إرفاق ملف</button>}
      </div>
      <span className="sub">حتى 3 ملفات، 5 ميجابايت للملف (صور، PDF، نص).</span>
    </div>
  );
}

function NewTicket({ onClose, onCreated }) {
  const cats = useApi(() => supportApi.categories(), []);
  const [form, setForm] = useState({ subject: "", description: "", category: "", kind: "ticket" });
  const [files, setFiles] = useState([]);
  const [errs, setErrs] = useState({});
  const [run, busy] = useAction();
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <Modal size="md" title="طلب دعم جديد" text="اشرح المشكلة بوضوح وسيردّ عليك فريق مدار هنا." onClose={onClose}
      footer={<><Btn variant="ghost" onClick={onClose}>إلغاء</Btn><Btn loading={busy} loadingText="جارٍ الإرسال…" onClick={() => run(async () => { const bad = {}; if (form.subject.trim().length < 3) bad.subject = "اكتب عنوانًا من 3 أحرف على الأقل."; if (form.description.trim().length < 5) bad.description = "اكتب تفاصيل أوضح للمشكلة."; if (!form.category) bad.category = "اختر التصنيف."; setErrs(bad); if (Object.keys(bad).length) return false; try { const t = await supportApi.create({ ...form, category: Number(form.category) || "" }, files); onCreated(t); onClose(); } catch (e) { setErrs(fieldErrors(e)); throw e; } }, "وصلنا طلبك وسنردّ قريبًا")}><Send size={15} /> إرسال</Btn></>}>
      <div style={{ display: "grid", gap: 8 }}>
        <Field label="نوع الطلب"><Select all={null} value={form.kind} onChange={(v) => setForm({ ...form, kind: v })} options={[{ value: "ticket", label: "مشكلة أو استفسار" }, { value: "complaint", label: "شكوى" }]} /></Field>
        <Field label="التصنيف" required error={errs.category}><Select all="اختر التصنيف…" value={form.category} onChange={(v) => setForm({ ...form, category: v })} options={(cats.data || []).map((c) => ({ value: c.id, label: c.name }))} /></Field>
        <Field label="العنوان" required error={errs.subject}><TextInput value={form.subject} onChange={set("subject")} maxLength={200} /></Field>
        <Field label="التفاصيل" required error={errs.description}><TextArea rows={5} value={form.description} onChange={set("description")} maxLength={5000} /></Field>
        <Files files={files} setFiles={setFiles} />
      </div>
    </Modal>
  );
}

function Rating({ ticket, onDone }) {
  const [stars, setStars] = useState(0);
  const [comment, setComment] = useState("");
  const [run, busy] = useAction();
  return (
    <div className="composer">
      <b>كيف كانت تجربتك مع الدعم؟</b>
      <div role="radiogroup" aria-label="التقييم" style={{ display: "flex", gap: 4 }}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" role="radio" aria-checked={stars === n} aria-label={`${n} من 5`} onClick={() => setStars(n)} style={{ all: "unset", cursor: "pointer", padding: 4, color: n <= stars ? "#eda100" : "#aab0ba" }}>
            <Star size={26} fill={n <= stars ? "currentColor" : "none"} />
          </button>
        ))}
      </div>
      <TextArea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} placeholder="ملاحظاتك (اختياري)" aria-label="ملاحظاتك" />
      <div><Btn disabled={!stars} loading={busy} loadingText="جارٍ الإرسال…" onClick={() => run(async () => onDone(await supportApi.rate(ticket.id, stars, comment)), "شكرًا لتقييمك")}>إرسال التقييم</Btn></div>
    </div>
  );
}

function TicketView({ id, onBack }) {
  const toast = useToast();
  const api = useApi(() => supportApi.get(id), [id]);
  const [local, setLocal] = useState(null);
  const [body, setBody] = useState("");
  const [files, setFiles] = useState([]);
  const [run, busy] = useAction();
  const t = local || api.data;
  useEffect(() => {
    setLocal(null);
  }, [id]);
  if (api.error && !api.data) return <ErrorState error={api.error} onRetry={api.reload} />;
  if (!t) return <Skeleton rows={6} />;
  return (
    <>
      <div className="cc-actions"><Btn variant="ghost" onClick={onBack}><ArrowRight size={16} /> كل طلباتي</Btn></div>
      <Card title={`${t.number} · ${t.subject}`} sub={`${t.category} · ${dt(t.created_at)}`} actions={<StatusBadge map={TICKET_STATUS} value={t.status} />} pad={false}>
        <div className="convo">
          {t.messages.map((m) => (
            <article key={m.id} className={"cc-msg " + (m.kind === "customer" ? "customer" : "agent")} style={m.kind === "customer" ? { marginInlineStart: "auto" } : undefined}>
              <div className="who"><b>{m.kind === "customer" ? "أنت" : "فريق مدار"}</b><span>{dt(m.created_at)}</span></div>
              <div className="body">{m.body}</div>
              {m.attachments.length > 0 && <div className="atts">{m.attachments.map((a) => <button key={a.id} type="button" className="cc-att" onClick={() => supportApi.downloadAttachment(a.id, a.name).catch((e) => toast(errText(e), "err"))}><Paperclip size={13} /> {a.name}</button>)}</div>}
            </article>
          ))}
        </div>
        {t.can_reply ? (
          <div className="composer">
            {t.status === "resolved" && <p className="sub">تم حل الطلب. إن لم تُحل المشكلة، اكتب هنا وسنعيد فتحه.</p>}
            <TextArea rows={3} value={body} onChange={(e) => setBody(e.target.value)} maxLength={5000} placeholder="اكتب ردّك…" aria-label="ردّك" />
            <Files files={files} setFiles={setFiles} />
            <div><Btn loading={busy} loadingText="جارٍ الإرسال…" onClick={() => run(async () => { if (!body.trim()) throw new Error("اكتب نص الرسالة أولًا."); setLocal(await supportApi.reply(t.id, body, files)); setBody(""); setFiles([]); }, "أُرسل ردّك")}><Send size={15} /> إرسال</Btn></div>
          </div>
        ) : (
          <div className="composer"><span className="sub">أُغلق هذا الطلب. إن احتجت مساعدة إضافية فافتح طلبًا جديدًا.</span></div>
        )}
        {t.can_rate && <Rating ticket={t} onDone={setLocal} />}
        {t.rating && <div className="composer"><span className="sub">تقييمك: {t.rating}/5</span></div>}
      </Card>
    </>
  );
}

function Inner() {
  const [open, setOpen] = useState(null);
  const [creating, setCreating] = useState(false);
  const api = useApi(() => supportApi.list(), []);
  return (
    <div className="cc cc-embed" style={{ display: "grid", gap: 16 }}>
      <div className="cc-head">
        <div><h1>الدعم والمساعدة</h1><p>تواصل مع فريق مدار: مشكلة، استفسار أو شكوى. نردّ هنا وتتابع الحالة في أي وقت.</p></div>
        <div className="cc-actions"><Btn onClick={() => setCreating(true)}><Plus size={16} /> طلب جديد</Btn></div>
      </div>
      {open ? (
        <TicketView id={open} onBack={() => { setOpen(null); api.reload(); }} />
      ) : (
        <Card pad={false}>
          <Async api={api}>
            {(rows) => (
              <DataTable rows={rows} onRow={(t) => setOpen(t.id)} empty={<EmptyState icon={LifeBuoy} title="لا توجد طلبات بعد" text="اضغط «طلب جديد» عندما تحتاج مساعدة." />} columns={[
                { key: "number", label: "الرقم", render: (t) => <span className="strong ltr">{t.number}</span> },
                { key: "subject", label: "الموضوع", render: (t) => <span className="strong">{t.subject}</span> },
                { key: "category", label: "التصنيف" },
                { key: "status", label: "الحالة", render: (t) => <StatusBadge map={TICKET_STATUS} value={t.status} /> },
                { key: "response_status", label: "بانتظار", render: (t) => (t.response_status === "done" ? "—" : <StatusBadge map={{ awaiting_team: ["فريق مدار", "warn"], awaiting_customer: ["ردّك أنت", "info"] }} value={t.response_status} />) },
                { key: "updated_at", label: "آخر تحديث", render: (t) => dt(t.updated_at) },
              ]} />
            )}
          </Async>
        </Card>
      )}
      {creating && <NewTicket onClose={() => setCreating(false)} onCreated={(t) => { api.reload(); setOpen(t.id); }} />}
    </div>
  );
}

/** Default export: the page, with its own toast host (no team permissions are involved). */
export default function SupportPage() {
  return (
    <ControlProvider me={{ permissions: [] }}>
      <Inner />
    </ControlProvider>
  );
}
