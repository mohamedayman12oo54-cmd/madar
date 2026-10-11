/**
 * AI Study Assistant (student area).
 *
 * Documented contract this screen implements:
 *  - a GENERAL educational tutor, grounded in the central curated Knowledge
 *    Base, with a bounded source contract (scope.md, glossary.md);
 *  - NOT scoped to the student's records or identity in V1 — so nothing on
 *    this screen reads or sends any record;
 *  - asynchronous and failure-tolerant (ADR-006): submit returns an operation
 *    id, the worker answers, the page polls.
 *
 * The "المصادر" block below is NOT decoration: `op.sources` is the exact set
 * of PUBLISHED KB documents the backend retrieved and fed to the provider for
 * this answer. When the KB has nothing relevant the operation fails and the
 * tutor says so, rather than answering from memory.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, RotateCcw, Send, BookOpen, Loader, History } from "lucide-react";
import { Btn, Banner } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { AI_TERMINAL } from "../lib/aiApi.js";
import { pollUntilDone } from "../lib/poll.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty } from "../dashboard/common.jsx";
import { fmtDateTime } from "../lib/dates.js";

const STATUS_LABEL = {
  pending: "في الانتظار…",
  processing: "جارٍ البحث في قاعدة المعرفة…",
  completed: "تمت الإجابة",
  failed: "تعذّرت الإجابة",
};
const MAX_PROMPT = 2000;
const SUGGESTIONS = ["اشرح لي مفهومًا لم أفهمه في الدرس", "ما الفرق بين مصطلحين تعلمتهما؟", "لخّص لي موضوعًا بإيجاز"];

const fmt = fmtDateTime;
const newKey = () => globalThis.crypto?.randomUUID?.() ?? `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;

/** The curated material this specific answer was built from. */
function Sources({ sources }) {
  if (!sources?.length) return null;
  return (
    <div className="ai-sources">
      <div className="ai-sources-head"><BookOpen size={14} /> المصادر من قاعدة المعرفة</div>
      <ul className="ai-source-list">
        {sources.map((s) => (
          <li key={`${s.id}-${s.version}`} className="ai-source">
            <span className="ai-source-title">{s.title}</span>
            {s.topic && <span className="chip-s">{s.topic}</span>}
            <span className="ai-source-ver">نسخة {s.version}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AssistantPage() {
  const api = studentApi.assistant;
  const [prompt, setPrompt] = useState("");
  const [op, setOp] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [timedOut, setTimedOut] = useState(false);
  const [history, setHistory] = useState([]);
  const controllerRef = useRef(null);
  // One idempotency key per *attempt*: a double-tap reuses it (no duplicate
  // operation); a deliberate retry after a failure gets a fresh one.
  const attemptKeyRef = useRef(newKey());

  const loadHistory = useCallback(() => {
    api.list().then((d) => setHistory(d.results || d)).catch(() => {});
  }, [api]);

  useEffect(() => { loadHistory(); return () => controllerRef.current?.abort(); }, [loadHistory]);

  const track = useCallback(async (id) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setTimedOut(false);
    try {
      const outcome = await pollUntilDone(() => api.get(id), {
        isDone: (o) => AI_TERMINAL.has(o.status),
        onUpdate: setOp,
        signal: controller.signal,
      });
      if (outcome.status === "timeout") setTimedOut(true);
      if (outcome.status === "done") { attemptKeyRef.current = newKey(); loadHistory(); }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "تعذّر متابعة حالة السؤال. تحقّق من اتصالك ثم أعد المحاولة.");
    }
  }, [api, loadHistory]);

  const submit = async (e) => {
    e?.preventDefault();
    const text = prompt.trim();
    if (!text || submitting) return;
    setSubmitting(true); setError(null); setOp(null);
    try {
      const created = await api.submit(text, attemptKeyRef.current);
      setOp(created);
      setSubmitting(false);
      track(created.id);
    } catch (e2) {
      setSubmitting(false);
      setError(e2 instanceof ApiError ? e2.message : "تعذّر إرسال السؤال.");
    }
  };

  const retry = () => { attemptKeyRef.current = newKey(); submit(); };

  const openFromHistory = (item) => {
    setPrompt(item.prompt);
    setOp(item);
    setError(null);
    if (!AI_TERMINAL.has(item.status)) track(item.id);
  };

  const inFlight = op && !AI_TERMINAL.has(op.status);

  return (
    <>
      <PageHeader infoKey="student_assistant" title="المساعد الدراسي" />

      <Banner tone="info">
        مدرّس عام يجيب من <strong>قاعدة المعرفة المعتمدة في مدار</strong> فقط، ويعرض لك المصادر التي استعان بها.
        لا يطّلع على حضورك أو درجاتك أو أي من سجلاتك.
      </Banner>

      <form onSubmit={submit} className="dash-form ai-ask" noValidate>
        <textarea
          className="inp" rows={4} maxLength={MAX_PROMPT} value={prompt} disabled={submitting || inFlight}
          placeholder="اكتب سؤالك التعليمي هنا…"
          onChange={(e) => { setPrompt(e.target.value); attemptKeyRef.current = newKey(); }}
        />
        <div className="ai-ask-foot">
          <span className="field-msg" style={{ margin: 0 }}>{prompt.length} / {MAX_PROMPT}</span>
          <Btn type="submit" loading={submitting} loadingText="جارٍ الإرسال…" disabled={!prompt.trim() || inFlight}>
            <Send size={16} /> اسأل
          </Btn>
        </div>
      </form>

      {!op && !error && (
        <div className="ai-suggestions">
          {SUGGESTIONS.map((sug) => (
            <button key={sug} type="button" className="mini-btn" onClick={() => setPrompt(sug)}>{sug}</button>
          ))}
        </div>
      )}

      {error && <div style={{ marginBlockStart: 14 }}><Banner tone="err">{error}</Banner></div>}

      {op && (
        <section className="ai-answer" aria-live="polite">
          <div className="ai-answer-head">
            {inFlight ? <Loader size={15} className="ai-spin" /> : <Sparkles size={15} />}
            <span>{STATUS_LABEL[op.status]}</span>
          </div>

          {inFlight && (
            <p className="field-msg">
              {timedOut
                ? "ما زال سؤالك قيد المعالجة. يمكنك العودة لاحقًا وفتحه من السجل بالأسفل."
                : "يتم تحضير الإجابة في الخلفية — يمكنك البقاء في هذه الصفحة."}
            </p>
          )}

          {op.status === "completed" && (
            <>
              <div className="ai-answer-body">{op.result}</div>
              <Sources sources={op.sources} />
            </>
          )}

          {op.status === "failed" && (
            <>
              <Banner tone="err">{op.error || "تعذّرت الإجابة."}</Banner>
              <div style={{ marginBlockStart: 10 }}>
                <Btn variant="ghost" onClick={retry}><RotateCcw size={14} /> إعادة المحاولة</Btn>
              </div>
            </>
          )}
        </section>
      )}

      <div className="dash-section-head" style={{ marginBlockStart: 26 }}>
        <h2 style={{ fontSize: "1rem" }}><History size={15} /> أسئلتي السابقة</h2>
      </div>
      {history.length === 0
        ? <Empty title="لا توجد أسئلة بعد" text="اكتب سؤالك التعليمي بالأعلى وسيظهر هنا بعد الإجابة." />
        : (
          <div className="list-rows">
            {history.map((h) => (
              <button key={h.id} className="list-row dash-card-btn ai-history-row" onClick={() => openFromHistory(h)}>
                <div className="ai-history-main">
                  <strong className="ai-history-q">{h.prompt}</strong>
                  <div className="stat-sub">{fmt(h.created_at)}</div>
                </div>
                <span className={"chip-s " + (h.status === "completed" ? "good" : h.status === "failed" ? "bad" : "warn")}>
                  {STATUS_LABEL[h.status].replace("…", "")}
                </span>
              </button>
            ))}
          </div>
        )}
    </>
  );
}
