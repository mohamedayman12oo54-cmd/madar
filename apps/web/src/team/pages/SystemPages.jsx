import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Download, Printer, Save } from "lucide-react";
import { Btn, Banner, Field } from "../../auth/ui.jsx";
import { controlApi } from "../../lib/controlApi.js";
import { AUDIT_ACTIONS, ENTITY, JOB_STATUS, REPORT_FILTERS, USER_ROLE } from "../labels.js";
import { AuditTable } from "./UsersPages.jsx";
import {
  Async,
  Badge,
  Card,
  ChartCard,
  DataTable,
  EmptyState,
  HBars,
  KV,
  LineChart,
  BarChart,
  PageHead,
  Pager,
  RangePicker,
  SERIES,
  SearchBox,
  Select,
  Skeleton,
  StatusBadge,
  Tabs,
  ago,
  dt,
  errText,
  hoursText,
  money,
  msText,
  num,
  rangeParams,
  secsText,
  tableOf,
  toSeries,
  useAction,
  useApi,
  useCan,
  useDebounce,
  useFilters,
  useToast,
} from "../kit.jsx";

/* ================================================================== reports */
const TOTAL = {
  new: "جديد في الفترة", all: "الإجمالي", active: "نشط", suspended: "موقوف", pending: "بانتظار التفعيل", with_students: "بيئات لها طلاب",
  created: "تذاكر جديدة", resolved: "محلولة", avg_first_response_hours: "متوسط أول رد (ساعة)", avg_resolution_hours: "متوسط الحل (ساعة)",
  agents: "موظفون", transactions: "معاملات", succeeded: "ناجحة", failed: "فاشلة", revenue: "الإيراد", total: "الإجمالي", completed: "مكتملة",
  avg_seconds: "متوسط التنفيذ (ث)", sent: "مُرسلة", read: "قُرئت", actions: "إجراءات",
};
const STATUS_FILTER = {
  users: [["active", "نشط"], ["suspended", "موقوف"], ["pending", "بانتظار التفعيل"]],
  teachers: [["active", "نشط"], ["suspended", "موقوف"], ["pending", "بانتظار التفعيل"]],
  students: [["active", "نشط"], ["suspended", "موقوف"], ["pending", "بانتظار التفعيل"]],
  tickets: [["open", "مفتوحة"], ["in_progress", "قيد المعالجة"], ["waiting_for_user", "بانتظار العميل"], ["resolved", "تم الحل"], ["closed", "مغلقة"]],
  finance: [["succeeded", "ناجحة"], ["failed", "فاشلة"], ["pending", "قيد المعالجة"], ["unknown", "تحتاج مطابقة"]],
  ai: [["completed", "مكتملة"], ["failed", "فاشلة"], ["pending", "قيد الانتظار"]],
  notifications: [["sent", "مُرسلة"], ["failed", "فاشلة"], ["pending", "قيد الإرسال"]],
};

function Table({ t, title }) {
  const rows = t.rows.map((r, i) => ({ ...r, __i: i }));
  return (
    <Card title={title} pad={false}>
      <DataTable
        rowKey="__i"
        rows={rows}
        empty={<EmptyState title="لا توجد بيانات" />}
        columns={t.columns.map((c) => ({ key: c.key, label: c.label, className: "cc-num", render: (r) => (/^\d{4}-\d\d-\d\dT/.test(String(r[c.key])) ? dt(r[c.key]) : r[c.key] === null || r[c.key] === undefined ? "—" : typeof r[c.key] === "number" ? num(r[c.key]) : r[c.key]) }))}
      />
    </Card>
  );
}

export function ReportsPage() {
  const { name } = useParams();
  const nav = useNavigate();
  const can = useCan();
  const toast = useToast();
  const list = useApi(() => controlApi.reports(), []);
  const [range, setRange] = useState({ range: "30d" });
  const [flt, setFlt] = useState({ status: "", role: "", environment: "" });
  const envs = useApi(() => controlApi.environments({ page_size: 100 }), [], { skip: !can("environments.view") });
  const key = name || list.data?.[0]?.key;
  const p = { ...rangeParams(range), ...flt };
  const api = useApi(() => controlApi.report(key, p), [key, JSON.stringify(p)], { skip: !key });
  const allowed = REPORT_FILTERS[key] || [];
  const numericCols = useMemo(() => (api.data ? api.data.columns.filter((c) => c.key !== "date" && api.data.rows.some((r) => typeof r[c.key] === "number")).slice(0, 3) : []), [api.data]);
  const colors = [SERIES.c1, SERIES.c2, SERIES.c3];
  return (
    <>
      <PageHead title="التقارير" desc="تقارير من بيانات النظام الفعلية. التصدير CSV من الخادم، وPDF عبر زر الطباعة (احفظ كـ PDF)." crumbs={[{ label: "التحليلات" }, { label: "التقارير" }]}>
        <Btn variant="secondary" onClick={() => window.print()}><Printer size={15} /> طباعة / PDF</Btn>
        <Btn variant="secondary" disabled={!key} onClick={() => controlApi.exportReport(key, p).catch((e) => toast(errText(e), "err"))}><Download size={15} /> تصدير CSV</Btn>
      </PageHead>
      <Card pad={false}>
        <Async api={list} rows={2}>
          {(reports) => (
            <>
              <Tabs value={key} onChange={(k) => nav(`/team/reports/${k}`)} tabs={reports.map((r) => ({ key: r.key, label: r.title }))} />
              <div className="cc-tools">
                <RangePicker value={range} onChange={setRange} />
                {allowed.includes("status") && <Select label="الحالة" value={flt.status} onChange={(v) => setFlt({ ...flt, status: v })} options={(STATUS_FILTER[key] || []).map(([value, label]) => ({ value, label }))} />}
                {allowed.includes("role") && <Select label="نوع المستخدم" value={flt.role} onChange={(v) => setFlt({ ...flt, role: v })} options={key === "tickets" ? [{ value: "teacher", label: "معلّم" }, { value: "student", label: "طالب" }, { value: "parent", label: "ولي أمر" }] : [{ value: "teacher", label: "معلّم" }, { value: "student", label: "طالب" }]} />}
                {allowed.includes("environment") && can("environments.view") && <Select label="البيئة" value={flt.environment} onChange={(v) => setFlt({ ...flt, environment: v })} options={(envs.data?.results || []).map((e) => ({ value: e.id, label: e.name }))} />}
              </div>
            </>
          )}
        </Async>
      </Card>
      <Async api={api} rows={8}>
        {(d) => (
          <>
            <div className="cc-grid kpi">
              {Object.entries(d.totals).map(([k, v]) => (
                <div className="cc-card kpi" key={k}><div className="top"><span>{TOTAL[k] || k}</span></div><div className="val">{v === null ? "—" : k === "revenue" ? money(v) : num(v)}</div></div>
              ))}
            </div>
            {numericCols.length > 0 && d.rows.length > 1 && (
              <ChartCard title={d.title} legend={numericCols.map((c, i) => ({ label: c.label, color: colors[i] }))} table={{ columns: d.columns.map((c) => c.label), rows: d.rows.map((r) => d.columns.map((c) => (typeof r[c.key] === "number" ? num(r[c.key]) : r[c.key] ?? "—"))) }}>
                <LineChart series={numericCols.map((c, i) => ({ label: c.label, color: colors[i], points: d.rows.map((r) => ({ date: r.date, value: r[c.key] || 0 })) }))} />
              </ChartCard>
            )}
            {!d.rows[0]?.date && <Table t={d} title={d.title} />}
            {d.breakdowns.map((b) => <Table key={b.title} t={b} title={b.title} />)}
            {d.detail && <Table t={d.detail} title={d.detail.title} />}
            {d.rows[0]?.date && !d.detail && <Table t={d} title="الجدول اليومي" />}
          </>
        )}
      </Async>
    </>
  );
}

/* ================================================================== analytics pages */
export function AnalyticsPage() {
  const { kind } = useParams();
  const [range, setRange] = useState({ range: "30d" });
  const p = rangeParams(range);
  const api = useApi(
    () => (kind === "finance" ? controlApi.financeOverview(p) : kind === "ai" ? controlApi.aiOverview(p) : controlApi.report("users", p)),
    [kind, JSON.stringify(p)]
  );
  const titles = { users: "تحليلات المستخدمين", finance: "التحليلات المالية", ai: "تحليلات الذكاء الاصطناعي" };
  return (
    <>
      <PageHead title={titles[kind] || "التحليلات"} desc="رسوم تحليلية للاتجاهات. القوائم التفصيلية في صفحات العمليات والتقارير." crumbs={[{ label: "التحليلات" }, { label: titles[kind] || "" }]}>
        <RangePicker value={range} onChange={setRange} />
      </PageHead>
      <Async api={api} rows={8}>
        {(d) => {
          if (kind === "finance")
            return (
              <div className="cc-grid c2">
                <ChartCard title="الإيراد اليومي" table={tableOf(["الإيراد"], [{ points: d.charts.revenue }])}><LineChart area series={toSeries([["الإيراد", SERIES.navy, d.charts.revenue]])} format={(v) => money(v)} /></ChartCard>
                <ChartCard title="المعاملات الناجحة والفاشلة" legend={[{ label: "ناجحة", color: SERIES.c1 }, { label: "فاشلة", color: SERIES.c2 }]} table={tableOf(["ناجحة", "فاشلة"], [{ points: d.charts.succeeded }, { points: d.charts.failed }])}><LineChart series={toSeries([["ناجحة", SERIES.c1, d.charts.succeeded], ["فاشلة", SERIES.c2, d.charts.failed]])} /></ChartCard>
                <Card title="حالات الاشتراك الآن"><HBars rows={[["نشط", d.subscriptions.active], ["تجريبي", d.subscriptions.trial], ["متأخر السداد", d.subscriptions.past_due], ["ملغى", d.subscriptions.canceled], ["منتهي", d.subscriptions.expired]].map(([name, count]) => ({ name, count }))} /></Card>
              </div>
            );
          if (kind === "ai")
            return (
              <div className="cc-grid c2">
                <ChartCard title="نجاح مقابل فشل" legend={[{ label: "ناجحة", color: SERIES.c1 }, { label: "فاشلة", color: SERIES.c2 }]} table={tableOf(["ناجحة", "فاشلة"], [{ points: d.charts.success }, { points: d.charts.failed }])}><LineChart series={toSeries([["ناجحة", SERIES.c1, d.charts.success], ["فاشلة", SERIES.c2, d.charts.failed]])} /></ChartCard>
                <Card title="حسب النوع"><HBars rows={d.by_kind.map((r) => ({ name: r.label, count: r.count }))} /></Card>
                <Card title="أسباب الفشل"><HBars color={SERIES.c2} rows={d.failure_categories.map((r) => ({ name: r.category, count: r.count }))} empty="لا إخفاقات." /></Card>
                <Card title="ملخص"><p>نسبة النجاح: <b>{d.success_rate === null ? "—" : `${num(d.success_rate)}%`}</b> · متوسط التنفيذ: <b>{secsText(d.avg_seconds)}</b></p></Card>
              </div>
            );
          const pts = (k) => d.rows.map((r) => ({ date: r.date, value: r[k] }));
          return (
            <div className="cc-grid c2">
              <ChartCard title="التسجيلات الجديدة" legend={[{ label: "معلّمون", color: SERIES.c1 }, { label: "طلاب", color: SERIES.c2 }]} table={tableOf(["معلّمون", "طلاب"], [{ points: pts("teachers") }, { points: pts("students") }])}><BarChart series={toSeries([["معلّمون", SERIES.c1, pts("teachers")], ["طلاب", SERIES.c2, pts("students")]])} /></ChartCard>
              <Card title="حالة الحسابات"><HBars rows={d.breakdowns[0].rows.map((r) => ({ name: r.name, count: r.count }))} /></Card>
              <Card title="الملخص"><p>إجمالي الحسابات: <b>{num(d.totals.all)}</b> · جديد في الفترة: <b>{num(d.totals.new)}</b></p></Card>
            </div>
          );
        }}
      </Async>
    </>
  );
}

/* ================================================================== audit */
export function AuditPage() {
  const toast = useToast();
  const [f, set, setPage] = useFilters({ search: "", actor: "", action: "", entity_type: "", from: "", to: "", hide_views: "" });
  const search = useDebounce(f.search);
  const params = { ...f, search };
  const api = useApi(() => controlApi.audit(params), [JSON.stringify(params)]);
  const meta = api.data?.filters;
  return (
    <>
      <PageHead title="سجل التدقيق" desc="سجل لا يُعدَّل ولا يُحذف لكل إجراء إداري مهم، مع القيم قبل وبعد. لا تُسجَّل كلمات المرور أو الرموز." crumbs={[{ label: "النظام" }, { label: "سجل التدقيق" }]}>
        <Btn variant="secondary" onClick={() => controlApi.exportAudit({ ...params, page: undefined }).catch((e) => toast(errText(e), "err"))}><Download size={15} /> تصدير CSV</Btn>
      </PageHead>
      <Card pad={false}>
        <div className="cc-tools">
          <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="كيان، منفّذ أو ملاحظة…" />
          <Select label="المنفّذ" value={f.actor} onChange={(v) => set({ actor: v })} options={(meta?.actors || []).map((a) => ({ value: a.id, label: a.name }))} />
          <Select label="الإجراء" value={f.action} onChange={(v) => set({ action: v })} options={(meta?.actions || []).map((a) => ({ value: a, label: AUDIT_ACTIONS[a] || a }))} />
          <Select label="نوع الكيان" value={f.entity_type} onChange={(v) => set({ entity_type: v })} options={(meta?.entity_types || []).map((a) => ({ value: a, label: ENTITY[a] || a }))} />
          <Select label="الاطّلاع" value={f.hide_views} onChange={(v) => set({ hide_views: v })} all="إظهار الكل" options={[{ value: "1", label: "إخفاء عمليات الاطّلاع" }]} />
          <label className="cc-field"><span>من</span><input type="date" className="cc-input" value={f.from} onChange={(e) => set({ from: e.target.value })} /></label>
          <label className="cc-field"><span>إلى</span><input type="date" className="cc-input" value={f.to} onChange={(e) => set({ to: e.target.value })} /></label>
        </div>
        <Async api={api}>
          {(d) => (
            <>
              <AuditTable rows={d.results} />
              <Pager page={d.page} pages={d.pages} count={d.count} onPage={setPage} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

/* ================================================================== system health */
const dot = (ok) => <span className={"dotstate " + (ok === true ? "ok" : ok === false ? "bad" : "none")} aria-hidden="true" />;

export function HealthPage() {
  const api = useApi(() => controlApi.health(), []);
  useEffect(() => {
    const t = setInterval(api.reload, 30000);
    return () => clearInterval(t);
  }, [api.reload]);
  return (
    <>
      <PageHead title="صحة النظام" desc="مبنية على فحوص حيّة وسجلات تشغيل فعلية. ما لا يوجد له سجل يُعرض صراحةً كـ «غير مسجّل»، ولا يُعرض كسليم." crumbs={[{ label: "النظام" }, { label: "صحة النظام" }]}>
        <Btn variant="secondary" onClick={api.reload}>تحديث الآن</Btn>
      </PageHead>
      <Async api={api} rows={8}>
        {(d) => (
          <>
            <Banner tone={d.overall === "ok" ? "info" : "err"}>
              {d.overall === "ok" ? "لا توجد مشكلات مرصودة." : "يوجد ما يحتاج متابعة: " + d.problems.map((x) => ({ db: "قاعدة البيانات", cache: "الذاكرة المؤقتة", jobs: "عمليات خلفية فاشلة", notifications: "طابور الإشعارات متأخر" }[x] || x)).join("، ")} · آخر فحص {ago(d.checked_at)}
            </Banner>
            <div className="cc-grid c3">
              <Card title="الخدمات الأساسية">
                <KV
                  items={[
                    ["واجهة API", <span key="a">{dot(true)}تستجيب (هذا الطلب نفسه)</span>],
                    ["قاعدة البيانات", <span key="d">{dot(d.database.ok)}{d.database.ok ? <>متصلة · <bdi dir="ltr">{num(d.database.latency_ms)} ms</bdi></> : "غير متاحة"}</span>],
                    ["الذاكرة المؤقتة", <span key="c">{dot(d.cache.ok)}{d.cache.ok ? "تعمل" : "لا تستجيب"}</span>],
                  ]}
                />
              </Card>
              <Card title="الإشعارات">
                <KV
                  items={[
                    ["قيد الإرسال", <span key="p">{dot(!d.notifications.backlog)}{num(d.notifications.pending)}{d.notifications.oldest_pending_at && <span className="sub"> · أقدمها {ago(d.notifications.oldest_pending_at)}</span>}</span>],
                    ["فشلت خلال 24 ساعة", <span key="f">{dot(d.notifications.failed_24h === 0)}{num(d.notifications.failed_24h)}</span>],
                    ["Web Push", <span key="w">{dot(d.notifications.push_configured)}{d.notifications.push_configured ? "مُعدّ" : "غير مُعدّ"}</span>],
                    ["وضع التسليم", d.notifications.dispatch_mode === "thread" ? "داخل الخادم" : "عملية خارجية"],
                  ]}
                />
              </Card>
              <Card title="الذكاء الاصطناعي">
                <KV
                  items={[
                    ["المزوّد", <span key="m">{dot(true)}{d.ai.provider === "llm" ? "نموذج حقيقي" : "بديل مبسّط (stub)"}</span>],
                    ["التنفيذ", d.ai.worker_mode === "thread" ? "داخل الخادم" : "عملية خارجية"],
                    ["قيد الانتظار", num(d.ai.pending)],
                    ["قيد المعالجة", num(d.ai.processing)],
                    ["عالقة (+15 دقيقة)", <span key="s">{dot(d.ai.stuck_processing === 0)}{num(d.ai.stuck_processing)}</span>],
                    ["فشلت خلال 24 ساعة", <span key="f">{dot(d.ai.failed_24h === 0)}{num(d.ai.failed_24h)}</span>],
                  ]}
                />
              </Card>
            </div>
            <Card title="العمليات الخلفية" sub="من سجلات التشغيل الفعلية" pad={false}><JobSummary rows={d.jobs} /></Card>
            <div className="cc-grid c3">
              <Card title="أخطاء عمليات خلفية" pad={false}><div className="feed">{d.recent_errors.jobs.length === 0 ? <EmptyState title="لا أخطاء" /> : d.recent_errors.jobs.map((e, i) => <div className="item" key={i}><span /><span>{e.name}<div className="sub">{e.error}</div></span><span className="when">{ago(e.at)}</span></div>)}</div></Card>
              <Card title="عمليات ذكاء اصطناعي فاشلة" pad={false}><div className="feed">{d.recent_errors.ai.length === 0 ? <EmptyState title="لا أخطاء" /> : d.recent_errors.ai.map((e) => <Link key={e.id} to={`/team/ai/${e.id}`}><span /><span>#{e.id}<div className="sub">{e.error}</div></span><span className="when">{ago(e.at)}</span></Link>)}</div></Card>
              <Card title="إشعارات فاشلة" pad={false}><div className="feed">{d.recent_errors.notifications.length === 0 ? <EmptyState title="لا أخطاء" /> : d.recent_errors.notifications.map((e) => <div className="item" key={e.id}><span /><span>#{e.id}<div className="sub">{e.error}</div></span><span className="when">{ago(e.at)}</span></div>)}</div></Card>
            </div>
          </>
        )}
      </Async>
    </>
  );
}

function JobSummary({ rows }) {
  return (
    <DataTable
      rowKey="name"
      rows={rows}
      columns={[
        { key: "label", label: "العملية", render: (j) => (<><div className="strong">{j.label}</div><div className="sub ltr">{j.name}</div></>) },
        { key: "status", label: "الحالة", render: (j) => <StatusBadge map={JOB_STATUS} value={j.status} /> },
        { key: "last", label: "آخر تشغيل", render: (j) => (j.last_run ? ago(j.last_run.at) : "—") },
        { key: "result", label: "النتيجة", render: (j) => (j.last_run ? (j.last_run.status === "ok" ? "نجح" : "فشل") : "—") },
        { key: "processed", label: "عناصر معالجة", render: (j) => (j.last_run ? num(j.last_run.processed) : "—") },
        { key: "failed", label: "عناصر فاشلة", render: (j) => (j.last_run ? num(j.last_run.failed_items) : "—") },
        { key: "dur", label: "المدة", render: (j) => (j.last_run ? msText(j.last_run.duration_ms) : "—") },
        { key: "runs", label: "تشغيلات 24 س", render: (j) => `${num(j.runs_24h)}${j.failed_runs_24h ? ` (${num(j.failed_runs_24h)} فاشلة)` : ""}` },
        { key: "err", label: "آخر خطأ", render: (j) => (j.last_error ? <span className="sub">{j.last_error.error}</span> : "—") },
      ]}
    />
  );
}

export function JobsPage() {
  const [f, set, setPage] = useFilters({ name: "", status: "" });
  const api = useApi(() => controlApi.jobs(f), [JSON.stringify(f)]);
  return (
    <>
      <PageHead title="العمليات الخلفية" desc="كل تشغيل لأوامر المعالجة يُسجَّل بنتيجته وعدد العناصر ومدته. «لا يوجد تشغيل مسجّل» يعني أن الأمر لم يُشغَّل بعد بجدولة أو يدويًا (أو أن التسليم يتم داخل الخادم)." crumbs={[{ label: "النظام" }, { label: "العمليات الخلفية" }]} />
      <Async api={api} rows={8}>
        {(d) => (
          <>
            <Card title="الملخص" pad={false}><JobSummary rows={d.summary} /></Card>
            <Card title="سجل التشغيل" pad={false}>
              <div className="cc-tools">
                <Select label="العملية" value={f.name} onChange={(v) => set({ name: v })} options={d.summary.map((j) => ({ value: j.name, label: j.label }))} />
                <Select label="النتيجة" value={f.status} onChange={(v) => set({ status: v })} options={[{ value: "ok", label: "نجحت" }, { value: "failed", label: "فشلت" }]} />
              </div>
              <DataTable rows={d.results} empty={<EmptyState title="لا يوجد سجل تشغيل" text="سيظهر هنا بعد أول تشغيل لأحد الأوامر." />} columns={[
                { key: "label", label: "العملية" },
                { key: "status", label: "النتيجة", render: (j) => <Badge tone={j.status === "ok" ? "ok" : "bad"}>{j.status === "ok" ? "نجحت" : "فشلت"}</Badge> },
                { key: "started_at", label: "البداية", render: (j) => dt(j.started_at) },
                { key: "duration_ms", label: "المدة", render: (j) => msText(j.duration_ms) },
                { key: "processed", label: "معالجة", render: (j) => num(j.processed) },
                { key: "failed_items", label: "فاشلة", render: (j) => num(j.failed_items) },
                { key: "error", label: "الخطأ", render: (j) => j.error || "—" },
              ]} />
              <Pager page={d.page} pages={d.pages} count={d.count} onPage={setPage} />
            </Card>
          </>
        )}
      </Async>
    </>
  );
}

/* ================================================================== settings */
export function SettingsPage() {
  const can = useCan();
  const toast = useToast();
  const api = useApi(() => controlApi.settings(), []);
  const [tab, setTab] = useState("ticket_workflow");
  const [draft, setDraft] = useState({});
  const [errs, setErrs] = useState({});
  const [run, busy] = useAction();
  useEffect(() => {
    if (api.data) setDraft(Object.fromEntries(api.data.editable.map((s) => [s.key, String(s.value)])));
  }, [api.data]);
  const manage = can("settings.manage");
  const save = (group) =>
    run(async () => {
      setErrs({});
      const items = api.data.editable.filter((s) => s.group === group);
      const body = {};
      for (const s of items) if (draft[s.key] !== String(s.value)) body[s.key] = Number(draft[s.key]);
      if (!Object.keys(body).length) return toast("لا تغييرات للحفظ.");
      try {
        await controlApi.saveSettings(body);
        api.reload();
      } catch (e) {
        const f = {};
        Object.entries(e.fields || {}).forEach(([k, v]) => (f[k] = Array.isArray(v) ? v[0] : v));
        setErrs(f);
        throw e;
      }
    }, "تم حفظ الإعدادات");
  return (
    <>
      <PageHead title="الإعدادات" desc="كل إعداد له وصف وحدود، ويُسجَّل كل تغيير في سجل التدقيق. الإعدادات المعروضة هنا تُستخدم فعليًا في منطق الدعم والمراقبة." crumbs={[{ label: "النظام" }, { label: "الإعدادات" }]} />
      <Card pad={false}>
        <Tabs value={tab} onChange={setTab} tabs={[{ key: "ticket_workflow", label: "سير عمل التذاكر" }, { key: "monitoring", label: "المراقبة والتنبيهات" }, { key: "security", label: "الأمان والجلسات" }, { key: "other", label: "الفريق والإشعارات والتصنيفات" }]} />
        <Async api={api} rows={6}>
          {(d) => (
            <div className="pad">
              {["ticket_workflow", "monitoring"].includes(tab) && (
                <div style={{ display: "grid", gap: 14, maxWidth: 720 }}>
                  {!manage && <Banner tone="info">عرض فقط. تعديل الإعدادات يتطلب صلاحية «تعديل إعدادات المنصة».</Banner>}
                  {d.editable.filter((s) => s.group === tab).map((s) => (
                    <Field key={s.key} label={s.label} hint={`${s.description} (من ${num(s.min)} إلى ${num(s.max)}، الافتراضي ${num(s.default)})`} error={errs[s.key]}>
                      <input className="cc-input" style={{ width: 160 }} type="number" inputMode="numeric" min={s.min} max={s.max} value={draft[s.key] ?? ""} disabled={!manage} onChange={(e) => setDraft({ ...draft, [s.key]: e.target.value })} />
                    </Field>
                  ))}
                  {manage && <div><Btn loading={busy} loadingText="جارٍ الحفظ…" onClick={() => save(tab)}><Save size={15} /> حفظ</Btn></div>}
                </div>
              )}
              {tab === "security" && (
                <div style={{ display: "grid", gap: 12, maxWidth: 720 }}>
                  <Banner tone="info">قيم تُضبط على مستوى نشر الخادم (متغيرات البيئة) ولا يغيّرها أحد من الواجهة، حمايةً من تعطيل الأمان بالخطأ.</Banner>
                  <DataTable rowKey="key" rows={d.readonly} columns={[{ key: "label", label: "الإعداد", render: (s) => (<><div className="strong">{s.label}</div><div className="sub">{s.description}</div></>) }, { key: "value", label: "القيمة", render: (s) => `${s.value ?? "—"} ${s.unit || ""}` }]} />
                </div>
              )}
              {tab === "other" && (
                <div className="cc-grid c3">
                  <Card title="تصنيفات التذاكر"><p className="sub">إضافة التصنيفات وتعطيلها.</p><Link className="abtn abtn-secondary" to="/team/support/categories">إدارة التصنيفات</Link></Card>
                  <Card title="قوالب الإشعارات"><p className="sub">قوالب الإشعارات التشغيلية الجاهزة.</p><Link className="abtn abtn-secondary" to="/team/notifications">إدارة القوالب</Link></Card>
                  <Card title="الفريق والأدوار"><p className="sub">أعضاء الفريق والصلاحيات.</p><Link className="abtn abtn-secondary" to="/team/roles">الأدوار والصلاحيات</Link></Card>
                </div>
              )}
            </div>
          )}
        </Async>
      </Card>
    </>
  );
}
