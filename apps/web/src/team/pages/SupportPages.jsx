import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Download, Lock, MessageSquarePlus, Paperclip, Plus, Send, Trash2, X } from "lucide-react";
import { Btn, Field, Modal, TextInput } from "../../auth/ui.jsx";
import { controlApi } from "../../lib/controlApi.js";
import { ACCOUNT_STATUS, KIND, PRIORITY, RESPONSE, TICKET_STATUS, USER_ROLE } from "../labels.js";
import {
  Async,
  Badge,
  Card,
  ChartCard,
  Confirm,
  DataTable,
  EmptyState,
  ErrorState,
  HBars,
  Input,
  KV,
  LineChart,
  BarChart,
  PageHead,
  Pager,
  PriorityBadge,
  RangePicker,
  SERIES,
  SearchBox,
  Select,
  Skeleton,
  StatusBadge,
  TextArea,
  Trend,
  ago,
  dt,
  errText,
  fieldErrors,
  hoursText,
  num,
  opts,
  rangeParams,
  tableOf,
  toSeries,
  useAction,
  useApi,
  useCan,
  useControl,
  useDebounce,
  useFilters,
  useSort,
  useToast,
} from "../kit.jsx";

const PRIORITY_OPTS = opts(PRIORITY);
const STATUS_OPTS = opts(TICKET_STATUS);

/* ------------------------------------------------------------------ support center */
export function SupportCenterPage() {
  const [range, setRange] = useState({ range: "30d" });
  const p = rangeParams(range);
  const ov = useApi(() => controlApi.supportOverview(p), [JSON.stringify(p)]);
  const can = useCan();
  const agents = useApi(() => controlApi.agents(), []);
  const cards = (d) => [
    ["إجمالي التذاكر", d.total, "/team/support/tickets"],
    ["مفتوحة", d.open, "/team/support/tickets?status=open"],
    ["قيد المعالجة", d.in_progress, "/team/support/tickets?status=in_progress"],
    ["بانتظار العميل", d.waiting_for_user, "/team/support/tickets?status=waiting_for_user"],
    ["تم الحل", d.resolved, "/team/support/tickets?status=resolved"],
    ["مغلقة", d.closed, "/team/support/tickets?status=closed"],
    ["غير مسندة", d.unassigned, "/team/support/unassigned", "warn"],
    ["أولوية عالية/حرجة", d.high_priority, "/team/support/tickets?priority=high", "warn"],
    ["متأخرة", d.overdue, "/team/support/tickets?overdue=1", "bad"],
  ];
  return (
    <>
      <PageHead title="مركز الدعم" desc="نظرة تشغيلية على التذاكر والشكاوى وأداء الفريق." crumbs={[{ label: "الدعم" }, { label: "مركز الدعم" }]}>
        <RangePicker value={range} onChange={setRange} />
        {can("tickets.create") && (
          <Link className="abtn abtn-primary" to="/team/support/tickets?new=1">
            <Plus size={16} /> تذكرة جديدة
          </Link>
        )}
      </PageHead>
      <Async api={ov} rows={6}>
        {(d) => (
          <>
            <div className="cc-grid kpi">
              {cards(d).map(([label, v, to, tone]) => (
                <Link key={label} to={to} className={"cc-card kpi " + (tone || "")}>
                  <div className="top"><span>{label}</span></div>
                  <div className="val">{num(v)}</div>
                </Link>
              ))}
              <div className="cc-card kpi"><div className="top"><span>متوسط أول رد</span></div><div className="val">{hoursText(d.avg_first_response_hours)}</div><div className="cmp">للتذاكر المنشأة في الفترة</div></div>
              <div className="cc-card kpi"><div className="top"><span>متوسط زمن الحل</span></div><div className="val">{hoursText(d.avg_resolution_hours)}</div><div className="cmp">للتذاكر المحلولة في الفترة</div></div>
            </div>
          </>
        )}
      </Async>
      <Card title="عبء العمل على الموظفين" sub="التذاكر النشطة المسندة لكل موظف" pad={false}>
        <Async api={agents} rows={3}>
          {(rows) => (
            <DataTable
              rows={rows}
              empty={<EmptyState title="لا يوجد موظفو دعم" />}
              columns={[
                { key: "name", label: "الموظف", render: (a) => <span className="strong">{a.name}</span> },
                { key: "role", label: "الدور" },
                { key: "active", label: "تذاكر نشطة", render: (a) => num(a.active) },
                { key: "resolved", label: "تذاكر محلولة", render: (a) => num(a.resolved) },
                { key: "overloaded", label: "الحالة", render: (a) => (a.overloaded ? <Badge tone="bad">مزدحم</Badge> : <Badge tone="ok">طبيعي</Badge>) },
                { key: "link", label: "", render: (a) => <Link to={`/team/support/tickets?assignee=${a.id}`} style={{ textDecoration: "underline" }}>عرض تذاكره</Link> },
              ]}
            />
          )}
        </Async>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------------ create ticket (on behalf of a customer) */
function RecipientPicker({ onPick }) {
  const [q, setQ] = useState("");
  const term = useDebounce(q.trim());
  const api = useApi(() => controlApi.recipients(term), [term], { skip: term.length < 2 });
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <Input placeholder="ابحث بالاسم أو الهاتف أو البريد…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="بحث عن عميل" />
      {api.data?.length === 0 && <span className="sub">لا توجد نتائج.</span>}
      {api.data?.map((u) => (
        <button key={u.id} type="button" className="abtn abtn-secondary" style={{ justifyContent: "space-between" }} onClick={() => onPick(u)}>
          <span>{u.name}</span>
          <span className="sub">{USER_ROLE[u.role]}</span>
        </button>
      ))}
    </div>
  );
}

function FilePicker({ files, setFiles }) {
  const ref = useRef(null);
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <input
        ref={ref}
        type="file"
        multiple
        hidden
        accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt"
        onChange={(e) => {
          setFiles([...files, ...e.target.files].slice(0, 3));
          e.target.value = "";
        }}
      />
      <div className="atts">
        {files.map((f, i) => (
          <span className="cc-att" key={i}>
            {f.name}
            <button type="button" aria-label="إزالة" onClick={() => setFiles(files.filter((_, j) => j !== i))} style={{ all: "unset", cursor: "pointer" }}>
              <X size={13} />
            </button>
          </span>
        ))}
        {files.length < 3 && (
          <button type="button" className="cc-att" onClick={() => ref.current.click()}>
            <Paperclip size={14} /> إرفاق ملف
          </button>
        )}
      </div>
      <span className="sub">حتى 3 ملفات، 5 ميجابايت للملف (صور، PDF، نص).</span>
    </div>
  );
}

function NewTicket({ preUser, onClose }) {
  const nav = useNavigate();
  const cats = useApi(() => controlApi.categories(), []);
  const [form, setForm] = useState({ subject: "", description: "", category: "", kind: "ticket", priority: "medium", requester_kind: "parent", requester_name: "", requester_phone: "" });
  const [customer, setCustomer] = useState(null); // an account, or null = a person without an account (guardian / other)
  const [files, setFiles] = useState([]);
  const [errs, setErrs] = useState({});
  const [run, busy] = useAction();
  const pre = useApi(() => controlApi.user(preUser), [preUser], { skip: !preUser });
  useEffect(() => {
    if (pre.data) setCustomer({ id: pre.data.id, name: pre.data.name, role: pre.data.role });
  }, [pre.data]);
  const submit = () =>
    run(async () => {
      const bad = {};
      if (form.subject.trim().length < 3) bad.subject = "اكتب عنوانًا من 3 أحرف على الأقل.";
      if (form.description.trim().length < 5) bad.description = "اكتب وصفًا أوضح للمشكلة.";
      if (!form.category) bad.category = "اختر تصنيفًا.";
      if (!customer && !form.requester_name.trim()) bad.requester_name = "اختر عميلًا أو اكتب اسمه.";
      setErrs(bad);
      if (Object.keys(bad).length) return false;
      const body = { ...form, category: Number(form.category) || "" };
      if (customer) {
        body.requester_user = customer.id;
        delete body.requester_name;
        delete body.requester_phone;
        delete body.requester_kind;
      }
      try {
        const t = await controlApi.createTicket(body, files);
        onClose();
        nav(`/team/support/tickets/${t.id}`);
      } catch (e) {
        setErrs(fieldErrors(e));
        throw e;
      }
    }, "تم إنشاء التذكرة");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <Modal
      size="lg"
      title="تذكرة جديدة نيابةً عن عميل"
      text="للحالات التي يتواصل فيها العميل هاتفيًا أو شخصيًا، وللأولياء الذين لا يملكون حسابًا."
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>إلغاء</Btn>
          <Btn loading={busy} loadingText="جارٍ الإنشاء…" onClick={submit}>إنشاء التذكرة</Btn>
        </>
      }
    >
      <div style={{ display: "grid", gap: 10 }}>
        <div className="cc-field">
          <span>العميل</span>
          {customer ? (
            <div className="cc-actions">
              <Badge tone="info">{customer.name} · {USER_ROLE[customer.role]}</Badge>
              <Btn variant="ghost" onClick={() => setCustomer(null)}>تغيير</Btn>
            </div>
          ) : (
            <RecipientPicker onPick={(u) => setCustomer(u)} />
          )}
        </div>
        {!customer && (
          <div className="cc-grid c2">
            <Field label="اسم العميل (بدون حساب)" error={errs.requester_name}><TextInput value={form.requester_name} onChange={set("requester_name")} placeholder="مثال: ولي أمر الطالب أحمد" /></Field>
            <Field label="هاتف العميل" error={errs.requester_phone}><TextInput ltr value={form.requester_phone} onChange={set("requester_phone")} /></Field>
            <Field label="نوع العميل"><Select all={null} value={form.requester_kind} onChange={(v) => setForm({ ...form, requester_kind: v })} options={[{ value: "parent", label: "ولي أمر" }, { value: "other", label: "آخر" }]} /></Field>
          </div>
        )}
        <Field label="الموضوع" required error={errs.subject}><TextInput value={form.subject} onChange={set("subject")} maxLength={200} /></Field>
        <Field label="الوصف" required error={errs.description}><TextArea rows={4} value={form.description} onChange={set("description")} maxLength={5000} /></Field>
        <div className="cc-grid c3">
          <Field label="التصنيف" required error={errs.category}>
            <Select all="اختر…" value={form.category} onChange={(v) => setForm({ ...form, category: v })} options={(cats.data || []).filter((c) => c.is_active).map((c) => ({ value: c.id, label: c.name }))} />
          </Field>
          <Field label="الأولوية"><Select all={null} value={form.priority} onChange={(v) => setForm({ ...form, priority: v })} options={PRIORITY_OPTS} /></Field>
          <Field label="النوع"><Select all={null} value={form.kind} onChange={(v) => setForm({ ...form, kind: v })} options={[{ value: "ticket", label: "تذكرة" }, { value: "complaint", label: "شكوى" }]} /></Field>
        </div>
        <FilePicker files={files} setFiles={setFiles} />
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ ticket list */
const MODE = {
  all: ["كل التذاكر", "كل التذاكر والشكاوى مع البحث والتصفية.", {}],
  mine: ["تذاكري", "التذاكر المسندة إليك.", { mine: "1" }],
  unassigned: ["التذاكر غير المسندة", "تذاكر نشطة لا يملكها أحد.", { unassigned: "1" }],
  complaints: ["الشكاوى", "التذاكر المصنّفة كشكاوى.", { kind: "complaint" }],
};

function AssignDialog({ ids, onClose, onDone }) {
  const agents = useApi(() => controlApi.agents(), []);
  const [agent, setAgent] = useState("");
  const toast = useToast();
  return (
    <Confirm
      title={ids.length > 1 ? `إسناد ${num(ids.length)} تذاكر` : "إسناد التذكرة"}
      text="اختر موظفًا. يظهر عبء عمله الحالي لتجنّب إرهاق أحد."
      confirmLabel="إسناد"
      onClose={onClose}
      onConfirm={async () => {
        if (!agent) {
          toast("اختر موظفًا أولًا.", "err");
          return false;
        }
        try {
          const r = await controlApi.bulkTickets({ ids, action: "assign", value: Number(agent) });
          toast(r.failed ? `أُسندت ${num(r.ok)} وتعذّرت ${num(r.failed)}` : `أُسندت ${num(r.ok)} تذكرة`, r.failed && !r.ok ? "err" : "ok");
          onDone();
        } catch (e) {
          toast(errText(e), "err");
          return false;
        }
      }}
    >
      {agents.error ? <p>{errText(agents.error)}</p> : (
        <Select
          all="— اختر —"
          value={agent}
          onChange={setAgent}
          options={(agents.data || []).map((a) => ({ value: a.id, label: `${a.name} — ${num(a.active)} نشطة${a.overloaded ? " (مزدحم)" : ""}` }))}
        />
      )}
    </Confirm>
  );
}

/** Re-mounts when the filters carried in the URL change (e.g. a KPI link), but not when only the "new ticket" dialog toggles. */
export function TicketsPage(props) {
  const loc = useLocation();
  const q = new URLSearchParams(loc.search);
  q.delete("new");
  return <TicketsInner key={props.mode + q.toString()} {...props} />;
}

function TicketsInner({ mode = "all" }) {
  const nav = useNavigate();
  const can = useCan();
  const toast = useToast();
  const [sp, setSp] = useSearchParams();
  const [title, desc, base] = MODE[mode];
  const [f, set, setPage] = useFilters({ search: "", status: sp.get("status") || "", priority: sp.get("priority") || "", category: "", assignee: sp.get("assignee") || "", overdue: sp.get("overdue") || "", response: sp.get("response") || "", active: sp.get("active") || "", requester_kind: "", created_from: "", created_to: "" });
  const [sort, toggle, sortParam] = useSort({ key: "updated_at", dir: "desc" });
  const search = useDebounce(f.search);
  const params = { ...f, ...base, search, sort: sortParam };
  const api = useApi(() => controlApi.tickets(params), [mode, JSON.stringify(params)]);
  const cats = useApi(() => controlApi.categories(), []);
  const [selected, setSelected] = useState([]);
  const [dialog, setDialog] = useState(null);
  const [prio, setPrio] = useState("");
  const newParam = sp.get("new");
  useEffect(() => {
    setSelected([]);
  }, [mode, JSON.stringify(params)]);

  const bulk = async (body, label) => {
    try {
      const r = await controlApi.bulkTickets({ ids: selected, ...body });
      toast(r.failed ? `${label}: نجح ${num(r.ok)} وتعذّر ${num(r.failed)}` : `${label}: ${num(r.ok)} تذكرة`, r.failed && !r.ok ? "err" : "ok");
      setSelected([]);
      api.reload();
    } catch (e) {
      toast(errText(e), "err");
    }
  };
  const closeNew = () => {
    sp.delete("new");
    setSp(sp, { replace: true });
  };

  return (
    <>
      <PageHead title={title} desc={desc} crumbs={[{ label: "الدعم" }, { label: title }]}>
        {can("reports.view") && (
          <Btn variant="secondary" onClick={() => controlApi.exportTickets({ ...params, page: undefined }).catch((e) => toast(errText(e), "err"))}>
            <Download size={15} /> تصدير CSV
          </Btn>
        )}
        {can("tickets.create") && (
          <Btn onClick={() => setSp({ new: "1" })}>
            <MessageSquarePlus size={16} /> تذكرة جديدة
          </Btn>
        )}
      </PageHead>
      <Card pad={false}>
        <div className="cc-tools">
          <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="رقم التذكرة، الموضوع أو العميل…" />
          <Select label="الحالة" value={f.status} onChange={(v) => set({ status: v })} options={STATUS_OPTS} />
          <Select label="الأولوية" value={f.priority} onChange={(v) => set({ priority: v })} options={PRIORITY_OPTS} />
          <Select label="التصنيف" value={f.category} onChange={(v) => set({ category: v })} options={(cats.data || []).map((c) => ({ value: c.id, label: c.name }))} />
          <Select label="نوع العميل" value={f.requester_kind} onChange={(v) => set({ requester_kind: v })} options={[{ value: "teacher", label: "معلّم" }, { value: "student", label: "طالب" }, { value: "parent", label: "ولي أمر" }, { value: "other", label: "آخر" }]} />
          <Select label="خيارات" value={f.overdue ? "overdue" : f.response ? "response" : f.active ? "active" : ""} onChange={(v) => set({ overdue: v === "overdue" ? "1" : "", response: v === "response" ? "awaiting_team" : "", active: v === "active" ? "1" : "" })} options={[{ value: "overdue", label: "المتأخرة فقط" }, { value: "response", label: "تنتظر ردّ الفريق" }, { value: "active", label: "النشطة فقط" }]} />
          <label className="cc-field"><span>من تاريخ</span><input type="date" className="cc-input" value={f.created_from} onChange={(e) => set({ created_from: e.target.value })} /></label>
          <label className="cc-field"><span>إلى تاريخ</span><input type="date" className="cc-input" value={f.created_to} onChange={(e) => set({ created_to: e.target.value })} /></label>
        </div>
        {selected.length > 0 && (
          <div className="bulkbar" role="region" aria-label="إجراءات جماعية">
            <b>{num(selected.length)} محدّدة</b>
            {can("tickets.assign", "tickets.reply") && <Btn variant="secondary" onClick={() => setDialog("assign")}>إسناد…</Btn>}
            {can("tickets.priority") && (
              <>
                <Select all="تغيير الأولوية إلى…" value={prio} onChange={(v) => v && bulk({ action: "priority", value: v }, "تغيير الأولوية")} options={PRIORITY_OPTS} />
              </>
            )}
            {can("tickets.resolve") && <Btn variant="secondary" onClick={() => setDialog("resolve")}>تعيين «تم الحل»</Btn>}
            <Btn variant="ghost" onClick={() => setSelected([])}>إلغاء التحديد</Btn>
          </div>
        )}
        <Async api={api}>
          {(d) => (
            <>
              <DataTable
                rows={d.results}
                sort={sort}
                onSort={toggle}
                onRow={(t) => nav(`/team/support/tickets/${t.id}`)}
                selected={selected}
                onSelect={can("tickets.assign", "tickets.priority", "tickets.resolve") ? setSelected : undefined}
                empty={<EmptyState title="لا توجد تذاكر مطابقة" text="غيّر عوامل التصفية أو ابحث بكلمة أخرى." />}
                columns={[
                  { key: "number", label: "الرقم", sort: "id", render: (t) => <span className="strong ltr">{t.number}</span> },
                  { key: "subject", label: "الموضوع", render: (t) => (<><div className="strong">{t.subject}</div>{t.kind === "complaint" && <Badge tone="warn">شكوى</Badge>} {t.overdue && <Badge tone="bad">متأخرة</Badge>}</>) },
                  { key: "requester", label: "العميل", render: (t) => (<><div>{t.requester.name || "—"}</div><div className="sub">{USER_ROLE[t.requester.kind]}</div></>) },
                  { key: "category", label: "التصنيف", render: (t) => t.category.name },
                  { key: "priority", label: "الأولوية", sort: "priority", render: (t) => <PriorityBadge value={t.priority} labels={PRIORITY} /> },
                  { key: "status", label: "الحالة", sort: "status", render: (t) => <StatusBadge map={TICKET_STATUS} value={t.status} /> },
                  { key: "assignee", label: "المسند إليه", render: (t) => t.assignee?.name || <span className="sub">غير مسندة</span> },
                  { key: "response", label: "الرد", render: (t) => <StatusBadge map={RESPONSE} value={t.response_status} /> },
                  { key: "created_at", label: "الإنشاء", sort: "created_at", render: (t) => dt(t.created_at) },
                  { key: "updated_at", label: "آخر تحديث", sort: "updated_at", render: (t) => ago(t.updated_at) },
                ]}
              />
              <Pager page={d.page} pages={d.pages} count={d.count} onPage={setPage} />
            </>
          )}
        </Async>
      </Card>
      {dialog === "assign" && <AssignDialog ids={selected} onClose={() => setDialog(null)} onDone={() => { setSelected([]); api.reload(); }} />}
      {dialog === "resolve" && (
        <Confirm title={`تعيين ${num(selected.length)} تذكرة كمحلولة`} text="ستنتقل التذاكر المؤهلة إلى «تم الحل». التي لا يسمح مسارها بذلك ستُذكر كفاشلة." confirmLabel="تأكيد" onClose={() => setDialog(null)} onConfirm={() => bulk({ action: "status", value: "resolved" }, "الحل")} />
      )}
      {newParam && <NewTicket preUser={newParam !== "1" ? newParam : null} onClose={closeNew} />}
    </>
  );
}

/* ------------------------------------------------------------------ ticket detail */
function Conversation({ messages, onDownload }) {
  const endRef = useRef(null);
  useEffect(() => {
    // braces matter: scrollIntoView returns a Promise in current Chromium, and an effect must return nothing or a cleanup function
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages.length]);
  return (
    <div className="convo">
      {messages.map((m) => (
        <article key={m.id} className={"cc-msg " + m.kind}>
          <div className="who">
            <b>{m.author || "—"}</b>
            <span>{m.kind === "customer" ? "العميل" : m.kind === "agent" ? "الفريق" : "ملاحظة داخلية — لا يراها العميل"}</span>
            <span>{dt(m.created_at)}</span>
          </div>
          <div className="body">{m.body}</div>
          {m.attachments.length > 0 && (
            <div className="atts">
              {m.attachments.map((a) => (
                <button key={a.id} type="button" className="cc-att" onClick={() => onDownload(a)}>
                  <Paperclip size={13} /> {a.name} <span className="sub"><bdi dir="ltr">{Math.max(1, Math.round(a.size / 1024))} KB</bdi></span>
                </button>
              ))}
            </div>
          )}
        </article>
      ))}
      <div ref={endRef} />
    </div>
  );
}

function Composer({ ticket, onSent }) {
  const can = useCan();
  const [body, setBody] = useState("");
  const [mode, setMode] = useState("reply");
  const [files, setFiles] = useState([]);
  const [run, busy] = useAction();
  const closed = ["resolved", "closed"].includes(ticket.status);
  if (!can("tickets.reply")) return <div className="composer"><span className="sub">لا تملك صلاحية الرد على التذاكر.</span></div>;
  if (closed && mode !== "note") {
    return (
      <div className="composer">
        <span className="sub">التذكرة {ticket.status === "closed" ? "مغلقة" : "محلولة"}. أعد فتحها للرد على العميل، أو أضف ملاحظة داخلية.</span>
        <div><Btn variant="secondary" onClick={() => setMode("note")}><Lock size={14} /> ملاحظة داخلية</Btn></div>
      </div>
    );
  }
  const send = () =>
    run(async () => {
      if (!body.trim()) throw new Error("اكتب نص الرسالة أولًا.");
      const t = await controlApi.replyTicket(ticket.id, { body, kind: mode }, files);
      setBody("");
      setFiles([]);
      onSent(t);
    }, mode === "note" ? "أُضيفت الملاحظة الداخلية" : mode === "request_info" ? "أُرسل الطلب وبانتظار العميل" : "أُرسل الرد");
  return (
    <div className="composer">
      <div className="cc-seg" role="tablist" aria-label="نوع الرسالة" style={{ width: "fit-content", maxWidth: "100%", overflowX: "auto" }}>
        {[["reply", "رد على العميل"], ["request_info", "طلب معلومات إضافية"], ["note", "ملاحظة داخلية"]].map(([k, l]) => (
          <button key={k} className={mode === k ? "on" : ""} onClick={() => setMode(k)} disabled={closed && k !== "note"}>{l}</button>
        ))}
      </div>
      {mode === "note" && <p className="sub"><Lock size={12} /> لن يراها العميل أبدًا.</p>}
      <TextArea value={body} onChange={(e) => setBody(e.target.value)} rows={4} maxLength={5000} placeholder={mode === "note" ? "ملاحظة للفريق…" : "اكتب ردك…"} aria-label="نص الرسالة" />
      <FilePicker files={files} setFiles={setFiles} />
      <div><Btn loading={busy} loadingText="جارٍ الإرسال…" onClick={send}><Send size={15} /> {mode === "note" ? "حفظ الملاحظة" : "إرسال"}</Btn></div>
    </div>
  );
}

export function TicketDetailPage() {
  const { id } = useParams();
  const can = useCan();
  const { me } = useControl();
  const toast = useToast();
  const api = useApi(() => controlApi.ticket(id), [id]);
  const cats = useApi(() => controlApi.categories(), []);
  const [local, setLocal] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [run, busy] = useAction();
  const t = local && local.id === Number(id) ? local : api.data;
  const [statusNote, setStatusNote] = useState("");
  if (api.error && !api.data) return <ErrorState error={api.error} onRetry={api.reload} />;
  if (!t) return <Skeleton rows={8} />;

  const doStatus = (status, ok) => run(async () => setLocal(await controlApi.setTicketStatus(t.id, status, statusNote.trim())), ok).then(() => setStatusNote(""));
  const download = (a) => controlApi.downloadAttachment(a.id, a.name).catch((e) => toast(errText(e), "err"));
  const reopening = ["resolved", "closed"].includes(t.status);
  const c = t.customer;

  return (
    <>
      <PageHead title={`${t.number} · ${t.subject}`} desc={`${KIND[t.kind]} · أُنشئت ${dt(t.created_at)}`} crumbs={[{ label: "الدعم" }, { label: "كل التذاكر", to: "/team/support/tickets" }, { label: t.number }]}>
        <StatusBadge map={TICKET_STATUS} value={t.status} />
        <PriorityBadge value={t.priority} labels={PRIORITY} />
        {t.overdue && <Badge tone="bad">متأخرة</Badge>}
      </PageHead>
      <div className="ticket-layout">
        <div style={{ display: "grid", gap: 16, minWidth: 0 }}>
          <Card pad={false} title="المحادثة">
            <Conversation messages={t.messages} onDownload={download} />
            <Composer ticket={t} onSent={setLocal} />
          </Card>
          <Card title="سجل التذكرة" pad={false}>
            <div className="timeline">
              {t.history.map((e) => (
                <div className="ev" key={e.id}>
                  <span />
                  <div>
                    {e.text}
                    {(e.from || e.to) && e.kind !== "reply" && e.kind !== "note" ? (
                      <span className="sub"> — {labelOf(e.kind, e.from)}{e.from ? " ← " : ""}{labelOf(e.kind, e.to)}</span>
                    ) : null}
                    <div className="when">{e.actor ? `${e.actor} · ` : ""}{dt(e.at)}</div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div style={{ display: "grid", gap: 16 }}>
          <Card title="إجراءات">
            <div style={{ display: "grid", gap: 12 }}>
              <Field label="الحالة">
                <Select all={null} value={t.status} disabled={busy || !can("tickets.reply", "tickets.resolve")} onChange={(v) => v !== t.status && (v === "closed" ? setDialog({ close: v }) : doStatus(v, v === "resolved" ? "تم تعيين التذكرة كمحلولة" : "تم تحديث الحالة"))}
                  options={[{ value: t.status, label: TICKET_STATUS[t.status][0] }, ...t.allowed_statuses.map((s) => ({ value: s, label: (reopening && ["open", "in_progress"].includes(s) ? "إعادة فتح — " : "") + TICKET_STATUS[s][0] }))]} />
              </Field>
              {can("tickets.resolve") && !reopening && <Btn variant="secondary" loading={busy} onClick={() => setDialog({ resolve: true })}>حل التذكرة</Btn>}
              <Field label="الأولوية">
                <Select all={null} value={t.priority} disabled={busy || !can("tickets.priority")} onChange={(v) => v !== t.priority && run(async () => setLocal(await controlApi.setTicketPriority(t.id, v)), "تم تغيير الأولوية")} options={PRIORITY_OPTS} />
              </Field>
              <Field label="التصنيف">
                <Select all={null} value={t.category.id} disabled={busy || !can("tickets.reply")} onChange={(v) => Number(v) !== t.category.id && run(async () => setLocal(await controlApi.setTicketCategory(t.id, Number(v))), "تم تغيير التصنيف")} options={(cats.data || []).filter((x) => x.is_active || x.id === t.category.id).map((x) => ({ value: x.id, label: x.name }))} />
              </Field>
              <div className="cc-field">
                <span>المسند إليه</span>
                <div className="cc-actions"><b>{t.assignee?.name || "غير مسندة"}</b>
                  {can("tickets.assign") && <Btn variant="secondary" onClick={() => setDialog({ assign: true })}>{t.assignee ? "إعادة إسناد" : "إسناد"}</Btn>}
                  {!t.assignee && !can("tickets.assign") && can("tickets.reply") && <Btn variant="secondary" loading={busy} onClick={() => run(async () => setLocal(await controlApi.assignTicket(t.id, me.id)), "أصبحت التذكرة لك")}>استلام التذكرة</Btn>}
                </div>
              </div>
            </div>
          </Card>
          <Card title="العميل">
            <KV items={[
              ["الاسم", c.user_id ? <Link key="n" to={`/team/users/${c.user_id}`} style={{ textDecoration: "underline" }}>{c.name}</Link> : c.name],
              ["النوع", USER_ROLE[c.kind]],
              ["البريد", c.email ? <bdi dir="ltr" key="e">{c.email}</bdi> : "—"],
              ["الهاتف", c.phone ? <bdi dir="ltr" key="p">{c.phone}</bdi> : "—"],
              ["البيئة", c.environment ? <Link key="env" to={`/team/environments/${c.environment.id}`} style={{ textDecoration: "underline" }}>{c.environment.name}</Link> : "—"],
              c.account_status ? ["حالة الحساب", <StatusBadge key="as" map={ACCOUNT_STATUS} value={c.account_status} />] : null,
              c.total_tickets ? ["تذاكره", `${num(c.open_tickets)} مفتوحة من ${num(c.total_tickets)}`] : null,
            ]} />
          </Card>
          <Card title="التوقيتات">
            <KV items={[["التصنيف", t.category.name], ["الموعد النهائي للحل", dt(t.due_at)], ["أول رد", dt(t.first_response_at)], ["الحل", dt(t.resolved_at)], ["مرات إعادة الفتح", num(t.reopen_count)], t.rating ? ["تقييم العميل", `${t.rating}/5${t.rating_comment ? ` — ${t.rating_comment}` : ""}`] : null]} />
          </Card>
        </div>
      </div>

      {dialog?.resolve && (
        <Confirm title="حل التذكرة" text="سيُبلَّغ العميل بالحل ويستطيع تقييم الخدمة. يمكن إعادة الفتح لاحقًا." confirmLabel="تأكيد الحل" onClose={() => setDialog(null)} onConfirm={async () => { await doStatus("resolved", "تم حل التذكرة"); }}>
          <Field label="ملاحظة داخلية (اختيارية)"><TextArea rows={2} value={statusNote} onChange={(e) => setStatusNote(e.target.value)} /></Field>
        </Confirm>
      )}
      {dialog?.close && (
        <Confirm title="إغلاق التذكرة" text="التذكرة المغلقة لا يستطيع العميل الرد عليها إلا خلال المهلة المضبوطة في الإعدادات." confirmLabel="إغلاق" onClose={() => setDialog(null)} onConfirm={async () => { await doStatus("closed", "أُغلقت التذكرة"); }} />
      )}
      {dialog?.assign && <TicketAssign ticket={t} onClose={() => setDialog(null)} onDone={setLocal} />}
    </>
  );
}

const labelOf = (kind, v) => (kind === "status" || kind === "reopened" ? TICKET_STATUS[v]?.[0] : kind === "priority" ? PRIORITY[v] : v) || v || "—";

function TicketAssign({ ticket, onClose, onDone }) {
  const agents = useApi(() => controlApi.agents(), []);
  const [agent, setAgent] = useState(ticket.assignee?.id ? String(ticket.assignee.id) : "");
  const toast = useToast();
  return (
    <Confirm
      title="إسناد التذكرة"
      text="يظهر لكل موظف عدد تذاكره النشطة. تُسجَّل كل عملية إسناد في سجل التذكرة."
      confirmLabel="حفظ الإسناد"
      onClose={onClose}
      onConfirm={async () => {
        try {
          onDone(await controlApi.assignTicket(ticket.id, agent ? Number(agent) : null));
          toast("تم تحديث الإسناد");
        } catch (e) {
          toast(errText(e), "err");
          return false;
        }
      }}
    >
      <Select all="— إلغاء الإسناد —" value={agent} onChange={setAgent} options={(agents.data || []).map((a) => ({ value: a.id, label: `${a.name} — ${num(a.active)} نشطة${a.overloaded ? " (مزدحم)" : ""}` }))} />
    </Confirm>
  );
}

/* ------------------------------------------------------------------ categories */
export function CategoriesPage() {
  const can = useCan();
  const toast = useToast();
  const api = useApi(() => controlApi.categories(), []);
  const [edit, setEdit] = useState(undefined);
  const [remove, setRemove] = useState(null);
  return (
    <>
      <PageHead title="تصنيفات التذاكر" desc="يختار العميل تصنيفًا عند فتح التذكرة. التصنيف المعطّل لا يظهر للعملاء لكن تذاكره القديمة تبقى." crumbs={[{ label: "الدعم" }, { label: "التصنيفات" }]}>
        {can("tickets.categories") && <Btn onClick={() => setEdit(null)}><Plus size={16} /> تصنيف جديد</Btn>}
      </PageHead>
      <Card pad={false}>
        <Async api={api}>
          {(rows) => (
            <DataTable
              rows={rows}
              empty={<EmptyState title="لا توجد تصنيفات" />}
              columns={[
                { key: "name", label: "التصنيف", render: (c) => (<><div className="strong">{c.name}</div><div className="sub">{c.description}</div></>) },
                { key: "tickets", label: "التذاكر", render: (c) => num(c.tickets) },
                { key: "is_active", label: "الحالة", render: (c) => <Badge tone={c.is_active ? "ok" : "plain"}>{c.is_active ? "مفعّل" : "معطّل"}</Badge> },
                ...(can("tickets.categories")
                  ? [{
                      key: "act", label: "", render: (c) => (
                        <span className="cc-actions">
                          <Btn variant="secondary" onClick={() => setEdit(c)}>تعديل</Btn>
                          <Btn variant="ghost" onClick={async () => { try { await controlApi.updateCategory(c.id, { is_active: !c.is_active }); toast(c.is_active ? "عُطّل التصنيف" : "فُعّل التصنيف"); api.reload(); } catch (e) { toast(errText(e), "err"); } }}>{c.is_active ? "تعطيل" : "تفعيل"}</Btn>
                          <Btn variant="ghost" onClick={() => setRemove(c)} aria-label="حذف"><Trash2 size={14} /></Btn>
                        </span>
                      ),
                    }]
                  : []),
              ]}
            />
          )}
        </Async>
      </Card>
      {edit !== undefined && <CategoryForm cat={edit} onClose={() => setEdit(undefined)} onSaved={api.reload} />}
      {remove && (
        <Confirm danger title={`حذف «${remove.name}»`} text="لا يمكن حذف تصنيف يحتوي تذاكر؛ عطّله بدلًا من ذلك." confirmLabel="حذف" onClose={() => setRemove(null)}
          onConfirm={async () => { try { await controlApi.deleteCategory(remove.id); toast("حُذف التصنيف"); api.reload(); } catch (e) { toast(errText(e), "err"); return false; } }} />
      )}
    </>
  );
}
function CategoryForm({ cat, onClose, onSaved }) {
  const [form, setForm] = useState({ name: cat?.name || "", description: cat?.description || "" });
  const [errs, setErrs] = useState({});
  const [run, busy] = useAction();
  return (
    <Modal title={cat ? "تعديل التصنيف" : "تصنيف جديد"} onClose={onClose} footer={<><Btn variant="ghost" onClick={onClose}>إلغاء</Btn><Btn loading={busy} loadingText="جارٍ الحفظ…" onClick={() => run(async () => { if (form.name.trim().length < 2) { setErrs({ name: "اكتب اسم التصنيف." }); return false; } setErrs({}); try { await (cat ? controlApi.updateCategory(cat.id, form) : controlApi.createCategory(form)); onSaved(); onClose(); } catch (e) { setErrs(fieldErrors(e)); throw e; } }, "تم الحفظ")}>حفظ</Btn></>}>
      <div style={{ display: "grid", gap: 8 }}>
        <Field label="الاسم" required error={errs.name}><TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={80} /></Field>
        <Field label="وصف مختصر" error={errs.description}><TextInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={200} /></Field>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ analytics */
export function SupportAnalyticsPage() {
  const [range, setRange] = useState({ range: "30d" });
  const p = rangeParams(range);
  const api = useApi(() => controlApi.supportAnalytics(p), [JSON.stringify(p)]);
  return (
    <>
      <PageHead title="تحليلات الدعم" desc="كل الأرقام محسوبة من أحداث التذاكر الفعلية، لا من قيم ثابتة." crumbs={[{ label: "الدعم" }, { label: "التحليلات" }]}>
        <RangePicker value={range} onChange={setRange} />
      </PageHead>
      <Async api={api} rows={8}>
        {(d) => (
          <>
            <div className="cc-grid kpi">
              {[["تذاكر جديدة", num(d.created)], ["تذاكر محلولة", num(d.resolved)], ["نسبة الحل", d.resolution_rate === null ? "—" : `${num(d.resolution_rate)}%`], ["متوسط أول رد", hoursText(d.avg_response_hours)], ["متوسط زمن الحل", hoursText(d.avg_resolution_hours)], ["معدل إعادة الفتح", d.reopen_rate === null ? "—" : `${num(d.reopen_rate)}%`], ["متوسط رضا العملاء", d.satisfaction.average ? `${num(d.satisfaction.average)}/5` : "—"]].map(([k, v]) => (
                <div className="cc-card kpi" key={k}><div className="top"><span>{k}</span></div><div className="val">{v}</div></div>
              ))}
            </div>
            <div className="cc-grid c2">
              <ChartCard title="حجم التذاكر عبر الزمن" legend={[{ label: "جديدة", color: SERIES.c1 }, { label: "محلولة", color: SERIES.c3 }]} table={tableOf(["جديدة", "محلولة"], [{ points: d.volume.created }, { points: d.volume.resolved }])}>
                <LineChart series={toSeries([["جديدة", SERIES.c1, d.volume.created], ["محلولة", SERIES.c3, d.volume.resolved]])} />
              </ChartCard>
              <Card title="حسب التصنيف"><HBars rows={d.by_category.map((r) => ({ name: r.name, count: r.count }))} /></Card>
              <Card title="حسب الأولوية"><HBars rows={d.by_priority.map((r) => ({ name: PRIORITY[r.priority], count: r.count }))} /></Card>
              <Card title="أكثر الشكاوى تكرارًا" sub="تصنيفات الشكاوى فقط"><HBars rows={d.common_complaints.map((r) => ({ name: r.name, count: r.count }))} empty="لا شكاوى في هذه الفترة." /></Card>
            </div>
            <Card title="أداء الموظفين" sub="للتذاكر المنشأة في الفترة والمسندة لكل موظف" pad={false}>
              <DataTable rowKey="id" rows={d.agents} empty={<EmptyState title="لا توجد تذاكر مسندة في هذه الفترة" />} columns={[
                { key: "name", label: "الموظف", render: (a) => <span className="strong">{a.name}</span> },
                { key: "assigned", label: "المسندة", render: (a) => num(a.assigned) },
                { key: "resolved", label: "المحلولة", render: (a) => num(a.resolved) },
                { key: "avg_response_hours", label: "متوسط أول رد", render: (a) => hoursText(a.avg_response_hours) },
                { key: "avg_rating", label: "متوسط التقييم", render: (a) => (a.avg_rating ? `${num(a.avg_rating)}/5` : "—") },
              ]} />
            </Card>
            <Card title="عبء العمل الحالي" pad={false}>
              <DataTable rowKey="id" rows={d.workload} empty={<EmptyState title="لا يوجد موظفون" />} columns={[
                { key: "name", label: "الموظف" }, { key: "active", label: "نشطة", render: (a) => num(a.active) },
                { key: "overloaded", label: "الحالة", render: (a) => (a.overloaded ? <Badge tone="bad">مزدحم</Badge> : <Badge tone="ok">طبيعي</Badge>) },
              ]} />
            </Card>
            <div className="cc-grid c2">
              <Card title="رضا العملاء" sub={`${num(d.satisfaction.count)} تقييم في الفترة`}>
                <HBars rows={[5, 4, 3, 2, 1].map((s) => ({ name: `${s} ${"★".repeat(s)}`, count: d.satisfaction.distribution[s] }))} />
              </Card>
              <Card title="أسباب عدم الرضا" sub="تعليقات التقييمات المنخفضة (1-2)">
                {d.satisfaction.low_rating_feedback.length === 0 ? <p className="sub">لا توجد تعليقات منخفضة.</p> : (
                  <div style={{ display: "grid", gap: 8 }}>{d.satisfaction.low_rating_feedback.map((f, i) => (<div key={i} style={{ fontSize: "0.86rem" }}><b>{f.ticket}</b> · {f.category} · {f.rating}/5<div className="sub">{f.comment}</div></div>))}</div>
                )}
              </Card>
            </div>
          </>
        )}
      </Async>
    </>
  );
}
