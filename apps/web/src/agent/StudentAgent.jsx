import { useState } from "react";
import { CalendarDays, FileText, ListChecks, Target, Eye, Hourglass, History } from "lucide-react";
import {
  AGENT_CHILDREN,
  WATCHED,
  averageExamPercent,
  completedExams,
  masteryTone,
  topicsByNeed,
  weakTopics,
} from "./mockAgent.js";
import {
  Empty,
  ExamCard,
  MockBanner,
  Panel,
  Section,
  Signals,
  StateHero,
  Tabs,
  Tiles,
  Timeline,
  TopicRow,
  WeekPlan,
  ltr,
  useToast,
} from "./parts.jsx";

const FILTERS = [
  { key: "all", label: "الكل", test: () => true },
  { key: "weak", label: "تحتاج تقوية", test: (t) => t.mastery < 50 },
  { key: "mid", label: "قيد التحسّن", test: (t) => t.mastery >= 50 && t.mastery < 75 },
  { key: "strong", label: "متمكّن", test: (t) => t.mastery >= 75 },
];

/** The student's view of the agent: what it sees, what it is asking them to practise, and why. */
export default function StudentAgentView({ child = AGENT_CHILDREN[0] }) {
  const [tab, setTab] = useState("overview");
  const [filter, setFilter] = useState("all");
  const [toast, show] = useToast();

  const ready = child.exams.filter((e) => e.status === "ready");
  const waiting = child.exams.filter((e) => e.status === "proposed");
  const done = completedExams(child.exams);
  const weak = weakTopics(child);
  const avg = averageExamPercent(child.exams);
  const sorted = topicsByNeed(child);
  const shown = sorted.filter(FILTERS.find((f) => f.key === filter).test);

  const tabs = [
    { key: "overview", label: "نظرة عامة", icon: <Eye size={15} /> },
    { key: "topics", label: "التقوية", icon: <Target size={15} />, badge: weak.length || null },
    { key: "exams", label: "اختباراتي", icon: <FileText size={15} />, badge: ready.length || null },
    { key: "log", label: "القرارات", icon: <History size={15} /> },
  ];

  const start = () => show("عرض تجريبي: سيفتح الاختبار هنا عند ربط الوكيل بالنظام.");
  const startButton = (
    <button type="button" className="mini-btn is-primary" onClick={start}>
      ابدأ الاختبار
    </button>
  );

  return (
    <div className="ag">
      <MockBanner />
      <StateHero child={child} audience="student" />
      <Tabs tabs={tabs} value={tab} onChange={setTab} label="أقسام صفحة الوكيل" idBase="ag-stu" />

      <Panel idBase="ag-stu" value="overview" current={tab}>
        <Section title="الخطوة التالية" icon={<ListChecks size={16} />}>
          {ready.length ? (
            <ExamCard exam={ready[0]} actions={startButton} />
          ) : (
            <Empty text="لا توجد اختبارات مطلوبة منك الآن. سيُخبرك الوكيل عندما يلزم تدريب جديد." />
          )}
          {waiting.length > 0 && (
            <p className="ag-hint">
              <Hourglass size={14} aria-hidden="true" /> اختبار «{waiting[0].title}» ينتظر موافقة ولي أمرك قبل أن يصل إليك.
            </p>
          )}
        </Section>

        <Section
          title="أهم ما يحتاج تقوية"
          icon={<Target size={16} />}
          meta={
            <button type="button" className="dash-linkish ag-sec-link" onClick={() => setTab("topics")}>
              كل المواضيع
            </button>
          }
        >
          {weak.length ? (
            <div className="ag-list">
              {weak.slice(0, 2).map((t) => (
                <TopicRow key={t.id} topic={t} />
              ))}
            </div>
          ) : (
            <Empty text="لا توجد مواضيع ضعيفة حاليًا. استمر على نفس المستوى." />
          )}
        </Section>

        <Section title="ما الذي يراقبه الوكيل؟" icon={<Eye size={16} />}>
          <p className="ag-lead">يقرأ الوكيل هذه الأرقام فقط: {WATCHED.join("، ")}. ولا يغيّر أيًا منها.</p>
          <Signals signals={child.signals} />
        </Section>

        <Section title="خطة هذا الأسبوع" icon={<CalendarDays size={16} />}>
          <WeekPlan plan={child.plan} />
        </Section>
      </Panel>

      <Panel idBase="ag-stu" value="topics" current={tab}>
        <Section title="مواضيعك حسب الحاجة" icon={<Target size={16} />}>
          <div className="ag-filters" role="group" aria-label="تصفية المواضيع">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                aria-pressed={filter === f.key}
                className={"ag-filter" + (filter === f.key ? " active" : "")}
                onClick={() => setFilter(f.key)}
              >
                {f.label} <span className="ag-count">{ltr(sorted.filter(f.test).length)}</span>
              </button>
            ))}
          </div>
          {shown.length ? (
            <div className="ag-list">
              {shown.map((t) => (
                <TopicRow key={t.id} topic={t} />
              ))}
            </div>
          ) : (
            <Empty text="لا توجد مواضيع في هذا التصنيف." />
          )}
        </Section>
      </Panel>

      <Panel idBase="ag-stu" value="exams" current={tab}>
        <Tiles
          items={[
            { label: "جاهزة للبدء", value: ltr(ready.length), tone: ready.length ? "warn" : "" },
            { label: "بانتظار الموافقة", value: ltr(waiting.length) },
            { label: "تم حلها", value: ltr(done.length) },
            { label: "متوسط النتائج", value: avg != null ? ltr(`${avg}%`) : "—", tone: avg != null ? masteryTone(avg) : "" },
          ]}
        />
        <Section title="جاهزة للبدء" icon={<FileText size={16} />}>
          {ready.length ? (
            <div className="ag-list">
              {ready.map((e) => (
                <ExamCard key={e.id} exam={e} actions={startButton} />
              ))}
            </div>
          ) : (
            <Empty text="لا توجد اختبارات جاهزة الآن." />
          )}
        </Section>
        {waiting.length > 0 && (
          <Section title="بانتظار موافقة ولي الأمر" icon={<Hourglass size={16} />}>
            <div className="ag-list">
              {waiting.map((e) => (
                <ExamCard key={e.id} exam={e} actions={<small className="ag-wait">سيظهر لك بعد الموافقة</small>} />
              ))}
            </div>
          </Section>
        )}
        <Section title="تم حلها" icon={<ListChecks size={16} />}>
          {done.length ? (
            <div className="ag-list">
              {done.map((e) => (
                <ExamCard key={e.id} exam={e} />
              ))}
            </div>
          ) : (
            <Empty text="لم تحل أي اختبار من الوكيل بعد." />
          )}
        </Section>
      </Panel>

      <Panel idBase="ag-stu" value="log" current={tab}>
        <Section title="ماذا فعل الوكيل ولماذا؟" icon={<History size={16} />}>
          <p className="ag-lead">كل قرار يأخذه الوكيل مسجّل هنا مع سببه والدلائل التي بُني عليها، من الأحدث إلى الأقدم.</p>
          <Timeline items={child.decisions} />
        </Section>
      </Panel>
      {toast}
    </div>
  );
}
