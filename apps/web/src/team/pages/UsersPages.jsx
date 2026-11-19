import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Pencil, ShieldOff, ShieldCheck, TicketPlus } from "lucide-react";
import { Btn, Field, Modal, TextInput } from "../../auth/ui.jsx";
import { controlApi } from "../../lib/controlApi.js";
import { ACCOUNT_STATUS, AI_KIND, AUDIT_ACTIONS, DELIVERY, ENTITY, PRIORITY, TICKET_STATUS, USER_ROLE } from "../labels.js";
import {
  Async,
  Badge,
  Card,
  Confirm,
  DataTable,
  EmptyState,
  ErrorState,
  KV,
  PageHead,
  Pager,
  PriorityBadge,
  SearchBox,
  Select,
  Skeleton,
  StatusBadge,
  Tabs,
  TextArea,
  ago,
  dt,
  errText,
  fieldErrors,
  num,
  opts,
  useAction,
  useApi,
  useCan,
  useDebounce,
  useFilters,
  useToast,
  useSort,
} from "../kit.jsx";

const STATUS_OPTS = [
  { value: "active", label: "نشط" },
  { value: "suspended", label: "موقوف" },
  { value: "pending", label: "بانتظار التفعيل" },
];
const TITLES = {
  all: ["كل المستخدمين", "المعلّمون والطلاب المسجّلون على المنصة. حسابات الفريق وأولياء الأمور لها صفحاتها الخاصة."],
  teachers: ["المعلّمون", "حسابات المعلّمين وبيئاتهم وأعداد طلابهم."],
  students: ["الطلاب", "حسابات الطلاب والمعلّم والبيئة المرتبطة بكل طالب."],
};

export function UsersPage({ kind }) {
  const nav = useNavigate();
  const [f, set, setPage] = useFilters({ search: "", role: kind === "teachers" ? "teacher" : kind === "students" ? "student" : "", status: "", joined_from: "", joined_to: "", active_from: "" });
  const [sort, toggle, sortParam] = useSort({ key: "date_joined", dir: "desc" });
  const search = useDebounce(f.search);
  const params = { ...f, search, sort: sortParam };
  const call = kind === "teachers" ? controlApi.teachers : kind === "students" ? controlApi.students : controlApi.users;
  const api = useApi(() => call(params), [kind, JSON.stringify(params)]);
  const [title, desc] = TITLES[kind];

  const cols = [
    { key: "id", label: "المعرّف", sort: "id", className: "cc-num" },
    {
      key: "name",
      label: "الاسم",
      sort: "name",
      render: (u) => (
        <>
          <div className="strong">{u.name || "—"}</div>
          <div className="sub ltr">{u.email || ""}</div>
        </>
      ),
    },
    { key: "phone", label: "الهاتف", ltr: true, render: (u) => u.phone || "—" },
    ...(kind === "all" ? [{ key: "role", label: "النوع", render: (u) => USER_ROLE[u.role] }] : []),
    ...(kind === "teachers"
      ? [
          { key: "student_count", label: "الطلاب", render: (u) => num(u.student_count) },
          { key: "group_count", label: "المجموعات", render: (u) => num(u.group_count) },
        ]
      : []),
    ...(kind === "students"
      ? [
          { key: "teacher", label: "المعلّم", render: (u) => [...new Set(u.enrollments.map((e) => e.teacher))].join("، ") || "—" },
          { key: "enr", label: "التسجيل", render: (u) => (u.enrollments.length ? (u.active_enrollments ? <Badge tone="ok">نشط</Badge> : <Badge tone="warn">غير نشط</Badge>) : "—") },
        ]
      : []),
    { key: "environment", label: "البيئة", render: (u) => (u.environment ? u.environments.map((e) => e.name).join("، ") : "—") },
    { key: "status", label: "الحالة", render: (u) => <StatusBadge map={ACCOUNT_STATUS} value={u.status} /> },
    { key: "date_joined", label: "التسجيل", sort: "date_joined", render: (u) => dt(u.date_joined) },
    { key: "last_activity", label: "آخر نشاط", sort: "last_activity", render: (u) => ago(u.last_activity) },
  ];

  return (
    <>
      <PageHead title={title} desc={desc} crumbs={[{ label: "الإدارة" }, { label: title }]} />
      <Card pad={false}>
        <div className="cc-tools">
          <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="اسم، بريد، هاتف أو معرّف…" />
          {kind === "all" && <Select label="النوع" value={f.role} onChange={(v) => set({ role: v })} options={[{ value: "teacher", label: "معلّم" }, { value: "student", label: "طالب" }]} />}
          <Select label="الحالة" value={f.status} onChange={(v) => set({ status: v })} options={STATUS_OPTS} />
          <label className="cc-field">
            <span>سُجّل من</span>
            <input type="date" className="cc-input" value={f.joined_from} onChange={(e) => set({ joined_from: e.target.value })} />
          </label>
          <label className="cc-field">
            <span>سُجّل حتى</span>
            <input type="date" className="cc-input" value={f.joined_to} onChange={(e) => set({ joined_to: e.target.value })} />
          </label>
          <label className="cc-field">
            <span>نشط منذ</span>
            <input type="date" className="cc-input" value={f.active_from} onChange={(e) => set({ active_from: e.target.value })} />
          </label>
        </div>
        <Async api={api}>
          {(d) => (
            <>
              <DataTable
                columns={cols}
                rows={d.results}
                sort={sort}
                onSort={toggle}
                onRow={(u) => nav(`/team/users/${u.id}`)}
                empty={<EmptyState title="لا يوجد مستخدمون مطابقون" text="جرّب تغيير عوامل التصفية أو البحث." />}
              />
              <Pager page={d.page} pages={d.pages} count={d.count} onPage={setPage} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------------ user detail */
function EditUser({ user, onClose, onSaved }) {
  const [form, setForm] = useState({ name: user.name || "", email: user.email || "", phone: user.phone || "" });
  const [errs, setErrs] = useState({});
  const [run, busy] = useAction();
  const save = async () => {
    if (form.name.trim().length < 2) {
      setErrs({ name: "الاسم يجب ألا يقل عن حرفين." });
      return;
    }
    setErrs({});
    const body = {};
    for (const k of ["name", "email", "phone"]) if ((form[k] || "") !== (user[k] || "")) body[k] = form[k];
    if (!Object.keys(body).length) return onClose();
    try {
      await run(async () => {
        try {
          const r = await controlApi.updateUser(user.id, body);
          onSaved(r);
          onClose();
        } catch (e) {
          setErrs(fieldErrors(e));
          throw e;
        }
      }, "تم حفظ التعديلات");
    } catch {
      /* shown via toast + field errors */
    }
  };
  return (
    <Modal
      title="تعديل بيانات المستخدم"
      text="تغيير البريد أو الهاتف يغيّر وسيلة دخول المستخدم. يُسجَّل هذا التعديل في سجل التدقيق."
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            إلغاء
          </Btn>
          <Btn loading={busy} loadingText="جارٍ الحفظ…" onClick={save}>
            حفظ
          </Btn>
        </>
      }
    >
      <div style={{ display: "grid", gap: 8 }}>
        <Field label="الاسم" required error={errs.name}>
          <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={150} />
        </Field>
        <Field label="البريد الإلكتروني" error={errs.email}>
          <TextInput ltr type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label="رقم الهاتف (مع رمز الدولة)" error={errs.phone}>
          <TextInput ltr value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        </Field>
      </div>
    </Modal>
  );
}

function SuspendDialog({ user, restore, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const toast = useToast();
  return (
    <Confirm
      title={restore ? "إعادة تفعيل الحساب" : "إيقاف الحساب"}
      text={restore ? `سيتمكّن ${user.name} من الدخول مرة أخرى.` : `سيُسجَّل خروج ${user.name} من كل أجهزته فورًا ولن يستطيع الدخول حتى تعيد تفعيله.`}
      confirmLabel={restore ? "إعادة التفعيل" : "إيقاف الحساب"}
      danger={!restore}
      onClose={onClose}
      onConfirm={async () => {
        try {
          const r = await (restore ? controlApi.restoreUser : controlApi.suspendUser)(user.id, reason.trim());
          onDone(r);
          toast(restore ? "أُعيد تفعيل الحساب" : "أُوقف الحساب وسُجّل خروجه");
        } catch (e) {
          toast(errText(e), "err");
          return false;
        }
      }}
    >
      <Field label="السبب (اختياري، يُحفظ في سجل التدقيق)">
        <TextArea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} rows={3} />
      </Field>
    </Confirm>
  );
}

export function UserDetailPage() {
  const { id } = useParams();
  const can = useCan();
  const [tab, setTab] = useState("overview");
  const [dialog, setDialog] = useState(null);
  const api = useApi(() => controlApi.user(id), [id]);
  const [local, setLocal] = useState(null);
  const u = local && local.id === Number(id) ? local : api.data;

  const tabs = [
    { key: "overview", label: "نظرة عامة" },
    { key: "personal", label: "البيانات الشخصية" },
    { key: "account", label: "بيانات الحساب" },
    { key: "env", label: "البيئة" },
    { key: "activity", label: "سجل النشاط" },
    ...(can("tickets.view") ? [{ key: "tickets", label: "التذاكر" }] : []),
    ...(can("notifications.view", "users.view") ? [{ key: "notifications", label: "الإشعارات" }] : []),
    ...(can("audit.view") ? [{ key: "history", label: "السجل الإداري" }] : []),
  ];

  if (api.error && !api.data) return <ErrorState error={api.error} onRetry={api.reload} />;
  if (!u) return <Skeleton rows={8} />;
  const roleLabel = USER_ROLE[u.role];
  return (
    <>
      <PageHead
        title={u.name || "مستخدم"}
        desc={`${roleLabel} · رقم ${u.id}`}
        crumbs={[{ label: "الإدارة" }, { label: "المستخدمون", to: "/team/users" }, { label: u.name || `#${u.id}` }]}
      >
        <StatusBadge map={ACCOUNT_STATUS} value={u.status} />
        {can("users.edit") && (
          <Btn variant="secondary" onClick={() => setDialog("edit")}>
            <Pencil size={15} /> تعديل
          </Btn>
        )}
        {can("tickets.create") && (
          <Link className="abtn abtn-secondary" to={`/team/support/tickets?new=${u.id}`}>
            <TicketPlus size={15} /> تذكرة جديدة
          </Link>
        )}
        {can("users.suspend") && u.status === "active" && (
          <Btn variant="danger" onClick={() => setDialog("suspend")}>
            <ShieldOff size={15} /> إيقاف الحساب
          </Btn>
        )}
        {can("users.suspend") && u.status === "suspended" && (
          <Btn onClick={() => setDialog("restore")}>
            <ShieldCheck size={15} /> إعادة التفعيل
          </Btn>
        )}
      </PageHead>

      <Card pad={false}>
        <Tabs tabs={tabs} value={tab} onChange={setTab} />
        <div className="pad">
          {tab === "overview" && (
            <div className="cc-grid c3">
              <Card title="الحالة"><div style={{ display: "grid", gap: 8 }}><StatusBadge map={ACCOUNT_STATUS} value={u.status} /><span className="sub">آخر نشاط: {ago(u.last_activity)}</span></div></Card>
              <Card title="الدعم"><KV items={[["تذاكر مفتوحة", num(u.open_tickets)], ["إجمالي التذاكر", num(u.total_tickets)]]} /></Card>
              <Card title="الاستخدام"><KV items={[["عمليات الذكاء الاصطناعي", num(u.ai_operations_count)], ["الإشعارات المستلمة", num(u.notifications_count)]]} /></Card>
              {u.teacher && (
                <Card title="نشاط المعلّم" className="">
                  <KV items={[["طلاب نشطون", num(u.teacher.students_active)], ["إجمالي الطلاب", num(u.teacher.students_total)], ["المجموعات", num(u.teacher.groups)], ["المواعيد", num(u.teacher.schedules)], ["جلسات (30 يومًا)", num(u.teacher.sessions_30d)], ["سجلات حضور (30 يومًا)", num(u.teacher.attendance_records_30d)], ["تقييمات (30 يومًا)", num(u.teacher.evaluations_30d)]]} />
                </Card>
              )}
            </div>
          )}
          {tab === "personal" && <KV items={[["الاسم", u.name], ["البريد الإلكتروني", <bdi dir="ltr" key="e">{u.email || "—"}</bdi>], ["الهاتف", <bdi dir="ltr" key="p">{u.phone || "—"}</bdi>], ["النوع", roleLabel]]} />}
          {tab === "account" && (
            <KV items={[["المعرّف", u.id], ["الحالة", <StatusBadge key="s" map={ACCOUNT_STATUS} value={u.status} />], ["تم التحقق من الهوية (OTP)", u.is_verified ? "نعم" : "لا"], ["تاريخ التسجيل", dt(u.date_joined)], ["آخر تسجيل دخول", dt(u.last_login)], ["آخر نشاط", dt(u.last_activity)]]} />
          )}
          {tab === "env" && <EnvTab u={u} />}
          {tab === "activity" && <ActivityTab id={u.id} />}
          {tab === "tickets" && <UserTickets id={u.id} />}
          {tab === "notifications" && <UserNotifications id={u.id} />}
          {tab === "history" && <UserHistory id={u.id} />}
        </div>
      </Card>

      {dialog === "edit" && <EditUser user={u} onClose={() => setDialog(null)} onSaved={(r) => setLocal(r)} />}
      {(dialog === "suspend" || dialog === "restore") && (
        <SuspendDialog
          user={u}
          restore={dialog === "restore"}
          onClose={() => setDialog(null)}
          onDone={(r) => setLocal(r)}
        />
      )}
    </>
  );
}

function EnvTab({ u }) {
  if (u.teacher) {
    const e = u.teacher.environment;
    return (
      <KV items={[["البيئة", <Link key="l" to={`/team/environments/${e.id}`} style={{ color: "var(--navy)", textDecoration: "underline" }}>{e.name}</Link>], ["المادة / المرحلة", e.subject_stage], ["العام الدراسي", e.academic_year], ["تاريخ الإنشاء", dt(e.created_at)]]} />
    );
  }
  if (u.student) {
    if (!u.student.length) return <EmptyState title="غير مسجّل لدى أي معلّم" />;
    return (
      <div style={{ display: "grid", gap: 14 }}>
        {u.student.map((s) => (
          <Card key={s.environment.id} title={s.environment.name} sub={`المعلّم: ${s.teacher}`}>
            <KV
              items={[
                ["الصف", s.grade],
                ["العام الدراسي", s.academic_year],
                ["حالة التسجيل", <Badge key="a" tone={s.is_active ? "ok" : "warn"}>{s.is_active ? "نشط" : "غير نشط"}</Badge>],
                ["تاريخ التسجيل", dt(s.enrolled_at)],
                ["المجموعات", s.groups.join("، ") || "—"],
                ["الحضور", `حاضر ${num(s.attendance.present || 0)} · غائب ${num(s.attendance.absent || 0)}`],
                ["التقييمات الشهرية", s.ratings.map((r) => `${r.month.slice(0, 7)}: ${r.value}/5`).join("، ") || "—"],
                ["حالة الطالب الشهرية", s.states.map((x) => `${x.month.slice(0, 7)}: ${x.state}`).join("، ") || "—"],
                s.guardian ? ["ولي الأمر", `${s.guardian.name || "—"} · ${s.guardian.phone || "—"}`] : null,
              ]}
            />
          </Card>
        ))}
      </div>
    );
  }
  return <EmptyState title="لا توجد بيئة مرتبطة" />;
}

function ActivityTab({ id }) {
  const api = useApi(() => controlApi.userActivity(id), [id]);
  return (
    <Async api={api}>
      {(rows) =>
        rows.length === 0 ? (
          <EmptyState title="لا يوجد نشاط مسجّل" />
        ) : (
          <div className="timeline" style={{ padding: 0 }}>
            {rows.map((r, i) => (
              <div className="ev" key={i}>
                <span />
                <div>
                  {r.ticket_id ? <Link to={`/team/support/tickets/${r.ticket_id}`} style={{ textDecoration: "underline" }}>{r.text}</Link> : r.text}
                  <div className="when">{dt(r.at)}</div>
                </div>
              </div>
            ))}
          </div>
        )
      }
    </Async>
  );
}

function UserTickets({ id }) {
  const nav = useNavigate();
  const api = useApi(() => controlApi.userTickets(id), [id]);
  return (
    <Async api={api}>
      {(rows) => (
        <DataTable
          rows={rows}
          onRow={(t) => nav(`/team/support/tickets/${t.id}`)}
          empty={<EmptyState title="لا توجد تذاكر لهذا المستخدم" />}
          columns={[
            { key: "number", label: "الرقم" },
            { key: "subject", label: "الموضوع" },
            { key: "priority", label: "الأولوية", render: (t) => <PriorityBadge value={t.priority} labels={PRIORITY} /> },
            { key: "status", label: "الحالة", render: (t) => <StatusBadge map={TICKET_STATUS} value={t.status} /> },
            { key: "created_at", label: "التاريخ", render: (t) => dt(t.created_at) },
          ]}
        />
      )}
    </Async>
  );
}

function UserNotifications({ id }) {
  const api = useApi(() => controlApi.userNotifications(id), [id]);
  return (
    <Async api={api}>
      {(rows) => (
        <DataTable
          rows={rows}
          empty={<EmptyState title="لا توجد إشعارات" />}
          columns={[
            { key: "title", label: "الإشعار" },
            { key: "type_label", label: "النوع" },
            { key: "delivery_status", label: "الحالة", render: (n) => <StatusBadge map={DELIVERY} value={n.delivery_status} /> },
            { key: "read_at", label: "قُرئ", render: (n) => (n.read_at ? dt(n.read_at) : "لم يُقرأ") },
            { key: "created_at", label: "التاريخ", render: (n) => dt(n.created_at) },
          ]}
        />
      )}
    </Async>
  );
}

const fmtVal = (v) => (v === undefined || v === null || v === "" ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));

export function AuditTable({ rows }) {
  return (
    <DataTable
      rows={rows}
      empty={<EmptyState title="لا توجد سجلات" />}
      columns={[
        { key: "created_at", label: "الوقت", render: (a) => dt(a.created_at) },
        { key: "actor", label: "المنفّذ", render: (a) => a.actor || "—" },
        { key: "action", label: "الإجراء", render: (a) => AUDIT_ACTIONS[a.action] || a.action },
        { key: "entity", label: "الكيان", render: (a) => `${ENTITY[a.entity_type] || a.entity_type}${a.entity_label ? `: ${a.entity_label}` : ""}` },
        {
          key: "change",
          label: "التغيير",
          render: (a) => {
            const keys = Object.keys({ ...a.before, ...a.after });
            if (!keys.length) return a.note || "—";
            return (
              <div style={{ display: "grid", gap: 2, fontSize: "0.8rem" }}>
                {keys.slice(0, 4).map((k) => (
                  <div key={k} style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                    <b>{k}</b>
                    <bdi dir="auto" className="sub">{fmtVal(a.before[k])}</bdi>
                    <span aria-hidden="true">←</span>
                    <bdi dir="auto">{fmtVal(a.after[k])}</bdi>
                  </div>
                ))}
                {a.note && <div className="sub">{a.note}</div>}
              </div>
            );
          },
        },
      ]}
    />
  );
}

function UserHistory({ id }) {
  const api = useApi(() => controlApi.userHistory(id), [id]);
  return <Async api={api}>{(rows) => <AuditTable rows={rows} />}</Async>;
}

/* ------------------------------------------------------------------ parents */
export function ParentsPage() {
  const nav = useNavigate();
  const [f, set, setPage] = useFilters({ search: "", issues: "" });
  const search = useDebounce(f.search);
  const api = useApi(() => controlApi.parents({ ...f, search }), [JSON.stringify({ ...f, search })]);
  return (
    <>
      <PageHead
        title="أولياء الأمور"
        desc="لا يملك ولي الأمر حسابًا في مدار: يدخل برقم هاتفه وكود الطالب بجلسة قراءة فقط. هذه الصفحة مشتقّة من بيانات التسجيل التي يدخلها المعلّمون."
        crumbs={[{ label: "الإدارة" }, { label: "أولياء الأمور" }]}
      />
      <Card pad={false}>
        <div className="cc-tools">
          <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="هاتف ولي الأمر أو اسم الطالب…" />
          <Select label="مشكلات الوصول" value={f.issues} onChange={(v) => set({ issues: v })} all="الكل" options={[{ value: "1", label: "من لديهم مشكلة وصول فقط" }]} />
        </div>
        <Async api={api}>
          {(d) => (
            <>
              <DataTable
                rows={d.results}
                rowKey="phone"
                onRow={(p) => nav(`/team/parents/${p.phone}`)}
                empty={<EmptyState title="لا يوجد أولياء أمور" text="يظهر ولي الأمر هنا عندما يسجّل المعلّم رقمه ضمن بيانات طالب." />}
                columns={[
                  { key: "phone", label: "الهاتف", ltr: true },
                  { key: "name", label: "الاسم", render: (p) => p.name || "—" },
                  { key: "children", label: "الأبناء", render: (p) => num(p.children) },
                  { key: "environments", label: "البيئات", render: (p) => p.environments.join("، ") },
                  { key: "unread_messages", label: "رسائل لم تُقرأ", render: (p) => num(p.unread_messages) },
                  { key: "has_access_issues", label: "الوصول", render: (p) => (p.has_access_issues ? <Badge tone="warn">مشكلة وصول</Badge> : <Badge tone="ok">سليم</Badge>) },
                ]}
              />
              <Pager page={d.page} pages={d.pages} count={d.count} onPage={setPage} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

export function ParentDetailPage() {
  const { phone } = useParams();
  const api = useApi(() => controlApi.parent(phone), [phone]);
  return (
    <>
      <PageHead title="ولي أمر" desc="عرض للقراءة فقط. لا يمكن من هنا منح ولي الأمر أي صلاحية." crumbs={[{ label: "الإدارة" }, { label: "أولياء الأمور", to: "/team/parents" }, { label: phone }]} />
      <Async api={api} rows={8}>
        {(d) => (
          <>
            <Card title="الأبناء وحالة الوصول" pad={false}>
              <DataTable
                rowKey="enrollment_id"
                rows={d.children}
                columns={[
                  { key: "student", label: "الطالب" },
                  { key: "environment", label: "البيئة", render: (c) => `${c.environment} — ${c.teacher}` },
                  { key: "grade", label: "الصف" },
                  { key: "enrollment_active", label: "التسجيل", render: (c) => <Badge tone={c.enrollment_active ? "ok" : "warn"}>{c.enrollment_active ? "نشط" : "غير نشط"}</Badge> },
                  { key: "access_ready", label: "إمكانية دخول البوابة", render: (c) => (c.access_ready ? <Badge tone="ok">جاهز</Badge> : <Badge tone="warn">{c.issues.join(" · ")}</Badge>) },
                ]}
              />
            </Card>
            <div className="cc-grid c2">
              <Card title="رسائل المعلّمين" sub="تحذيرات وملاحظات (تلقائية أو يدوية)" pad={false}>
                <DataTable
                  rows={d.messages}
                  empty={<EmptyState title="لا توجد رسائل" />}
                  columns={[
                    { key: "title", label: "الرسالة", render: (m) => (<><div className="strong">{m.title}</div><div className="sub">{m.body}</div></>) },
                    { key: "student", label: "الطالب" },
                    { key: "kind", label: "النوع", render: (m) => (m.automatic ? <Badge tone="info">تلقائية</Badge> : <Badge tone={m.kind === "warning" ? "warn" : "plain"}>{m.kind === "warning" ? "تحذير" : "ملاحظة"}</Badge>) },
                    { key: "read_at", label: "قُرئت", render: (m) => (m.read_at ? dt(m.read_at) : "لا") },
                  ]}
                />
              </Card>
              <Card title="ردود ولي الأمر" pad={false}>
                <DataTable
                  rows={d.replies}
                  empty={<EmptyState title="لا توجد ردود" />}
                  columns={[
                    { key: "body", label: "الرد" },
                    { key: "student", label: "الطالب" },
                    { key: "created_at", label: "التاريخ", render: (r) => dt(r.created_at) },
                    { key: "read_by_teacher", label: "قرأها المعلّم", render: (r) => (r.read_by_teacher ? "نعم" : "لا") },
                  ]}
                />
              </Card>
            </div>
            <Card title="تذاكر مرتبطة" pad={false}>
              <DataTable
                rows={d.tickets}
                empty={<EmptyState title="لا توجد تذاكر" text="يمكنك تسجيل تذكرة نيابةً عن ولي الأمر من مركز الدعم." />}
                columns={[
                  { key: "number", label: "الرقم", render: (t) => <Link to={`/team/support/tickets/${t.id}`} style={{ textDecoration: "underline" }}>{t.number}</Link> },
                  { key: "subject", label: "الموضوع" },
                  { key: "status", label: "الحالة", render: (t) => <StatusBadge map={TICKET_STATUS} value={t.status} /> },
                ]}
              />
            </Card>
          </>
        )}
      </Async>
    </>
  );
}
