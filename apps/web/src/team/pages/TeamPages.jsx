import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { Btn, Field, Modal, TextInput } from "../../auth/ui.jsx";
import { controlApi } from "../../lib/controlApi.js";
import { PRIORITY, TICKET_STATUS } from "../labels.js";
import { AuditTable } from "./UsersPages.jsx";
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
  useAction,
  useApi,
  useCan,
  useDebounce,
  useFilters,
  useSort,
  useToast,
  useControl,
} from "../kit.jsx";

/* ------------------------------------------------------------------ permission picker */
function PermissionPicker({ catalog, value, onChange, disabledKeys = [], readOnly }) {
  const toggle = (k) => onChange(value.includes(k) ? value.filter((x) => x !== k) : [...value, k]);
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {catalog.map((g) => (
        <div className="perm-group" key={g.key}>
          <h4>{g.label}</h4>
          {g.permissions.map((p) => (
            <label className="cc-check" key={p.key}>
              <input type="checkbox" checked={value.includes(p.key)} disabled={readOnly || disabledKeys.includes(p.key)} onChange={() => toggle(p.key)} />
              {p.label}
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ members */
export function MembersPage() {
  const nav = useNavigate();
  const [f, set] = useFilters({ search: "" });
  const search = useDebounce(f.search);
  const api = useApi(() => controlApi.team({ search }), [search]);
  return (
    <>
      <PageHead
        title="أعضاء الفريق"
        desc="حسابات فريق مدار الداخلي. تُنشأ الحسابات من الخادم (أمر create_team_user) ولا يوجد تسجيل عام للفريق."
        crumbs={[{ label: "الإدارة" }, { label: "أعضاء الفريق" }]}
      />
      <Card pad={false}>
        <div className="cc-tools">
          <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="الاسم أو معرّف الدخول…" />
        </div>
        <Async api={api}>
          {(rows) => (
            <DataTable
              rows={rows}
              onRow={(m) => nav(`/team/members/${m.id}`)}
              empty={<EmptyState title="لا يوجد أعضاء" />}
              columns={[
                { key: "name", label: "الاسم", render: (m) => (<><div className="strong">{m.name}</div><div className="sub ltr">{m.username}</div></>) },
                { key: "role", label: "الدور", render: (m) => <Badge tone={m.role ? "info" : "plain"}>{m.role_name}</Badge> },
                { key: "is_active", label: "الحالة", render: (m) => <Badge tone={m.is_active ? "ok" : "bad"}>{m.is_active ? "نشط" : "معطّل"}</Badge> },
                { key: "permission_count", label: "الصلاحيات", render: (m) => `${num(m.permission_count)} صلاحية` },
                { key: "last_login", label: "آخر دخول", render: (m) => ago(m.last_login) },
                { key: "assigned_active", label: "تذاكر مسندة", render: (m) => num(m.assigned_active) },
                { key: "resolved", label: "تذاكر محلولة", render: (m) => num(m.resolved) },
              ]}
            />
          )}
        </Async>
      </Card>
    </>
  );
}

function EditMember({ m, roles, catalog, onClose, onSaved }) {
  const can = useCan();
  const [form, setForm] = useState({
    name: m.name,
    role: m.role || "",
    extra: m.extra_permissions,
    revoked: m.revoked_permissions,
  });
  const [errs, setErrs] = useState({});
  const [run, busy] = useAction();
  const role = roles.find((r) => r.key === form.role);
  const base = role?.permissions || [];
  // A permission is "on" if the role gives it (and it is not revoked) or it is granted on top.
  const effective = useMemo(() => [...new Set([...base.filter((p) => !form.revoked.includes(p)), ...form.extra])], [base, form.revoked, form.extra]);
  const setEffective = (next) => {
    const extra = next.filter((p) => !base.includes(p));
    const revoked = base.filter((p) => !next.includes(p));
    setForm({ ...form, extra, revoked });
  };
  const save = () =>
    run(async () => {
      if (form.name.trim().length < 2) {
        setErrs({ name: "الاسم يجب ألا يقل عن حرفين." });
        return false;
      }
      setErrs({});
      const body = {};
      if (form.name !== m.name) body.name = form.name;
      if (form.role && form.role !== m.role) body.role = form.role;
      if (JSON.stringify([...form.extra].sort()) !== JSON.stringify([...m.extra_permissions].sort()) || form.role !== (m.role || "")) body.extra_permissions = form.extra;
      if (JSON.stringify([...form.revoked].sort()) !== JSON.stringify([...m.revoked_permissions].sort()) || form.role !== (m.role || "")) body.revoked_permissions = form.revoked;
      if (!Object.keys(body).length) return onClose();
      try {
        const r = await controlApi.updateMember(m.id, body);
        onSaved(r);
        onClose();
      } catch (e) {
        setErrs(fieldErrors(e));
        throw e;
      }
    }, "تم حفظ بيانات العضو");
  return (
    <Modal
      size="lg"
      title={`تعديل ${m.name}`}
      text="تغيير الدور أو الصلاحيات يسري على الخادم فور الحفظ ويُسجَّل في سجل التدقيق."
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
      <div style={{ display: "grid", gap: 10 }}>
        <Field label="الاسم" required error={errs.name}>
          <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="الدور" required error={errs.role} hint="الدور يحدّد الصلاحيات الأساسية. يمكنك تعديلها لهذا الشخص أدناه.">
          <select className="cc-select" style={{ width: "100%" }} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value, extra: [], revoked: [] })}>
            {!m.role && <option value="">— اختر دورًا —</option>}
            {roles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.name}
              </option>
            ))}
          </select>
        </Field>
        {(errs.extra_permissions || errs.revoked_permissions) && <p style={{ color: "#b4442f" }}>{errs.extra_permissions || errs.revoked_permissions}</p>}
        {form.role && can("team.manage") && (
          <>
            <b style={{ fontSize: "0.9rem" }}>الصلاحيات الفعلية لهذا العضو</b>
            <PermissionPicker catalog={catalog} value={effective} onChange={setEffective} readOnly={form.role === "super_admin"} />
          </>
        )}
      </div>
    </Modal>
  );
}

export function MemberDetailPage() {
  const { id } = useParams();
  const can = useCan();
  const toast = useToast();
  const [tab, setTab] = useState("overview");
  const [edit, setEdit] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [local, setLocal] = useState(null);
  const api = useApi(() => controlApi.member(id), [id]);
  const roles = useApi(() => controlApi.roles(), [], { skip: !can("roles.view", "team.manage") });
  const catalog = useApi(() => controlApi.permissions(), []);
  const m = local && local.id === Number(id) ? local : api.data;
  if (api.error && !api.data) return <ErrorState error={api.error} onRetry={api.reload} />;
  if (!m) return <Skeleton rows={8} />;
  const toggleActive = async () => {
    try {
      setLocal(await controlApi.updateMember(m.id, { is_active: !m.is_active }));
      toast(m.is_active ? "عُطّل الحساب وسُجّل خروجه من كل الأجهزة" : "فُعّل الحساب");
    } catch (e) {
      toast(errText(e), "err");
      return false;
    }
  };
  return (
    <>
      <PageHead title={m.name} desc={`${m.role_name} · ${m.username}`} crumbs={[{ label: "الإدارة" }, { label: "أعضاء الفريق", to: "/team/members" }, { label: m.name }]}>
        <Badge tone={m.is_active ? "ok" : "bad"}>{m.is_active ? "نشط" : "معطّل"}</Badge>
        {can("team.manage") && (
          <>
            <Btn variant="secondary" onClick={() => setEdit(true)}>
              <Pencil size={15} /> تعديل
            </Btn>
            <Btn variant={m.is_active ? "danger" : "primary"} onClick={() => setConfirm(true)}>
              {m.is_active ? "تعطيل الحساب" : "تفعيل الحساب"}
            </Btn>
          </>
        )}
      </PageHead>
      <Card pad={false}>
        <Tabs
          tabs={[
            { key: "overview", label: "نظرة عامة" },
            { key: "permissions", label: "الصلاحيات" },
            ...(can("tickets.view") ? [{ key: "tickets", label: "التذاكر المسندة" }] : []),
            ...(can("audit.view") ? [{ key: "activity", label: "النشاط الإداري" }] : []),
          ]}
          value={tab}
          onChange={setTab}
        />
        <div className="pad">
          {tab === "overview" && (
            <div className="cc-grid c2">
              <KV items={[["الدور", m.role_name], ["معرّف الدخول", <bdi dir="ltr" key="u">{m.username}</bdi>], ["البريد", m.email || "—"], ["تاريخ الإضافة", dt(m.date_joined)], ["آخر دخول", dt(m.last_login)]]} />
              <KV items={[["تذاكر نشطة مسندة", num(m.assigned_active)], ["تذاكر محلولة", num(m.resolved)], ["عدد الصلاحيات", num(m.permission_count)]]} />
            </div>
          )}
          {tab === "permissions" &&
            (catalog.data ? <PermissionPicker catalog={catalog.data} value={m.permissions} onChange={() => {}} readOnly /> : <Skeleton rows={4} />)}
          {tab === "tickets" && <MemberTickets id={m.id} />}
          {tab === "activity" && <MemberActivity id={m.id} />}
        </div>
      </Card>
      {edit && roles.data && catalog.data && <EditMember m={m} roles={roles.data} catalog={catalog.data} onClose={() => setEdit(false)} onSaved={setLocal} />}
      {confirm && (
        <Confirm
          title={m.is_active ? "تعطيل الحساب" : "تفعيل الحساب"}
          text={m.is_active ? `سيُسجَّل خروج ${m.name} من كل أجهزته فورًا ولن يستطيع الدخول.` : `سيتمكّن ${m.name} من الدخول بصلاحيات دوره.`}
          confirmLabel={m.is_active ? "تعطيل" : "تفعيل"}
          danger={m.is_active}
          onClose={() => setConfirm(null)}
          onConfirm={toggleActive}
        />
      )}
    </>
  );
}

function MemberTickets({ id }) {
  const nav = useNavigate();
  const api = useApi(() => controlApi.memberTickets(id), [id]);
  return (
    <Async api={api}>
      {(rows) => (
        <DataTable
          rows={rows}
          onRow={(t) => nav(`/team/support/tickets/${t.id}`)}
          empty={<EmptyState title="لا توجد تذاكر مسندة" />}
          columns={[
            { key: "number", label: "الرقم" },
            { key: "subject", label: "الموضوع" },
            { key: "priority", label: "الأولوية", render: (t) => <PriorityBadge value={t.priority} labels={PRIORITY} /> },
            { key: "status", label: "الحالة", render: (t) => <StatusBadge map={TICKET_STATUS} value={t.status} /> },
            { key: "updated_at", label: "آخر تحديث", render: (t) => ago(t.updated_at) },
          ]}
        />
      )}
    </Async>
  );
}
function MemberActivity({ id }) {
  const api = useApi(() => controlApi.memberActivity(id), [id]);
  return <Async api={api}>{(rows) => <AuditTable rows={rows} />}</Async>;
}

/* ------------------------------------------------------------------ roles */
function RoleEditor({ role, catalog, myPerms, isSuper, onClose, onSaved }) {
  const [form, setForm] = useState({ name: role?.name || "", description: role?.description || "", permissions: role?.permissions || [] });
  const [errs, setErrs] = useState({});
  const [run, busy] = useAction();
  const lockedKeys = isSuper ? [] : catalog.flatMap((g) => g.permissions.map((p) => p.key)).filter((k) => !myPerms.includes(k));
  const save = () =>
    run(async () => {
      if (form.name.trim().length < 2) {
        setErrs({ name: "اكتب اسم الدور." });
        return false;
      }
      setErrs({});
      try {
        await (role ? controlApi.updateRole(role.id, form) : controlApi.createRole(form));
        onSaved();
        onClose();
      } catch (e) {
        setErrs(fieldErrors(e));
        throw e;
      }
    }, role ? "تم تحديث الدور" : "تم إنشاء الدور");
  return (
    <Modal
      size="lg"
      title={role ? `تعديل الدور: ${role.name}` : "دور جديد"}
      text="لا يمكنك منح صلاحيات لا تملكها أنت."
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
      <div style={{ display: "grid", gap: 10 }}>
        <Field label="اسم الدور" required error={errs.name}>
          <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={80} />
        </Field>
        <Field label="الوصف" error={errs.description}>
          <TextArea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={300} />
        </Field>
        {errs.permissions && <p style={{ color: "#b4442f" }}>{errs.permissions}</p>}
        <PermissionPicker catalog={catalog} value={form.permissions} onChange={(permissions) => setForm({ ...form, permissions })} disabledKeys={lockedKeys} />
      </div>
    </Modal>
  );
}

export function RolesPage() {
  const can = useCan();
  const { permissions: mine, me } = useControl();
  const toast = useToast();
  const roles = useApi(() => controlApi.roles(), []);
  const catalog = useApi(() => controlApi.permissions(), []);
  const [editing, setEditing] = useState(undefined); // undefined = closed, null = new
  const [removing, setRemoving] = useState(null);
  return (
    <>
      <PageHead title="الأدوار والصلاحيات" desc="الصلاحيات تُفرض على الخادم عند كل طلب. إخفاء زر في الواجهة لا يمنح ولا يمنع شيئًا." crumbs={[{ label: "النظام" }, { label: "الأدوار والصلاحيات" }]}>
        {can("roles.manage") && (
          <Btn onClick={() => setEditing(null)}>
            <Plus size={16} /> دور جديد
          </Btn>
        )}
      </PageHead>
      <Async api={roles}>
        {(rows) => (
          <div className="cc-grid c3">
            {rows.map((r) => (
              <Card
                key={r.id}
                title={r.name}
                sub={r.description}
                actions={
                  <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
                    {r.locked && <Lock size={15} aria-label="دور مقفل" />}
                    {r.is_system && <Badge tone="plain" className="plain">أساسي</Badge>}
                  </span>
                }
              >
                <div style={{ display: "grid", gap: 10 }}>
                  <div className="sub">
                    {num(r.permissions.length)} صلاحية · {num(r.members)} عضو
                  </div>
                  {can("roles.manage") && !r.locked && (
                    <div className="cc-actions">
                      <Btn variant="secondary" onClick={() => setEditing(r)}>
                        <Pencil size={14} /> تعديل
                      </Btn>
                      {!r.is_system && (
                        <Btn variant="ghost" onClick={() => setRemoving(r)}>
                          <Trash2 size={14} /> حذف
                        </Btn>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </Async>
      {editing !== undefined && catalog.data && (
        <RoleEditor role={editing} catalog={catalog.data} myPerms={mine} isSuper={me.role === "super_admin"} onClose={() => setEditing(undefined)} onSaved={roles.reload} />
      )}
      {removing && (
        <Confirm
          danger
          title={`حذف الدور «${removing.name}»`}
          text="لا يمكن حذف دور له أعضاء. هذا الإجراء نهائي."
          confirmLabel="حذف"
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            try {
              await controlApi.deleteRole(removing.id);
              roles.reload();
            } catch (e) {
              toast(errText(e), "err");
              return false;
            }
          }}
        />
      )}
    </>
  );
}

/* ------------------------------------------------------------------ environments */
export function EnvironmentsPage() {
  const nav = useNavigate();
  const [f, set, setPage] = useFilters({ search: "", status: "" });
  const [sort, toggle, sortParam] = useSort({ key: "created_at", dir: "desc" });
  const search = useDebounce(f.search);
  const params = { ...f, search, sort: sortParam };
  const api = useApi(() => controlApi.environments(params), [JSON.stringify(params)]);
  return (
    <>
      <PageHead title="البيئات التعليمية" desc="كل معلّم يملك بيئة واحدة. تفاصيل أي بيئة تُفتح بتسجيل في سجل التدقيق." crumbs={[{ label: "الإدارة" }, { label: "البيئات" }]} />
      <Card pad={false}>
        <div className="cc-tools">
          <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="اسم البيئة أو المعلّم أو المعرّف…" />
          <Select label="الحالة" value={f.status} onChange={(v) => set({ status: v })} options={[{ value: "active", label: "نشطة" }, { value: "suspended", label: "موقوفة (المالك موقوف)" }]} />
        </div>
        <Async api={api}>
          {(d) => (
            <>
              <DataTable
                rows={d.results}
                sort={sort}
                onSort={toggle}
                onRow={(e) => nav(`/team/environments/${e.id}`)}
                empty={<EmptyState title="لا توجد بيئات" />}
                columns={[
                  { key: "name", label: "البيئة", sort: "name", render: (e) => (<><div className="strong">{e.name}</div><div className="sub">{e.subject_stage}</div></>) },
                  { key: "id", label: "المعرّف", className: "cc-num" },
                  { key: "owner", label: "المعلّم", render: (e) => e.owner.name },
                  { key: "student_count", label: "الطلاب", render: (e) => num(e.student_count) },
                  { key: "group_count", label: "المجموعات", render: (e) => num(e.group_count) },
                  { key: "created_at", label: "الإنشاء", sort: "created_at", render: (e) => dt(e.created_at) },
                  { key: "status", label: "الحالة", render: (e) => <Badge tone={e.status === "active" ? "ok" : "bad"}>{e.status === "active" ? "نشطة" : "موقوفة"}</Badge> },
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

function EditEnv({ env, onClose, onSaved }) {
  const [form, setForm] = useState({ name: env.name, subject_stage: env.subject_stage || "" });
  const [errs, setErrs] = useState({});
  const [run, busy] = useAction();
  return (
    <Modal
      title="تعديل بيانات البيئة"
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            إلغاء
          </Btn>
          <Btn
            loading={busy}
            loadingText="جارٍ الحفظ…"
            onClick={() =>
              run(async () => {
                if (form.name.trim().length < 2) {
                  setErrs({ name: "اكتب اسم البيئة." });
                  return false;
                }
                setErrs({});
                try {
                  onSaved(await controlApi.updateEnvironment(env.id, form));
                  onClose();
                } catch (e) {
                  setErrs(fieldErrors(e));
                  throw e;
                }
              }, "تم حفظ بيانات البيئة")
            }
          >
            حفظ
          </Btn>
        </>
      }
    >
      <div style={{ display: "grid", gap: 8 }}>
        <Field label="اسم البيئة" required error={errs.name}>
          <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="المادة / المرحلة" error={errs.subject_stage}>
          <TextInput value={form.subject_stage} onChange={(e) => setForm({ ...form, subject_stage: e.target.value })} />
        </Field>
      </div>
    </Modal>
  );
}

export function EnvironmentDetailPage() {
  const { id } = useParams();
  const can = useCan();
  const [tab, setTab] = useState("general");
  const [edit, setEdit] = useState(false);
  const [local, setLocal] = useState(null);
  const api = useApi(() => controlApi.environment(id), [id]);
  const e = local && local.id === Number(id) ? local : api.data;
  if (api.error && !api.data) return <ErrorState error={api.error} onRetry={api.reload} />;
  if (!e) return <Skeleton rows={8} />;
  const c = e.counts;
  return (
    <>
      <PageHead title={e.name} desc={`${e.subject_stage || "—"} · ${e.academic_year}`} crumbs={[{ label: "الإدارة" }, { label: "البيئات", to: "/team/environments" }, { label: e.name }]}>
        {can("environments.manage") && (
          <Btn variant="secondary" onClick={() => setEdit(true)}>
            <Pencil size={15} /> تعديل
          </Btn>
        )}
      </PageHead>
      <div className="cc-grid c4">
        {[["الطلاب النشطون", c.students_active], ["إجمالي الطلاب", c.students_total], ["المجموعات", c.groups], ["جلسات (30 يومًا)", c.sessions_30d]].map(([k, v]) => (
          <div className="cc-card kpi" key={k}><div className="top"><span>{k}</span></div><div className="val">{num(v)}</div></div>
        ))}
      </div>
      <Card pad={false}>
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { key: "general", label: "معلومات عامة" },
            { key: "groups", label: "المجموعات والمواعيد" },
            { key: "students", label: "الطلاب" },
            { key: "attendance", label: "الحضور والتقييم" },
            { key: "activity", label: "النشاط الأخير" },
            { key: "tickets", label: "التذاكر" },
          ]}
        />
        <div className="pad">
          {tab === "general" && (
            <KV
              items={[
                ["المعلّم المالك", <Link key="o" to={`/team/users/${e.owner.id}`} style={{ textDecoration: "underline" }}>{e.owner.name}</Link>],
                ["حالة المالك", <Badge key="s" tone={e.owner.is_active ? "ok" : "bad"}>{e.owner.is_active ? "نشط" : "موقوف"}</Badge>],
                ["تاريخ الإنشاء", dt(e.created_at)],
                ["الصفوف", e.grades.map((g) => `${g.name} (${num(g.students)})`).join("، ") || "—"],
                ["الاشتراك", e.subscription ? `${e.subscription.plan || "—"} — ${e.subscription.state}` : "لا يوجد"],
              ]}
            />
          )}
          {tab === "groups" && (
            <div className="cc-grid c2">
              <DataTable rows={e.groups} empty={<EmptyState title="لا مجموعات" />} columns={[{ key: "name", label: "المجموعة" }, { key: "grade", label: "الصف" }, { key: "students", label: "الطلاب", render: (g) => num(g.students) }]} />
              <DataTable rowKey="group" rows={e.schedules.map((s, i) => ({ ...s, i }))} empty={<EmptyState title="لا مواعيد" />} columns={[{ key: "group", label: "المجموعة" }, { key: "weekday", label: "اليوم" }, { key: "start", label: "البداية", ltr: true }, { key: "end", label: "النهاية", ltr: true, render: (s) => s.end || "—" }]} />
            </div>
          )}
          {tab === "students" &&
            (can("students.view") ? (
              <DataTable
                rows={e.students}
                empty={<EmptyState title="لا يوجد طلاب" />}
                columns={[{ key: "name", label: "الطالب", render: (s) => <Link to={`/team/users/${s.id}`} style={{ textDecoration: "underline" }}>{s.name}</Link> }, { key: "grade", label: "الصف" }, { key: "is_active", label: "التسجيل", render: (s) => <Badge tone={s.is_active ? "ok" : "warn"}>{s.is_active ? "نشط" : "غير نشط"}</Badge> }]}
              />
            ) : (
              <EmptyState title="قائمة الطلاب مخفية" text="تحتاج صلاحية «عرض الطلاب»." />
            ))}
          {tab === "attendance" && (
            <KV items={[["حضور (30 يومًا)", num(e.attendance_30d.present)], ["غياب (30 يومًا)", num(e.attendance_30d.absent)], ["حالات الطلاب الشهرية (30 يومًا)", Object.entries(e.evaluations_30d).map(([k, v]) => `${k}: ${num(v)}`).join("، ") || "—"]]} />
          )}
          {tab === "activity" && (
            <div className="timeline" style={{ padding: 0 }}>
              {e.recent_activity.length === 0 && <EmptyState title="لا نشاط" />}
              {e.recent_activity.map((a, i) => (
                <div className="ev" key={i}><span /><div>{a.text}<div className="when">{dt(a.at)}</div></div></div>
              ))}
            </div>
          )}
          {tab === "tickets" && (
            <DataTable rows={e.tickets} empty={<EmptyState title="لا توجد تذاكر مرتبطة" />} columns={[{ key: "number", label: "الرقم", render: (t) => <Link to={`/team/support/tickets/${t.id}`} style={{ textDecoration: "underline" }}>{t.number}</Link> }, { key: "subject", label: "الموضوع" }, { key: "priority", label: "الأولوية", render: (t) => <PriorityBadge value={t.priority} labels={PRIORITY} /> }, { key: "status", label: "الحالة", render: (t) => <StatusBadge map={TICKET_STATUS} value={t.status} /> }]} />
          )}
        </div>
      </Card>
      {edit && <EditEnv env={e} onClose={() => setEdit(false)} onSaved={setLocal} />}
    </>
  );
}
