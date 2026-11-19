import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Download, Plus, Send, Trash2 } from "lucide-react";
import { Btn, Banner, Field, Modal, TextInput } from "../../auth/ui.jsx";
import { controlApi } from "../../lib/controlApi.js";
import { AI_KIND, AI_STATUS, DELIVERY, NOTICE_DELIVERY, PAYMENT_STATUS, SUB_STATE } from "../labels.js";
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
  BarChart,
  LineChart,
  PageHead,
  Pager,
  RangePicker,
  SERIES,
  SearchBox,
  Select,
  Skeleton,
  StatusBadge,
  Tabs,
  TextArea,
  dt,
  errText,
  fieldErrors,
  money,
  msText,
  num,
  opts,
  rangeParams,
  secsText,
  tableOf,
  toSeries,
  useAction,
  useApi,
  useCan,
  useDebounce,
  useFilters,
  useSort,
  useToast,
} from "../kit.jsx";

/* ================================================================== finance */
export function FinanceOverviewPage() {
  const [range, setRange] = useState({ range: "30d" });
  const p = rangeParams(range);
  const api = useApi(() => controlApi.financeOverview(p), [JSON.stringify(p)]);
  const plans = useApi(() => controlApi.plans(), []);
  return (
    <>
      <PageHead title="الإدارة المالية" desc="اشتراكات المعلّمين ومعاملات الدفع. للقراءة فقط: لا يمكن من هنا تغيير حالة أي دفعة؛ النجاح يأتي فقط من التحقق الموثوق من مزوّد الدفع." crumbs={[{ label: "العمليات التجارية" }, { label: "المالية" }]}>
        <RangePicker value={range} onChange={setRange} />
      </PageHead>
      <Async api={api} rows={8}>
        {(d) => (
          <>
            <div className="cc-grid kpi">
              {[["إجمالي المعاملات", d.total, "/team/finance/transactions"], ["ناجحة", d.succeeded, "/team/finance/transactions?status=succeeded"], ["فاشلة", d.failed, "/team/finance/transactions?status=failed", "bad"], ["معلّقة (الآن)", d.pending, "/team/finance/transactions?status=pending", "warn"], ["تحتاج مطابقة", d.unknown, "/team/finance/issues", "warn"], ["اشتراكات نشطة", d.subscriptions.active, "/team/finance/subscriptions?state=active"], ["اشتراكات منتهية", d.subscriptions.expired, "/team/finance/subscriptions?state=expired"], ["متأخرة السداد", d.subscriptions.past_due, "/team/finance/subscriptions?state=past_due", "warn"]].map(([k, v, to, tone]) => (
                <Link key={k} to={to} className={"cc-card kpi " + (tone || "")}><div className="top"><span>{k}</span></div><div className="val">{num(v)}</div></Link>
              ))}
              <div className="cc-card kpi"><div className="top"><span>إيراد الفترة</span></div>{d.revenue.period.length ? d.revenue.period.map((r) => <div className="val" key={r.currency}>{money(r.amount, r.currency)}</div>) : <div className="val">{money(0)}</div>}<div className="cmp">معاملات ناجحة فقط</div></div>
              <div className="cc-card kpi"><div className="top"><span>الإيراد الكلي</span></div>{d.revenue.all_time.length ? d.revenue.all_time.map((r) => <div className="val" key={r.currency}>{money(r.amount, r.currency)}</div>) : <div className="val">{money(0)}</div>}</div>
            </div>
            <div className="cc-grid c2">
              <ChartCard title="الإيراد اليومي" table={tableOf(["الإيراد"], [{ points: d.charts.revenue }])}>
                <BarChart series={toSeries([["الإيراد", SERIES.navy, d.charts.revenue]])} format={(v) => money(v)} />
              </ChartCard>
              <ChartCard title="المعاملات: ناجحة وفاشلة" legend={[{ label: "ناجحة", color: SERIES.c1 }, { label: "فاشلة", color: SERIES.c2 }]} table={tableOf(["ناجحة", "فاشلة"], [{ points: d.charts.succeeded }, { points: d.charts.failed }])}>
                <BarChart series={toSeries([["ناجحة", SERIES.c1, d.charts.succeeded], ["فاشلة", SERIES.c2, d.charts.failed]])} />
              </ChartCard>
            </div>
          </>
        )}
      </Async>
      <Card title="الباقات" pad={false}>
        <Async api={plans} rows={3}>
          {(rows) => (
            <DataTable rows={rows} columns={[{ key: "name", label: "الباقة", render: (p) => <span className="strong">{p.name}</span> }, { key: "price", label: "السعر", render: (p) => money(p.price, p.currency) }, { key: "period_days", label: "مدة الفترة", render: (p) => `${num(p.period_days)} يومًا` }, { key: "max_students", label: "حد الطلاب", render: (p) => (p.max_students ? num(p.max_students) : "بلا حد") }, { key: "active_subscriptions", label: "اشتراكات نشطة", render: (p) => num(p.active_subscriptions) }, { key: "is_active", label: "الحالة", render: (p) => <Badge tone={p.is_active ? "ok" : "plain"}>{p.is_active ? "متاحة" : "غير متاحة"}</Badge> }]} />
          )}
        </Async>
      </Card>
    </>
  );
}

export function TransactionsPage() {
  const nav = useNavigate();
  const toast = useToast();
  const [sp] = useSearchParams();
  const [f, set, setPage] = useFilters({ search: "", status: sp.get("status") || "", from: "", to: "" });
  const [sort, toggle, sortParam] = useSort({ key: "created_at", dir: "desc" });
  const search = useDebounce(f.search);
  const params = { ...f, search, sort: sortParam };
  const api = useApi(() => controlApi.transactions(params), [JSON.stringify(params)]);
  return (
    <>
      <PageHead title="المعاملات" desc="محاولات الدفع كما سجّلها النظام. لا تظهر هنا أي بيانات بطاقات." crumbs={[{ label: "العمليات التجارية" }, { label: "المعاملات" }]}>
        <Btn variant="secondary" onClick={() => controlApi.exportTransactions({ ...params, page: undefined }).catch((e) => toast(errText(e), "err"))}><Download size={15} /> تصدير CSV</Btn>
      </PageHead>
      <Card pad={false}>
        <div className="cc-tools">
          <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="رقم المعاملة، المرجع، البيئة أو المعلّم…" />
          <Select label="الحالة" value={f.status} onChange={(v) => set({ status: v })} options={opts({ ...PAYMENT_STATUS, pending: ["معلّقة (كل الحالات غير النهائية)"] })} />
          <label className="cc-field"><span>من</span><input type="date" className="cc-input" value={f.from} onChange={(e) => set({ from: e.target.value })} /></label>
          <label className="cc-field"><span>إلى</span><input type="date" className="cc-input" value={f.to} onChange={(e) => set({ to: e.target.value })} /></label>
        </div>
        <Async api={api}>
          {(d) => (
            <>
              <DataTable rows={d.results} sort={sort} onSort={toggle} onRow={(a) => nav(`/team/environments/${a.environment.id}`)} empty={<EmptyState title="لا توجد معاملات" />} columns={[
                { key: "transaction_id", label: "المعاملة", render: (a) => <span className="strong ltr">{a.transaction_id}</span> },
                { key: "environment", label: "البيئة / المعلّم", render: (a) => (<><div>{a.environment.name}</div><div className="sub">{a.owner}</div></>) },
                { key: "amount", label: "المبلغ", sort: "amount", render: (a) => money(a.amount, a.currency) },
                { key: "kind", label: "النوع", render: (a) => (a.kind === "renewal" ? "تجديد" : "اشتراك") },
                { key: "plan", label: "الباقة", render: (a) => a.plan || "—" },
                { key: "provider", label: "المزوّد" },
                { key: "status", label: "الحالة", sort: "status", render: (a) => <StatusBadge map={PAYMENT_STATUS} value={a.status} /> },
                { key: "reference", label: "المرجع", ltr: true, render: (a) => a.reference || "—" },
                { key: "created_at", label: "التاريخ", sort: "created_at", render: (a) => dt(a.created_at) },
              ]} />
              <Pager page={d.page} pages={d.pages} count={d.count} onPage={setPage} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

export function SubscriptionsPage() {
  const [sp] = useSearchParams();
  const [f, set, setPage] = useFilters({ search: "", state: sp.get("state") || "" });
  const search = useDebounce(f.search);
  const params = { ...f, search };
  const api = useApi(() => controlApi.subscriptions(params), [JSON.stringify(params)]);
  const RENEW = { auto: "تجديد تلقائي", manual: "تجديد يدوي", canceled: "لن يتجدد" };
  return (
    <>
      <PageHead title="الاشتراكات" desc="حالة اشتراك كل بيئة، وفترته الحالية، وهل سيتجدد تلقائيًا." crumbs={[{ label: "العمليات التجارية" }, { label: "الاشتراكات" }]} />
      <Card pad={false}>
        <div className="cc-tools">
          <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="اسم البيئة أو المعلّم…" />
          <Select label="الحالة" value={f.state} onChange={(v) => set({ state: v })} options={opts(SUB_STATE)} />
        </div>
        <Async api={api}>
          {(d) => (
            <>
              <DataTable rows={d.results} empty={<EmptyState title="لا توجد اشتراكات" />} columns={[
                { key: "environment", label: "البيئة", render: (s) => (<><Link className="strong" to={`/team/environments/${s.environment.id}`}>{s.environment.name}</Link><div className="sub">{s.owner}</div></>) },
                { key: "plan", label: "الباقة", render: (s) => s.plan || "—" },
                { key: "state", label: "الحالة", render: (s) => <StatusBadge map={SUB_STATE} value={s.state} /> },
                { key: "period_start", label: "بداية الفترة", render: (s) => dt(s.period_start) },
                { key: "period_end", label: "نهاية الفترة", render: (s) => dt(s.period_end) },
                { key: "trial_ends_at", label: "نهاية التجربة", render: (s) => (s.trial_ends_at ? dt(s.trial_ends_at) : "—") },
                { key: "renewal", label: "التجديد", render: (s) => RENEW[s.renewal] },
              ]} />
              <Pager page={d.page} pages={d.pages} count={d.count} onPage={setPage} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

export function PaymentIssuesPage() {
  const api = useApi(() => controlApi.paymentIssues(), []);
  const attemptCols = [
    { key: "transaction_id", label: "المعاملة", render: (a) => <span className="strong ltr">{a.transaction_id}</span> },
    { key: "environment", label: "البيئة", render: (a) => <Link to={`/team/environments/${a.environment.id}`} style={{ textDecoration: "underline" }}>{a.environment.name}</Link> },
    { key: "amount", label: "المبلغ", render: (a) => money(a.amount, a.currency) },
    { key: "status", label: "الحالة", render: (a) => <StatusBadge map={PAYMENT_STATUS} value={a.status} /> },
    { key: "updated_at", label: "آخر تحديث", render: (a) => dt(a.updated_at) },
    { key: "tickets", label: "تذاكر البيئة", render: (a) => (a.tickets.length ? a.tickets.map((t) => <Link key={t.id} to={`/team/support/tickets/${t.id}`} style={{ textDecoration: "underline", marginInlineEnd: 6 }}>{t.number}</Link>) : "—") },
  ];
  return (
    <>
      <PageHead title="مشكلات الدفع" desc="عمليات فاشلة أو عالقة أو تحتاج مطابقة، وأحداث تعذّر التحقق منها. المطابقة تتم بالعمليات الخلفية الموثوقة، لا يدويًا من هنا." crumbs={[{ label: "العمليات التجارية" }, { label: "مشكلات الدفع" }]} />
      <Async api={api} rows={8}>
        {(d) => (
          <>
            <Banner tone="info">تُعرض الأحداث خلال آخر {num(d.window_days)} أيام (قابلة للتعديل من الإعدادات).</Banner>
            <Card title={`عمليات فاشلة (${num(d.failed.length)})`} pad={false}><DataTable rows={d.failed} columns={attemptCols} empty={<EmptyState title="لا توجد عمليات فاشلة" />} /></Card>
            <Card title={`تحتاج مطابقة (${num(d.needs_reconciliation.length)})`} sub="النتيجة غامضة (مهلة أو انقطاع). لا تُعدّ ناجحة ولا فاشلة حتى تُحسم." pad={false}><DataTable rows={d.needs_reconciliation} columns={attemptCols} empty={<EmptyState title="لا شيء يحتاج مطابقة" />} /></Card>
            <Card title={`معلّقة أكثر من 30 دقيقة (${num(d.pending_too_long.length)})`} pad={false}><DataTable rows={d.pending_too_long} columns={attemptCols} empty={<EmptyState title="لا توجد عمليات عالقة" />} /></Card>
            <Card title={`مشكلات التحقق من الأحداث (${num(d.verification.length)})`} sub="أحداث من مزوّد الدفع لم يتحقق توقيعها أو تعذّر تطبيقها" pad={false}>
              <DataTable rows={d.verification} empty={<EmptyState title="لا توجد مشكلات تحقق" />} columns={[
                { key: "event_type", label: "الحدث" }, { key: "transaction_status", label: "حالة المعاملة", render: (e) => e.transaction_status || "—" },
                { key: "signature_valid", label: "التوقيع", render: (e) => <Badge tone={e.signature_valid ? "ok" : "bad"}>{e.signature_valid ? "سليم" : "غير صالح"}</Badge> },
                { key: "processing_status", label: "المعالجة" }, { key: "attempts", label: "المحاولات", render: (e) => num(e.attempts) },
                { key: "error", label: "الخطأ", render: (e) => e.error || "—" }, { key: "received_at", label: "الاستلام", render: (e) => dt(e.received_at) },
              ]} />
            </Card>
          </>
        )}
      </Async>
    </>
  );
}

/* ================================================================== AI */
export function AiPage() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [range, setRange] = useState({ range: "30d" });
  const rp = rangeParams(range);
  const ov = useApi(() => controlApi.aiOverview(rp), [JSON.stringify(rp)]);
  const [f, set, setPage] = useFilters({ search: "", kind: "", status: sp.get("status") || "", failure_category: "", slow: "", from: "", to: "" });
  const search = useDebounce(f.search);
  const params = { ...f, search };
  const list = useApi(() => controlApi.aiOperations(params), [JSON.stringify(params)]);
  return (
    <>
      <PageHead title="عمليات الذكاء الاصطناعي" desc="مراقبة العمليات الفعلية: توليد الاختبارات، المساعد الدراسي واقتراح حالة الطالب. لا تُعرض أي أسئلة أو إجابات أو محتوى خاص." crumbs={[{ label: "العمليات التجارية" }, { label: "الذكاء الاصطناعي" }]}>
        <RangePicker value={range} onChange={setRange} />
      </PageHead>
      <Async api={ov} rows={5}>
        {(d) => (
          <>
            <div className="cc-grid kpi">
              {[["إجمالي العمليات", num(d.total)], ["ناجحة", num(d.completed)], ["فاشلة", num(d.failed), "bad"], ["قيد التنفيذ", num(d.pending), "warn"], ["معدل النجاح", d.success_rate === null ? "—" : `${num(d.success_rate)}%`], ["معدل الفشل", d.failure_rate === null ? "—" : `${num(d.failure_rate)}%`], ["متوسط زمن التنفيذ", secsText(d.avg_seconds)], ["عمليات بطيئة", num(d.slow_count), "warn"]].map(([k, v, tone]) => (
                <div className={"cc-card kpi " + (tone || "")} key={k}><div className="top"><span>{k}</span></div><div className="val">{v}</div></div>
              ))}
            </div>
            <Banner tone="info">المزوّد الحالي: <b>{d.provider === "llm" ? "نموذج حقيقي" : "بديل مبسّط (stub)"}</b>. الأرقام تعكس ما سجّلته العمليات فقط؛ لا نفترض نجاح أي عملية لم يؤكدها الخادم.</Banner>
            <div className="cc-grid c2">
              <ChartCard title="نجاح مقابل فشل" legend={[{ label: "ناجحة", color: SERIES.c1 }, { label: "فاشلة", color: SERIES.c2 }]} table={tableOf(["ناجحة", "فاشلة"], [{ points: d.charts.success }, { points: d.charts.failed }])}>
                <BarChart series={toSeries([["ناجحة", SERIES.c1, d.charts.success], ["فاشلة", SERIES.c2, d.charts.failed]])} />
              </ChartCard>
              <div style={{ display: "grid", gap: 16 }}>
                <Card title="حسب النوع"><HBars rows={d.by_kind.map((r) => ({ name: r.label, count: r.count }))} /></Card>
                <Card title="أسباب الفشل"><HBars color={SERIES.c2} rows={d.failure_categories.map((r) => ({ name: r.category, count: r.count }))} empty="لا إخفاقات في هذه الفترة." /></Card>
              </div>
            </div>
            {d.repeated_failures.length > 0 && (
              <Card title="مستخدمون تكرر فشل عملياتهم" sub="3 إخفاقات أو أكثر في الفترة" pad={false}>
                <DataTable rowKey="user_id" rows={d.repeated_failures} onRow={(r) => nav(`/team/users/${r.user_id}`)} columns={[{ key: "name", label: "المستخدم" }, { key: "count", label: "عدد الإخفاقات", render: (r) => num(r.count) }]} />
              </Card>
            )}
          </>
        )}
      </Async>
      <Card title="كل العمليات" pad={false}>
        <div className="cc-tools">
          <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="مستخدم، بيئة أو نص الخطأ…" />
          <Select label="النوع" value={f.kind} onChange={(v) => set({ kind: v })} options={opts(AI_KIND)} />
          <Select label="الحالة" value={f.status} onChange={(v) => set({ status: v })} options={opts(AI_STATUS)} />
          <Select label="سبب الفشل" value={f.failure_category} onChange={(v) => set({ failure_category: v, status: v ? "failed" : f.status })} options={(ov.data?.failure_categories || []).map((c) => ({ value: c.category, label: c.category }))} />
          <Select label="الزمن" value={f.slow} onChange={(v) => set({ slow: v })} options={[{ value: "1", label: "البطيئة فقط" }]} />
          <label className="cc-field"><span>من</span><input type="date" className="cc-input" value={f.from} onChange={(e) => set({ from: e.target.value })} /></label>
          <label className="cc-field"><span>إلى</span><input type="date" className="cc-input" value={f.to} onChange={(e) => set({ to: e.target.value })} /></label>
        </div>
        <Async api={list}>
          {(d) => (
            <>
              <DataTable rows={d.results} onRow={(o) => nav(`/team/ai/${o.id}`)} empty={<EmptyState title="لا توجد عمليات" />} columns={[
                { key: "id", label: "المعرّف", className: "cc-num" },
                { key: "user", label: "المستخدم", render: (o) => (<><div className="strong">{o.user.name}</div><div className="sub">{o.environment.name}</div></>) },
                { key: "kind", label: "النوع", render: (o) => o.kind_label },
                { key: "status", label: "الحالة", render: (o) => <StatusBadge map={AI_STATUS} value={o.status} /> },
                { key: "created_at", label: "الإنشاء", render: (o) => dt(o.created_at) },
                { key: "duration_seconds", label: "المدة", render: (o) => (<>{secsText(o.duration_seconds)} {o.slow && <Badge tone="warn">بطيئة</Badge>}</>) },
                { key: "error", label: "الخطأ", render: (o) => (o.status === "failed" ? <span>{o.failure_category && <Badge tone="bad">{o.failure_category}</Badge>} <span className="sub">{o.error}</span></span> : "—") },
              ]} />
              <Pager page={d.page} pages={d.pages} count={d.count} onPage={setPage} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

export function AiDetailPage() {
  const { id } = useParams();
  const api = useApi(() => controlApi.aiOperation(id), [id]);
  const TL = { created: "أُنشئت", started: "بدأت المعالجة", completed: "اكتملت", ended: "انتهت (فشل)" };
  return (
    <>
      <PageHead title={`عملية ذكاء اصطناعي #${id}`} crumbs={[{ label: "العمليات التجارية" }, { label: "الذكاء الاصطناعي", to: "/team/ai" }, { label: `#${id}` }]} />
      <Async api={api} rows={8}>
        {(o) => (
          <div className="cc-grid c2">
            <Card title="معلومات العملية">
              <KV items={[["النوع", o.kind_label], ["الحالة", <StatusBadge key="s" map={AI_STATUS} value={o.status} />], ["المستخدم", <Link key="u" to={`/team/users/${o.user.id}`} style={{ textDecoration: "underline" }}>{o.user.name}</Link>], ["البيئة", <Link key="e" to={`/team/environments/${o.environment.id}`} style={{ textDecoration: "underline" }}>{o.environment.name}</Link>], ["المدة الكلية", secsText(o.duration_seconds)], o.failure_category ? ["فئة الفشل", <Badge key="f" tone="bad">{o.failure_category}</Badge>] : null, o.error ? ["رسالة الخطأ", o.error] : null]} />
            </Card>
            <Card title="الجدول الزمني" pad={false}>
              <div className="timeline">{o.timeline.map((t) => (<div className="ev" key={t.key}><span /><div>{TL[t.key]}<div className="when">{t.at ? dt(t.at) : "لم يحدث"}</div></div></div>))}</div>
            </Card>
            <Card title="أزمنة المراحل" sub="من بيانات التنفيذ المسجّلة">
              {Object.keys(o.timings_ms).length === 0 ? <p className="sub">لا توجد أزمنة مسجّلة لهذه العملية.</p> : (
                <KV items={[["فحص المحتوى", o.timings_ms.content_check !== undefined ? msText(o.timings_ms.content_check) : "—"], ["التوليد", o.timings_ms.generation !== undefined ? msText(o.timings_ms.generation) : "—"], ["الإجمالي", o.timings_ms.total !== undefined ? msText(o.timings_ms.total) : "—"]]} />
              )}
            </Card>
            <Card title="سياق الطلب (بدون محتوى خاص)">
              <KV items={[["مرتبط بطالب", o.context.has_student ? "نعم" : "لا"], ["مرتبط بمحتوى تعليمي", o.context.has_content ? "نعم" : "لا"], ["طول السؤال", `${num(o.context.prompt_chars)} حرفًا`], ["طول الإجابة", `${num(o.context.result_chars)} حرفًا`], ["الشهر", o.context.month || "—"]]} />
              <p className="sub" style={{ marginTop: 10 }}>نص الأسئلة والإجابات والدروس لا يُعرض لحماية الخصوصية.</p>
            </Card>
            <Card title="بيانات تقنية" className="">
              {Object.keys(o.metadata).length === 0 ? <p className="sub">لا توجد بيانات تقنية.</p> : <KV items={Object.entries(o.metadata).map(([k, v]) => [k, <bdi dir="ltr" key={k}>{typeof v === "object" ? JSON.stringify(v) : String(v)}</bdi>])} />}
            </Card>
          </div>
        )}
      </Async>
    </>
  );
}

/* ================================================================== notifications */
function SendNotice({ onClose, onSent }) {
  const toast = useToast();
  const tpl = useApi(() => controlApi.templates(), []);
  const [form, setForm] = useState({ title: "", body: "", url: "/", audience: "teachers" });
  const [picked, setPicked] = useState([]);
  const [env, setEnv] = useState(null);
  const [q, setQ] = useState("");
  const term = useDebounce(q.trim());
  const people = useApi(() => controlApi.recipients(term, form.audience === "environment" ? "environment" : undefined), [term, form.audience], { skip: term.length < 2 || !["user", "users", "environment"].includes(form.audience) });
  const [errs, setErrs] = useState({});
  const [result, setResult] = useState(null);
  const [run, busy] = useAction();
  const multi = form.audience === "users";
  const send = () =>
    run(async () => {
      const bad = {};
      if (form.title.trim().length < 2) bad.title = "اكتب عنوان الإشعار.";
      if (["user", "users"].includes(form.audience) && !picked.length) bad.user_ids = "ابحث عن مستخدم واحد على الأقل واخترته.";
      if (form.audience === "environment" && !env) bad.environment = "ابحث عن بيئة واخترها.";
      setErrs(bad);
      if (Object.keys(bad).length) return false;
      const body = { ...form };
      if (["user", "users"].includes(form.audience)) body.user_ids = picked.map((p) => p.id);
      if (form.audience === "environment") body.environment = env?.id;
      try {
        const r = await controlApi.sendNotice(body);
        setResult(r);
        onSent();
      } catch (e) {
        // the shared action wrapper already toasts the server's sentence; here it only needs to mark the field
        setErrs(e.code === "push_not_configured" ? { audience: errText(e) } : fieldErrors(e));
        throw e;
      }
    });
  return (
    <Modal size="lg" title="إرسال إشعار منصّة" text="يصل عبر Web Push إلى الأجهزة التي فعّلت الإشعارات فقط. تسليم الخدمة للرسالة لا يضمن ظهورها على الجهاز." onClose={onClose}
      footer={result ? <Btn onClick={onClose}>إغلاق</Btn> : <><Btn variant="ghost" onClick={onClose}>إلغاء</Btn><Btn loading={busy} loadingText="جارٍ الإرسال…" onClick={send}><Send size={15} /> إرسال</Btn></>}>
      {result ? (
        <div style={{ display: "grid", gap: 10 }}>
          <Banner tone="info">أُنشئ الإشعار لـ {num(result.recipients)} مستلم.</Banner>
          <KV items={[["سُلّم لخدمة الدفع", num(result.sent)], ["فشل", num(result.failed)], ["بلا جهاز مفعّل", num(result.no_device)], ["في الانتظار", num(result.queued)]]} />
          {result.queued > 0 && <p className="sub">المتبقي سيُرسل عبر العملية الخلفية process_platform_notices.</p>}
        </div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {tpl.data?.filter((t) => t.is_active).length > 0 && (
            <Field label="قالب جاهز (اختياري)">
              <Select all="— بدون —" value="" onChange={(id) => { const t = tpl.data.find((x) => String(x.id) === id); if (t) setForm({ ...form, title: t.title, body: t.body }); }} options={tpl.data.filter((t) => t.is_active).map((t) => ({ value: t.id, label: t.name }))} />
            </Field>
          )}
          <Field label="المستلمون" required error={errs.audience || errs.user_ids || errs.environment}>
            <Select all={null} value={form.audience} onChange={(v) => { setForm({ ...form, audience: v }); setPicked([]); setEnv(null); }} options={[{ value: "teachers", label: "كل المعلّمين" }, { value: "students", label: "كل الطلاب" }, { value: "environment", label: "بيئة محددة (المعلّم وطلابه)" }, { value: "user", label: "مستخدم محدد" }, { value: "users", label: "مستخدمون محددون" }]} />
          </Field>
          {["user", "users", "environment"].includes(form.audience) && (
            <div style={{ display: "grid", gap: 6 }}>
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={form.audience === "environment" ? "ابحث عن بيئة…" : "ابحث بالاسم أو الهاتف…"} aria-label="بحث عن مستلم" />
              {people.data?.map((p) => (
                <button key={p.id} type="button" className="abtn abtn-secondary" style={{ justifyContent: "space-between" }} onClick={() => { if (form.audience === "environment") setEnv(p); else setPicked(multi ? (picked.some((x) => x.id === p.id) ? picked : [...picked, p]) : [p]); setQ(""); }}>
                  <span>{p.name}</span><span className="sub">{p.owner || p.phone}</span>
                </button>
              ))}
              <div className="atts">
                {env && <span className="cc-att">{env.name}</span>}
                {picked.map((p) => <span className="cc-att" key={p.id}>{p.name}<button type="button" aria-label="إزالة" onClick={() => setPicked(picked.filter((x) => x.id !== p.id))} style={{ all: "unset", cursor: "pointer" }}>×</button></span>)}
              </div>
            </div>
          )}
          <Field label="العنوان" required error={errs.title}><TextInput value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} maxLength={150} /></Field>
          <Field label="النص" error={errs.body}><TextArea rows={3} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} maxLength={300} /></Field>
          <Field label="الرابط عند الضغط" hint="مسار داخل التطبيق فقط، مثل /app أو /learn" error={errs.url}><TextInput ltr value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></Field>
        </div>
      )}
    </Modal>
  );
}

function TemplateForm({ tpl, onClose, onSaved }) {
  const [form, setForm] = useState({ name: tpl?.name || "", title: tpl?.title || "", body: tpl?.body || "" });
  const [errs, setErrs] = useState({});
  const [run, busy] = useAction();
  return (
    <Modal title={tpl ? "تعديل القالب" : "قالب جديد"} onClose={onClose} footer={<><Btn variant="ghost" onClick={onClose}>إلغاء</Btn><Btn loading={busy} loadingText="جارٍ الحفظ…" onClick={() => run(async () => { const bad = {}; if (!form.name.trim()) bad.name = "اكتب اسم القالب."; if (!form.title.trim()) bad.title = "اكتب عنوان الإشعار."; setErrs(bad); if (Object.keys(bad).length) return false; try { await (tpl ? controlApi.updateTemplate(tpl.id, form) : controlApi.createTemplate(form)); onSaved(); onClose(); } catch (e) { setErrs(fieldErrors(e)); throw e; } }, "تم حفظ القالب")}>حفظ</Btn></>}>
      <div style={{ display: "grid", gap: 8 }}>
        <Field label="اسم القالب" required error={errs.name}><TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={80} /></Field>
        <Field label="عنوان الإشعار" required error={errs.title}><TextInput value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} maxLength={150} /></Field>
        <Field label="النص" error={errs.body}><TextArea rows={3} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} maxLength={300} /></Field>
      </div>
    </Modal>
  );
}

export function NotificationsPage() {
  const can = useCan();
  const toast = useToast();
  const [tab, setTab] = useState("history");
  const [range, setRange] = useState({ range: "30d" });
  const rp = rangeParams(range);
  const ov = useApi(() => controlApi.notificationOverview(rp), [JSON.stringify(rp)]);
  const [f, set, setPage] = useFilters({ search: "", type: "", status: "", from: "", to: "" });
  const search = useDebounce(f.search);
  const params = { ...f, search };
  const list = useApi(() => controlApi.notifications(params), [JSON.stringify(params)], { skip: tab !== "history" });
  const notices = useApi(() => controlApi.platformNotices(), [], { skip: tab !== "platform" });
  const templates = useApi(() => controlApi.templates(), [], { skip: tab !== "templates" });
  const [sending, setSending] = useState(false);
  const [detail, setDetail] = useState(null);
  const [tplEdit, setTplEdit] = useState(undefined);
  const [tplDel, setTplDel] = useState(null);
  const detailApi = useApi(() => controlApi.notification(detail), [detail], { skip: !detail });
  return (
    <>
      <PageHead title="الإشعارات" desc="سجل إشعارات المعلّمين لطلابهم، وإشعارات المنصّة التي يرسلها الفريق. «سُلّم لخدمة الدفع» تعني قبول الخدمة للرسالة، لا ظهورها على الجهاز." crumbs={[{ label: "العمليات التجارية" }, { label: "الإشعارات" }]}>
        <RangePicker value={range} onChange={setRange} />
        {can("notifications.manage") && <Btn onClick={() => setSending(true)}><Send size={15} /> إشعار جديد</Btn>}
      </PageHead>
      <Async api={ov} rows={3}>
        {(d) => (
          <>
            <div className="cc-grid kpi">
              {[["الإجمالي", d.total], ["سُلّمت لخدمة الدفع", d.sent], ["قيد الإرسال", d.pending, "warn"], ["فشلت", d.failed, "bad"], ["قُرئت (مؤكَّد)", d.read], ["إشعارات المنصّة", d.platform_notices], ["أجهزة مفعّلة", d.push.subscribed_devices]].map(([k, v, tone]) => (
                <div className={"cc-card kpi " + (tone || "")} key={k}><div className="top"><span>{k}</span></div><div className="val">{num(v)}</div></div>
              ))}
            </div>
            {!d.push.configured && <Banner tone="err">مفاتيح Web Push (VAPID) غير مضبوطة على الخادم: لن يُرسل أي إشعار دفع حتى تُضبط.</Banner>}
            <div className="cc-grid c2">
              <ChartCard title="الإرسال اليومي" legend={[{ label: "سُلّمت", color: SERIES.c1 }, { label: "فشلت", color: SERIES.c2 }]} table={tableOf(["سُلّمت", "فشلت"], [{ points: d.charts.sent }, { points: d.charts.failed }])}>
                <BarChart series={toSeries([["سُلّمت", SERIES.c1, d.charts.sent], ["فشلت", SERIES.c2, d.charts.failed]])} />
              </ChartCard>
              <Card title="حسب النوع"><HBars rows={d.by_type.map((r) => ({ name: r.label, count: r.count }))} /></Card>
            </div>
          </>
        )}
      </Async>
      <Card pad={false}>
        <Tabs value={tab} onChange={setTab} tabs={[{ key: "history", label: "سجل الإشعارات" }, { key: "platform", label: "إشعارات المنصّة" }, { key: "templates", label: "القوالب" }]} />
        {tab === "history" && (
          <>
            <div className="cc-tools">
              <SearchBox value={f.search} onChange={(v) => set({ search: v })} placeholder="العنوان أو المستلم…" />
              <Select label="النوع" value={f.type} onChange={(v) => set({ type: v })} options={(ov.data?.by_type || []).map((t) => ({ value: t.type, label: t.label }))} />
              <Select label="الحالة" value={f.status} onChange={(v) => set({ status: v })} options={opts(DELIVERY)} />
              <label className="cc-field"><span>من</span><input type="date" className="cc-input" value={f.from} onChange={(e) => set({ from: e.target.value })} /></label>
              <label className="cc-field"><span>إلى</span><input type="date" className="cc-input" value={f.to} onChange={(e) => set({ to: e.target.value })} /></label>
            </div>
            <Async api={list}>
              {(d) => (
                <>
                  <DataTable rows={d.results} onRow={(n) => setDetail(n.id)} empty={<EmptyState title="لا توجد إشعارات" />} columns={[
                    { key: "title", label: "الإشعار", render: (n) => (<><div className="strong">{n.title}</div><div className="sub">{n.type_label}</div></>) },
                    { key: "recipient", label: "المستلم", render: (n) => n.recipient.name },
                    { key: "environment", label: "البيئة", render: (n) => n.environment.name },
                    { key: "status", label: "الحالة", render: (n) => <StatusBadge map={DELIVERY} value={n.status} /> },
                    { key: "confirmed_read", label: "قُرئ", render: (n) => (n.confirmed_read ? <Badge tone="ok">نعم</Badge> : "—") },
                    { key: "created_at", label: "التاريخ", render: (n) => dt(n.created_at) },
                  ]} />
                  <Pager page={d.page} pages={d.pages} count={d.count} onPage={setPage} />
                </>
              )}
            </Async>
          </>
        )}
        {tab === "platform" && (
          <Async api={notices}>
            {(d) => (
              <DataTable rows={d.results} empty={<EmptyState title="لم تُرسل إشعارات منصّة بعد" />} columns={[
                { key: "title", label: "الإشعار", render: (n) => (<><div className="strong">{n.title}</div><div className="sub">{n.body}</div></>) },
                { key: "audience", label: "المستلمون", render: (n) => `${n.audience_label}${n.environment ? `: ${n.environment}` : ""} (${num(n.recipients)})` },
                { key: "sent", label: "التسليم", render: (n) => (<span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><Badge tone="info">{NOTICE_DELIVERY.sent}: {num(n.sent)}</Badge>{n.failed > 0 && <Badge tone="bad">{NOTICE_DELIVERY.failed}: {num(n.failed)}</Badge>}{n.no_device > 0 && <Badge tone="plain">{NOTICE_DELIVERY.no_device}: {num(n.no_device)}</Badge>}{n.queued > 0 && <Badge tone="warn">{NOTICE_DELIVERY.queued}: {num(n.queued)}</Badge>}</span>) },
                { key: "sent_by", label: "المرسِل" }, { key: "created_at", label: "التاريخ", render: (n) => dt(n.created_at) },
              ]} />
            )}
          </Async>
        )}
        {tab === "templates" && (
          <>
            <div className="cc-tools">{can("notifications.manage") && <Btn onClick={() => setTplEdit(null)}><Plus size={15} /> قالب جديد</Btn>}</div>
            <Async api={templates}>
              {(rows) => (
                <DataTable rows={rows} empty={<EmptyState title="لا توجد قوالب" />} columns={[
                  { key: "name", label: "القالب", render: (t) => <span className="strong">{t.name}</span> }, { key: "title", label: "العنوان" }, { key: "body", label: "النص", render: (t) => t.body || "—" },
                  ...(can("notifications.manage") ? [{ key: "act", label: "", render: (t) => (<span className="cc-actions"><Btn variant="secondary" onClick={() => setTplEdit(t)}>تعديل</Btn><Btn variant="ghost" aria-label="حذف" onClick={() => setTplDel(t)}><Trash2 size={14} /></Btn></span>) }] : []),
                ]} />
              )}
            </Async>
          </>
        )}
      </Card>
      {sending && <SendNotice onClose={() => setSending(false)} onSent={() => { notices.reload(); ov.reload(); }} />}
      {detail && (
        <Modal title="تفاصيل الإشعار" onClose={() => setDetail(null)} footer={<Btn onClick={() => setDetail(null)}>إغلاق</Btn>}>
          <Async api={detailApi} rows={4}>
            {(n) => <KV items={[["العنوان", n.title], ["النص", n.body || "—"], ["النوع", n.type_label], ["المستلم", `${n.recipient.name}`], ["البيئة", n.environment.name], ["الحالة", <StatusBadge key="s" map={DELIVERY} value={n.status} />], ["الخطأ", n.error || "—"], ["أجهزة الدفع للمستلم", num(n.push_devices)], ["أُنشئ", dt(n.created_at)], ["سُلّم", dt(n.sent_at)], ["قُرئ", dt(n.read_at)]]} />}
          </Async>
        </Modal>
      )}
      {tplEdit !== undefined && <TemplateForm tpl={tplEdit} onClose={() => setTplEdit(undefined)} onSaved={templates.reload} />}
      {tplDel && <Confirm danger title={`حذف القالب «${tplDel.name}»`} confirmLabel="حذف" onClose={() => setTplDel(null)} onConfirm={async () => { try { await controlApi.deleteTemplate(tplDel.id); toast("حُذف القالب"); templates.reload(); } catch (e) { toast(errText(e), "err"); return false; } }} />}
    </>
  );
}
