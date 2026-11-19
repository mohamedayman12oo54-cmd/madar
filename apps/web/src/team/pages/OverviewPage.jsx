import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertOctagon,
  Bot,
  Building2,
  ChevronLeft,
  CircleCheck,
  CircleDollarSign,
  CircleX,
  Clock,
  GraduationCap,
  Inbox,
  LifeBuoy,
  ShieldAlert,
  UserRound,
  Users,
  UserCheck,
  Wallet,
  Activity as ActivityIcon,
} from "lucide-react";
import { controlApi } from "../../lib/controlApi.js";
import { ATTENTION, KPI } from "../labels.js";
import {
  Async,
  Card,
  ChartCard,
  EmptyState,
  HBars,
  LineChart,
  BarChart,
  PageHead,
  RangePicker,
  SERIES,
  Trend,
  ago,
  num,
  rangeParams,
  sumSeries,
  teamRel,
  tableOf,
  toSeries,
  useApi,
  useControl,
} from "../kit.jsx";

const ICON = {
  total_users: Users,
  active_users: UserCheck,
  total_teachers: GraduationCap,
  total_students: UserRound,
  total_environments: Building2,
  open_tickets: LifeBuoy,
  unassigned_tickets: Inbox,
  critical_complaints: AlertOctagon,
  ai_success: CircleCheck,
  ai_failed: CircleX,
  payments_success: CircleDollarSign,
  payments_pending: Clock,
};
const FEED_ICON = { user: Users, ticket: LifeBuoy, ticket_event: LifeBuoy, payment: Wallet, ai: Bot, admin: ShieldAlert };
// For these, a rise is bad news: the trend arrow is coloured accordingly.
const BAD_WHEN_UP = new Set(["ai_failed", "open_tickets", "critical_complaints", "unassigned_tickets", "payments_pending"]);
const STATUS_LABEL = { open: "مفتوحة", in_progress: "قيد المعالجة", waiting_for_user: "بانتظار العميل", resolved: "تم الحل", closed: "مغلقة" };

function Kpi({ k }) {
  const Icon = ICON[k.key] || ActivityIcon;
  const body = (
    <>
      <div className="top">
        <span>{KPI[k.key] || k.key}</span>
        <span className="ico">
          <Icon size={17} />
        </span>
      </div>
      <div className="val">{num(k.value)}</div>
      <div className="cmp">
        {k.period ? (
          <>
            <Trend pct={k.period.change_pct} goodWhenDown={BAD_WHEN_UP.has(k.key)} />
            <span>
              {num(k.period.current)} في الفترة · {num(k.period.previous)} قبلها
            </span>
          </>
        ) : (
          <span>الحالة الراهنة</span>
        )}
      </div>
    </>
  );
  const cls = "cc-card kpi " + (k.tone || "");
  return k.link ? (
    <Link to={`/team/${teamRel(k.link)}`} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export default function OverviewPage() {
  const { me } = useControl();
  const [range, setRange] = useState({ range: "30d" });
  const api = useApi(() => controlApi.overview(rangeParams(range)), [JSON.stringify(rangeParams(range))]);

  // The feed stays live: re-read every minute without flashing a skeleton.
  useEffect(() => {
    const t = setInterval(api.reload, 60000);
    return () => clearInterval(t);
  }, [api.reload]);

  return (
    <>
      <PageHead title={`مرحبًا ${me.name}`} desc="ملخص تشغيلي مباشر لمنصة مدار، من بيانات النظام الفعلية.">
        <RangePicker value={range} onChange={setRange} />
      </PageHead>
      <Async api={api} rows={10}>
        {(d) => {
          const c = d.charts;
          return (
            <>
              <div className="cc-grid kpi">
                {d.kpis.map((k) => (
                  <Kpi key={k.key} k={k} />
                ))}
              </div>

              <div className="cc-grid c21">
                <Card title="يحتاج انتباهًا" sub="أشياء تتطلب إجراءً الآن" pad={false}>
                  {d.attention.length === 0 ? (
                    <EmptyState icon={CircleCheck} title="لا شيء يحتاج انتباهًا" text="لا توجد شكاوى حرجة أو مدفوعات فاشلة أو أعطال ضمن المراقبة." />
                  ) : (
                    d.attention.map((a) => {
                      const [title, sub] = ATTENTION[a.key] || [a.key, ""];
                      return (
                        <Link key={a.key} to={`/team/${teamRel(a.link)}`} className="attn">
                          <span className={"ico " + a.severity}>
                            <AlertOctagon size={18} />
                          </span>
                          <span>
                            <div className="t">
                              {num(a.count)} · {title}
                            </div>
                            <div className="s">
                              {a.samples?.length ? a.samples.map((s) => s.label).join(" — ") : sub}
                            </div>
                          </span>
                          <ChevronLeft size={16} />
                        </Link>
                      );
                    })
                  )}
                </Card>
                <Card title="النشاط الأخير" sub="يتحدّث تلقائيًا" pad={false}>
                  {d.activity.length === 0 ? (
                    <EmptyState title="لا نشاط بعد" />
                  ) : (
                    <div className="feed" style={{ maxHeight: 380, overflowY: "auto" }}>
                      {d.activity.map((a, i) => {
                        const I = FEED_ICON[a.kind] || ActivityIcon;
                        return (
                          <Link key={i} to={`/team/${teamRel(a.link)}`}>
                            <span className="ico">
                              <I size={15} />
                            </span>
                            <span>{a.text}</span>
                            <span className="when">{ago(a.at)}</span>
                          </Link>
                        );
                      })}
                    </div>
                  )}
                </Card>
              </div>

              <div className="cc-grid c2">
                {c.user_growth && (
                  <ChartCard
                    title="نمو المستخدمين"
                    sub="إجمالي الحسابات عبر الفترة"
                    table={tableOf(["الإجمالي"], [{ points: c.user_growth }])}
                  >
                    <LineChart area series={toSeries([["إجمالي المستخدمين", SERIES.navy, c.user_growth]])} />
                  </ChartCard>
                )}
                {c.daily_activity && (
                  <ChartCard
                    title="النشاط اليومي على المنصة"
                    legend={[
                      { label: "سجلات الحضور", color: SERIES.c1 },
                      { label: "الإشعارات", color: SERIES.c2 },
                      { label: "الذكاء الاصطناعي", color: SERIES.c3 },
                      { label: "التذاكر", color: SERIES.c4 },
                    ]}
                    table={tableOf(
                      ["الحضور", "الإشعارات", "الذكاء الاصطناعي", "التذاكر"],
                      [{ points: c.daily_activity.attendance }, { points: c.daily_activity.notifications }, { points: c.daily_activity.ai }, { points: c.daily_activity.tickets }]
                    )}
                  >
                    <LineChart
                      series={toSeries([
                        ["سجلات الحضور", SERIES.c1, c.daily_activity.attendance],
                        ["الإشعارات", SERIES.c2, c.daily_activity.notifications],
                        ["الذكاء الاصطناعي", SERIES.c3, c.daily_activity.ai],
                        ["التذاكر", SERIES.c4, c.daily_activity.tickets],
                      ])}
                    />
                  </ChartCard>
                )}
                {c.teacher_registrations && (
                  <ChartCard
                    title="تسجيلات المعلّمين الجدد"
                    sub={`${num(sumSeries(c.teacher_registrations))} في الفترة`}
                    table={tableOf(["معلّمون جدد"], [{ points: c.teacher_registrations }])}
                  >
                    <BarChart series={toSeries([["معلّمون جدد", SERIES.navy, c.teacher_registrations]])} />
                  </ChartCard>
                )}
                {c.student_registrations && (
                  <ChartCard
                    title="تسجيلات الطلاب الجدد"
                    sub={`${num(sumSeries(c.student_registrations))} في الفترة`}
                    table={tableOf(["طلاب جدد"], [{ points: c.student_registrations }])}
                  >
                    <BarChart series={toSeries([["طلاب جدد", SERIES.navy, c.student_registrations]])} />
                  </ChartCard>
                )}
                {c.ticket_trends && (
                  <ChartCard
                    title="اتجاه تذاكر الدعم"
                    legend={[
                      { label: "تذاكر جديدة", color: SERIES.c1 },
                      { label: "تذاكر محلولة", color: SERIES.c3 },
                    ]}
                    table={tableOf(["جديدة", "محلولة"], [{ points: c.ticket_trends.created }, { points: c.ticket_trends.resolved }])}
                  >
                    <LineChart
                      series={toSeries([
                        ["تذاكر جديدة", SERIES.c1, c.ticket_trends.created],
                        ["تذاكر محلولة", SERIES.c3, c.ticket_trends.resolved],
                      ])}
                    />
                  </ChartCard>
                )}
                {c.ticket_resolution && (
                  <Card title="حالة تذاكر الفترة" sub="توزيع التذاكر المنشأة حسب حالتها الحالية">
                    <HBars rows={c.ticket_resolution.map((r) => ({ name: STATUS_LABEL[r.status] || r.status, count: r.count }))} empty="لا توجد تذاكر في هذه الفترة." />
                  </Card>
                )}
                {c.ai && (
                  <ChartCard
                    title="الذكاء الاصطناعي: نجاح مقابل فشل"
                    legend={[
                      { label: "ناجحة", color: SERIES.c1 },
                      { label: "فاشلة", color: SERIES.c2 },
                    ]}
                    table={tableOf(["ناجحة", "فاشلة"], [{ points: c.ai.success }, { points: c.ai.failed }])}
                  >
                    <BarChart
                      series={toSeries([
                        ["ناجحة", SERIES.c1, c.ai.success],
                        ["فاشلة", SERIES.c2, c.ai.failed],
                      ])}
                    />
                  </ChartCard>
                )}
                {c.finance && (
                  <ChartCard
                    title="اتجاه المعاملات المالية"
                    legend={[
                      { label: "ناجحة", color: SERIES.c1 },
                      { label: "فاشلة", color: SERIES.c2 },
                    ]}
                    table={tableOf(["ناجحة", "فاشلة"], [{ points: c.finance.succeeded }, { points: c.finance.failed }])}
                  >
                    <BarChart
                      series={toSeries([
                        ["ناجحة", SERIES.c1, c.finance.succeeded],
                        ["فاشلة", SERIES.c2, c.finance.failed],
                      ])}
                    />
                  </ChartCard>
                )}
              </div>
            </>
          );
        }}
      </Async>
    </>
  );
}
