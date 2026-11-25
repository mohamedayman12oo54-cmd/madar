import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bot,
  Check,
  ChevronDown,
  CircleCheck,
  Clock,
  Eye,
  FileText,
  Gauge,
  Minus,
  PlayCircle,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { fmtDateTime } from "../lib/dates.js";
import {
  EXAM_STATUS,
  STATE_LABEL,
  STATE_TONE,
  TREND_LABEL,
  examPercent,
  masteryLabel,
  masteryTone,
} from "./mockAgent.js";
import "../dashboard/dashboard.css"; // the shared chips (.chip-s) live here
import "./agent.css";

// Digits around a slash are reordered by right-to-left text ("7 / 10" reads "10 / 7"): isolate them.
export const ltr = (t) => <bdi dir="ltr">{t}</bdi>;

/** The page is made of fake data until the agent has a backend; say so, always, so nobody mistakes it for real. */
export function MockBanner() {
  return (
    <div className="ag-mock" role="note">
      <Bot size={15} aria-hidden="true" />
      <span>عرض تجريبي ببيانات وهمية — لا شيء هنا يُحفظ أو يُرسل إلى أي جهة.</span>
    </div>
  );
}

export function StatePill({ state, big = false }) {
  return <span className={"chip-s " + (STATE_TONE[state] || "") + (big ? " ag-pill-big" : "")}>{STATE_LABEL[state] || state}</span>;
}

/** Hero shared by both audiences: who, what state the agent currently reads, and its one-line explanation. */
export function StateHero({ child, audience }) {
  const { student, state, headline } = child;
  const who = audience === "parent" ? `ملخص الوكيل عن ${student.name}` : "حالتك كما يراها الوكيل";
  return (
    <section className={"ag-hero tone-" + (STATE_TONE[state.key] || "")} aria-label={who}>
      <div className="ag-hero-top">
        <div>
          <div className="ag-eyebrow">
            <Bot size={14} aria-hidden="true" /> وكيل مدار الذكي
          </div>
          <h1 className="ag-hero-title">{who}</h1>
          <div className="ag-hero-meta">
            {student.name} — {student.grade} — {student.env}
          </div>
        </div>
        <div className="ag-hero-state">
          <StatePill state={state.key} big />
          <span className="ag-hero-trend">
            {state.trend === "improving" ? <TrendingUp size={14} /> : state.trend === "declining" ? <TrendingDown size={14} /> : <Minus size={14} />}
            {TREND_LABEL[state.trend]}
            {state.previous !== state.key && <> (كانت: {STATE_LABEL[state.previous]})</>}
          </span>
        </div>
      </div>
      <p className="ag-hero-text">{headline}</p>
      <div className="ag-hero-foot">
        <span>ثقة التقدير: {ltr(`${state.confidence}%`)}</span>
        <span>آخر تحديث: {fmtDateTime(state.updatedAt)}</span>
        <span className="ag-hero-note">تقدير استشاري — القرار النهائي للمعلّم.</span>
      </div>
    </section>
  );
}

/** One of the numbers the agent reads, with its movement since the previous period. */
export function Signals({ signals }) {
  return (
    <ul className="ag-signals">
      {signals.map((s) => {
        const tone = s.delta > 0 ? "good" : s.delta < 0 ? "bad" : "";
        return (
          <li key={s.id} className="ag-signal">
            <div className="ag-signal-label">{s.label}</div>
            <div className="ag-signal-value">{ltr(`${s.value}${s.unit}`)}</div>
            <div className={"ag-delta " + tone}>
              {s.delta > 0 ? <TrendingUp size={13} /> : s.delta < 0 ? <TrendingDown size={13} /> : <Minus size={13} />}
              {s.delta === 0 ? "ثابت" : ltr(`${s.delta > 0 ? "+" : "−"}${Math.abs(s.delta)}`)}
              <span className="ag-sr"> عن الفترة السابقة</span>
            </div>
            <div className="ag-signal-note">{s.note}</div>
          </li>
        );
      })}
    </ul>
  );
}

/** Weekly mastery points, oldest on the left (a chart reads left→right in every language). */
export function Sparkline({ points, tone }) {
  const W = 84;
  const H = 26;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const xy = points.map((p, i) => [(i * (W - 6)) / (points.length - 1) + 3, H - 3 - ((p - min) * (H - 6)) / span]);
  const last = xy[xy.length - 1];
  return (
    <svg
      className={"ag-spark " + tone}
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      role="img"
      aria-label={`تطور الإتقان خلال 6 أسابيع: من ${points[0]}% إلى ${points[points.length - 1]}%`}
    >
      <polyline points={xy.map((p) => p.join(",")).join(" ")} fill="none" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="3" />
    </svg>
  );
}

export function MasteryBar({ value }) {
  const tone = masteryTone(value);
  return (
    <div className={"ag-bar " + tone} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value} aria-label="مستوى الإتقان">
      <i style={{ width: `${value}%` }} />
    </div>
  );
}

/** A topic with its mastery, its 6-week movement and — on request — the evidence behind the agent's reading. */
export function TopicRow({ topic, defaultOpen = false }) {
  const tone = masteryTone(topic.mastery);
  const first = topic.history[0];
  const diff = topic.mastery - first;
  return (
    <article className="ag-topic">
      <div className="ag-topic-head">
        <div className="ag-topic-name">
          <h3>{topic.name}</h3>
          <span className="ag-topic-unit">{topic.unit}</span>
        </div>
        <span className={"chip-s " + tone}>{masteryLabel(topic.mastery)}</span>
      </div>
      <div className="ag-topic-body">
        <div className="ag-topic-score">
          <strong>{ltr(`${topic.mastery}%`)}</strong>
          <span className={"ag-delta " + (diff > 0 ? "good" : diff < 0 ? "bad" : "")}>
            {diff > 0 ? <TrendingUp size={13} /> : diff < 0 ? <TrendingDown size={13} /> : <Minus size={13} />}
            {ltr(`${diff > 0 ? "+" : diff < 0 ? "−" : ""}${Math.abs(diff)}`)} خلال 6 أسابيع
          </span>
        </div>
        <MasteryBar value={topic.mastery} />
        <Sparkline points={topic.history} tone={tone} />
      </div>
      <details className="ag-why" open={defaultOpen}>
        <summary>
          <Eye size={14} aria-hidden="true" /> ما الذي رآه الوكيل؟ <ChevronDown size={14} className="ag-chev" aria-hidden="true" />
        </summary>
        <ul>
          {topic.evidence.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
        <p className="ag-next">
          <Target size={14} aria-hidden="true" /> الخطوة التالية: {topic.next}
        </p>
      </details>
    </article>
  );
}

/** One exam the agent created or proposed. `actions` is a render prop so each audience brings its own buttons. */
export function ExamCard({ exam, status, actions }) {
  const st = EXAM_STATUS[status || exam.status];
  const pct = examPercent(exam);
  return (
    <article className={"ag-exam " + (status || exam.status)}>
      <div className="ag-exam-head">
        <div className="ag-exam-title">
          <FileText size={16} aria-hidden="true" />
          <h3>{exam.title}</h3>
        </div>
        <span className={"chip-s " + st.tone}>{st.label}</span>
      </div>
      <div className="ag-exam-meta">
        <span>{ltr(exam.questions)} أسئلة</span>
        <span>{ltr(exam.minutes)} دقيقة</span>
        <span>
          المستوى: {exam.difficulty}
        </span>
        <span>{exam.auto ? "أنشأه الوكيل تلقائيًا" : "اقتراح من الوكيل"}</span>
      </div>
      <div className="ag-exam-topics">
        {exam.topics.map((t) => (
          <span key={t} className="chip-s">
            {t}
          </span>
        ))}
      </div>
      <p className="ag-exam-reason">
        <strong>لماذا؟</strong> {exam.reason}
      </p>
      {pct != null && (
        <div className="ag-exam-result">
          <span>النتيجة: {ltr(`${exam.score} / ${exam.max}`)}</span>
          <MasteryBar value={pct} />
          <span className={"chip-s " + masteryTone(pct)}>{ltr(`${pct}%`)}</span>
        </div>
      )}
      <div className="ag-exam-foot">
        <small>أُنشئ {fmtDateTime(exam.createdAt)}</small>
        {actions}
      </div>
    </article>
  );
}

const KIND = {
  observation: { label: "ملاحظة", icon: Eye },
  decision: { label: "قرار", icon: Gauge },
  exam: { label: "اختبار", icon: FileText },
  result: { label: "نتيجة", icon: CircleCheck },
  state: { label: "تغيّر الحالة", icon: Target },
};
const AUTONOMY_NOTE = {
  auto: ["تلقائي", "good"],
  approval: ["احتاج موافقة", "warn"],
  info: null,
};

/** The agent's decision log: what it noticed, what it decided, what it did — and why, with the evidence. */
export function Timeline({ items, approved = {} }) {
  return (
    <ol className="ag-timeline">
      {items.map((d) => {
        const k = KIND[d.kind] || KIND.decision;
        const Icon = k.icon;
        const note = AUTONOMY_NOTE[d.autonomy];
        const wasApproved = d.examId && approved[d.examId];
        return (
          <li key={d.id} className={"ag-tl " + d.kind}>
            <span className="ag-tl-dot" aria-hidden="true">
              <Icon size={14} />
            </span>
            <div className="ag-tl-card">
              <div className="ag-tl-head">
                <span className="ag-tl-kind">{k.label}</span>
                {wasApproved ? <span className="chip-s good">تمت الموافقة</span> : note && <span className={"chip-s " + note[1]}>{note[0]}</span>}
                <time dateTime={d.at}>{fmtDateTime(d.at)}</time>
              </div>
              <h3>{d.title}</h3>
              <p>{d.why}</p>
              {d.evidence.length > 0 && (
                <ul className="ag-evidence" aria-label="الدلائل">
                  {d.evidence.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const PLAN_ICON = { class: Clock, exam: FileText, video: PlayCircle };

export function WeekPlan({ plan }) {
  return (
    <ol className="ag-plan">
      {plan.map((d) => (
        <li key={d.day} className="ag-plan-day">
          <span className="ag-plan-name">{d.day}</span>
          <ul>
            {d.items.map((it) => {
              const Icon = PLAN_ICON[it.type] || Clock;
              return (
                <li key={it.text} className={"ag-plan-item " + it.type}>
                  <Icon size={14} aria-hidden="true" /> {it.text}
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ol>
  );
}

/** A row of headline numbers. `items` = [{label, value, sub?, tone?}]. */
export function Tiles({ items }) {
  return (
    <div className="ag-tiles">
      {items.map((t) => (
        <div key={t.label} className={"ag-tile " + (t.tone || "")}>
          <div className="ag-tile-label">{t.label}</div>
          <div className="ag-tile-value">{t.value}</div>
          {t.sub && <div className="ag-tile-sub">{t.sub}</div>}
        </div>
      ))}
    </div>
  );
}

export function Section({ title, icon, meta, children }) {
  return (
    <section className="ag-sec">
      <div className="ag-sec-head">
        {icon && <span className="ag-ic">{icon}</span>}
        <h2>{title}</h2>
        {meta}
      </div>
      {children}
    </section>
  );
}

export function Empty({ text }) {
  return <p className="ag-empty">{text}</p>;
}

/** A WAI-ARIA tab strip. Panels are rendered by the caller; `idBase` ties each tab to its panel. */
export function Tabs({ tabs, value, onChange, label, idBase }) {
  const refs = useRef({});
  // A tab chosen from elsewhere (or by keyboard) must not sit off-screen in the scrolling strip.
  useEffect(() => {
    refs.current[value]?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [value]);
  const onKey = (e, i) => {
    // The page is right-to-left: the visually "next" tab is to the LEFT.
    const step = e.key === "ArrowLeft" ? 1 : e.key === "ArrowRight" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = tabs[(i + step + tabs.length) % tabs.length];
    onChange(next.key);
    refs.current[next.key]?.focus();
  };
  return (
    <div className="ag-tabs" role="tablist" aria-label={label}>
      {tabs.map((t, i) => {
        const on = t.key === value;
        return (
          <button
            key={t.key}
            ref={(el) => {
              refs.current[t.key] = el;
            }}
            id={`${idBase}-tab-${t.key}`}
            type="button"
            role="tab"
            aria-selected={on}
            aria-controls={`${idBase}-panel-${t.key}`}
            tabIndex={on ? 0 : -1}
            className={"ag-tab" + (on ? " active" : "")}
            onClick={() => onChange(t.key)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {t.icon}
            <span>{t.label}</span>
            {t.badge ? <span className="ag-tab-badge">{ltr(t.badge)}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

export function Panel({ idBase, value, current, children }) {
  if (value !== current) return null;
  return (
    <div role="tabpanel" id={`${idBase}-panel-${value}`} aria-labelledby={`${idBase}-tab-${value}`} className="ag-panel" tabIndex={0}>
      {children}
    </div>
  );
}

/** A short confirmation line that clears itself. Returns [node, show]. */
export function useToast() {
  const [msg, setMsg] = useState("");
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  const show = useCallback((text) => {
    clearTimeout(timer.current);
    setMsg(text);
    timer.current = setTimeout(() => setMsg(""), 3400);
  }, []);
  const node = (
    <div className="ag-toast-host" role="status" aria-live="polite">
      {msg && (
        <div className="ag-toast">
          <Check size={14} aria-hidden="true" /> {msg}
        </div>
      )}
    </div>
  );
  return [node, show];
}
