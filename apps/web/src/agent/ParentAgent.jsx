import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Ban,
  Bot,
  Check,
  Clock,
  FileText,
  Gauge,
  History,
  Lightbulb,
  LogOut,
  Minus,
  Plus,
  Settings2,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import logo from "../assets/madar-logo.png";
import { clearParentSession, getParentSession, renewParentSession } from "../lib/parentApi.js";
import { startKeepAlive } from "../lib/keepalive.js";
import "../student/student.css";
import "../parent/parent.css";
import {
  AGENT_CHILDREN,
  AUTONOMY_LEVELS,
  GUARDRAILS,
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

/** The guardian's view of the agent: what it noticed, what it wants to do, and the controls that bound it. */
export function ParentAgentView() {
  const [childId, setChildId] = useState(AGENT_CHILDREN[0].id);
  const [tab, setTab] = useState("overview");
  const [decided, setDecided] = useState({}); // examId -> "ready" | "postponed" | "declined"
  const [settings, setSettings] = useState(() => Object.fromEntries(AGENT_CHILDREN.map((c) => [c.id, { ...c.defaults }])));
  const [toast, show] = useToast();

  const child = AGENT_CHILDREN.find((c) => c.id === childId);
  const cfg = settings[child.id];
  const statusOf = (e) => decided[e.id] || e.status;
  const pending = child.exams.filter((e) => statusOf(e) === "proposed");
  const decidedHere = child.exams.filter((e) => decided[e.id]);
  const done = completedExams(child.exams);
  const avg = averageExamPercent(child.exams);
  const weak = weakTopics(child);
  const sorted = topicsByNeed(child);
  const approvedMap = Object.fromEntries(Object.entries(decided).map(([k, v]) => [k, v === "ready"]));

  const set = (patch) => setSettings((s) => ({ ...s, [child.id]: { ...s[child.id], ...patch } }));
  const decide = (exam, to, text) => {
    setDecided((d) => ({ ...d, [exam.id]: to }));
    show(text);
  };
  const undo = (exam) => {
    setDecided((d) => {
      const next = { ...d };
      delete next[exam.id];
      return next;
    });
    show("تم التراجع — عاد الاقتراح إلى قائمة الانتظار.");
  };
  const pick = (id) => {
    setChildId(id);
    setTab("overview");
  };

  const tabs = [
    { key: "overview", label: "نظرة عامة", icon: <Gauge size={15} /> },
    { key: "approvals", label: "الموافقات", icon: <ShieldCheck size={15} />, badge: pending.length || null },
    { key: "progress", label: "التقدّم", icon: <TrendingUp size={15} /> },
    { key: "exams", label: "الاختبارات", icon: <FileText size={15} /> },
    { key: "log", label: "السجل", icon: <History size={15} /> },
    { key: "settings", label: "التحكم", icon: <Settings2 size={15} /> },
  ];

  const approvalButtons = (e) => (
    <div className="ag-actions">
      <button type="button" className="mini-btn is-primary" onClick={() => decide(e, "ready", "تمت الموافقة — سيظهر الاختبار عند الطالب (تجريبي).")}>
        <Check size={14} /> موافقة
      </button>
      <button type="button" className="mini-btn" onClick={() => decide(e, "postponed", "تم التأجيل — سيذكّرك الوكيل لاحقًا (تجريبي).")}>
        <Clock size={14} /> تأجيل
      </button>
      <button type="button" className="mini-btn danger" onClick={() => decide(e, "declined", "تم الرفض — لن يُنشئ الوكيل هذا الاختبار (تجريبي).")}>
        <X size={14} /> رفض
      </button>
    </div>
  );

  return (
    <div className="ag">
      <MockBanner />
      {AGENT_CHILDREN.length > 1 && (
        <div className="ag-kids" role="group" aria-label="اختيار الابن">
          {AGENT_CHILDREN.map((c) => (
            <button key={c.id} type="button" aria-pressed={c.id === childId} onClick={() => pick(c.id)}>
              {c.student.name}
            </button>
          ))}
        </div>
      )}
      <StateHero child={child} audience="parent" />
      <Tabs tabs={tabs} value={tab} onChange={setTab} label="أقسام متابعة الوكيل" idBase="ag-par" />

      <Panel idBase="ag-par" value="overview" current={tab}>
        {pending.length > 0 && (
          <div className="ag-callout warn" role="status">
            <ShieldCheck size={18} aria-hidden="true" />
            <div>
              <strong>
                {pending.length === 1 ? "قرار واحد ينتظر موافقتك" : `${pending.length} قرارات تنتظر موافقتك`}
              </strong>
              <p>الوكيل لن يُنشئ «{pending[0].title}» قبل أن توافق.</p>
            </div>
            <button type="button" className="mini-btn is-primary" onClick={() => setTab("approvals")}>
              مراجعة الآن
            </button>
          </div>
        )}

        <Section title="ماذا حدث باختصار؟" icon={<Bot size={16} />}>
          <ol className="ag-story">
            {child.story.map((s, i) => (
              <li key={s.step}>
                <span className="ag-story-n">{ltr(i + 1)}</span>
                <div>
                  <strong>{s.step}</strong>
                  <p>{s.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </Section>

        <Section title={`ما الذي يراقبه الوكيل عند ${child.student.name}؟`} icon={<Gauge size={16} />}>
          <p className="ag-lead">يقرأ الوكيل هذه الأرقام فقط: {WATCHED.join("، ")}. ولا يغيّر أيًا منها.</p>
          <Signals signals={child.signals} />
        </Section>

        <Section title="كيف تساعد؟" icon={<Lightbulb size={16} />}>
          <ul className="ag-tips">
            {child.tips.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </Section>

        <Section title="خطة هذا الأسبوع" icon={<Clock size={16} />}>
          <WeekPlan plan={child.plan} />
        </Section>
      </Panel>

      <Panel idBase="ag-par" value="approvals" current={tab}>
        <Section title="قرارات تنتظر موافقتك" icon={<ShieldCheck size={16} />}>
          {pending.length ? (
            <div className="ag-list">
              {pending.map((e) => (
                <ExamCard key={e.id} exam={e} status={statusOf(e)} actions={approvalButtons(e)} />
              ))}
            </div>
          ) : (
            <Empty text="لا توجد قرارات تنتظر موافقتك. سيُبلغك الوكيل عندما يحتاج رأيك." />
          )}
        </Section>
        {decidedHere.length > 0 && (
          <Section title="قرارات اتخذتها الآن" icon={<History size={16} />}>
            <div className="ag-list">
              {decidedHere.map((e) => (
                <ExamCard
                  key={e.id}
                  exam={e}
                  status={statusOf(e)}
                  actions={
                    <button type="button" className="mini-btn" onClick={() => undo(e)}>
                      تراجع
                    </button>
                  }
                />
              ))}
            </div>
          </Section>
        )}
        <p className="ag-hint">
          <ShieldCheck size={14} aria-hidden="true" /> مستوى الاستقلالية الحالي:{" "}
          <strong>{AUTONOMY_LEVELS.find((l) => l.key === cfg.autonomy).title}</strong>.{" "}
          <button type="button" className="dash-linkish" onClick={() => setTab("settings")}>
            تغييره
          </button>
        </p>
      </Panel>

      <Panel idBase="ag-par" value="progress" current={tab}>
        <Tiles
          items={[
            { label: "اختبارات تم حلها", value: ltr(done.length) },
            { label: "متوسط نتائجها", value: avg != null ? ltr(`${avg}%`) : "—", tone: avg != null ? masteryTone(avg) : "" },
            { label: "مواضيع تحتاج تقوية", value: ltr(weak.length), tone: weak.length ? "warn" : "good" },
            { label: "اختبارات هذا الأسبوع", value: ltr(`${child.weeklyUsed} / ${cfg.weeklyLimit}`), sub: "المُنشأ من الحد الأسبوعي الذي حددته" },
          ]}
        />
        <Section title="مستوى الإتقان في كل موضوع" icon={<TrendingUp size={16} />}>
          <div className="ag-list">
            {sorted.map((t) => (
              <TopicRow key={t.id} topic={t} />
            ))}
          </div>
        </Section>
      </Panel>

      <Panel idBase="ag-par" value="exams" current={tab}>
        <Section title="كل اختبارات الوكيل" icon={<FileText size={16} />}>
          {child.exams.length ? (
            <div className="ag-list">
              {child.exams.map((e) => (
                <ExamCard key={e.id} exam={e} status={statusOf(e)} />
              ))}
            </div>
          ) : (
            <Empty text="لم يُنشئ الوكيل أي اختبار بعد." />
          )}
        </Section>
      </Panel>

      <Panel idBase="ag-par" value="log" current={tab}>
        <Section title="سجل قرارات الوكيل" icon={<History size={16} />}>
          <p className="ag-lead">كل قرار مسجّل مع سببه والدلائل التي بُني عليها. لا يوجد قرار بلا تفسير.</p>
          <Timeline items={child.decisions} approved={approvedMap} />
        </Section>
      </Panel>

      <Panel idBase="ag-par" value="settings" current={tab}>
        <Section title="مستوى استقلالية الوكيل" icon={<Settings2 size={16} />}>
          <div className="ag-radios" role="radiogroup" aria-label="مستوى الاستقلالية">
            {AUTONOMY_LEVELS.map((l) => (
              <button
                key={l.key}
                type="button"
                role="radio"
                aria-checked={cfg.autonomy === l.key}
                className={"ag-radio" + (cfg.autonomy === l.key ? " active" : "")}
                onClick={() => set({ autonomy: l.key })}
              >
                <strong>{l.title}</strong>
                <span>{l.text}</span>
              </button>
            ))}
          </div>

          <div className="ag-setting">
            <div>
              <strong>الحد الأقصى لاختبارات الوكيل في الأسبوع</strong>
              <p>لن يتجاوزه الوكيل مهما كانت الحالة.</p>
            </div>
            <div className="ag-stepper" role="group" aria-label="الحد الأسبوعي">
              <button type="button" aria-label="إنقاص" disabled={cfg.weeklyLimit <= 1} onClick={() => set({ weeklyLimit: cfg.weeklyLimit - 1 })}>
                <Minus size={15} />
              </button>
              <output aria-live="polite">{ltr(cfg.weeklyLimit)}</output>
              <button type="button" aria-label="زيادة" disabled={cfg.weeklyLimit >= 5} onClick={() => set({ weeklyLimit: cfg.weeklyLimit + 1 })}>
                <Plus size={15} />
              </button>
            </div>
          </div>

          <Switch
            label="أبلغني عند إنشاء أي اختبار جديد"
            text="إشعار فوري كلما أنشأ الوكيل أو اقترح اختبارًا."
            on={cfg.notify}
            onChange={(v) => set({ notify: v })}
          />
          <Switch
            label="ملخص أسبوعي"
            text="رسالة واحدة كل أسبوع بما لاحظه الوكيل وما فعله."
            on={cfg.weeklySummary}
            onChange={(v) => set({ weeklySummary: v })}
          />

          <button type="button" className="mini-btn is-primary ag-save" onClick={() => show("تم حفظ الإعدادات (تجريبي — لم يُرسل شيء).")}>
            حفظ الإعدادات
          </button>
        </Section>

        <div className="ag-twocol">
          <Section title="ما يفعله الوكيل" icon={<Check size={16} />}>
            <ul className="ag-checks yes">
              {GUARDRAILS.does.map((t) => (
                <li key={t}>
                  <Check size={14} aria-hidden="true" /> {t}
                </li>
              ))}
            </ul>
          </Section>
          <Section title="ما لا يفعله أبدًا" icon={<Ban size={16} />}>
            <ul className="ag-checks no">
              {GUARDRAILS.doesNot.map((t) => (
                <li key={t}>
                  <Ban size={14} aria-hidden="true" /> {t}
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </Panel>
      {toast}
    </div>
  );
}

function Switch({ label, text, on, onChange }) {
  return (
    <div className="ag-setting">
      <div>
        <strong>{label}</strong>
        <p>{text}</p>
      </div>
      <button type="button" role="switch" aria-checked={on} aria-label={label} className={"ag-switch" + (on ? " on" : "")} onClick={() => onChange(!on)}>
        <i />
      </button>
    </div>
  );
}

/** The route /parent/agent: the guardian's shell (same look as the portal) around the view. */
export default function ParentAgentPage() {
  const nav = useNavigate();
  const [session, setSession] = useState(() => getParentSession());

  // Same rule as the portal: no timed sign-out while the tab is open.
  useEffect(
    () =>
      startKeepAlive(async () => {
        const next = await renewParentSession();
        if (next) setSession(next);
        else nav("/auth/parent", { replace: true });
      }),
    [nav]
  );

  if (!session) return <Navigate to="/auth/parent" replace />;

  const out = () => {
    clearParentSession();
    nav("/", { replace: true });
  };

  return (
    <div className="stu">
      <header className="stu-top">
        <div className="brand">
          <img src={logo} alt="مدار Madar" />
        </div>
        <div className="stu-env">
          <span className="name">وكيل مدار الذكي</span>
        </div>
        <div className="stu-top-end">
          <Link to="/parent" className="stu-icon-btn" aria-label="العودة إلى متابعة ولي الأمر">
            <ArrowRight size={18} />
          </Link>
          <button className="stu-icon-btn" aria-label="تسجيل الخروج" onClick={out}>
            <LogOut size={18} />
          </button>
        </div>
      </header>
      <main className="stu-body pp">
        <ParentAgentView />
      </main>
    </div>
  );
}
