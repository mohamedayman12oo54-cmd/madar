import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, RotateCcw, Send } from "lucide-react";
import { Btn, Banner } from "../auth/ui.jsx";
import { aiApi, AI_TERMINAL } from "../lib/aiApi.js";
import { pollUntilDone } from "../lib/poll.js";
import { ApiError } from "../lib/api.js";
import { PageHeader } from "./common.jsx";
import { fmtDateTime } from "../lib/dates.js";

const STATUS_LABEL = { pending: "بانتظار المعالجة…", processing: "جارٍ إعداد الإجابة…", completed: "مكتملة", failed: "فشلت" };
const MAX_PROMPT = 2000;

const fmt = fmtDateTime;

function newKey() {
  return globalThis.crypto?.randomUUID?.() ?? `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function AiPage({ api = aiApi, infoKey = "ai" }) {
  const [prompt, setPrompt] = useState("");
  const [op, setOp] = useState(null);            // the operation currently on screen
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [timedOut, setTimedOut] = useState(false);
  const [history, setHistory] = useState([]);
  const controllerRef = useRef(null);
  // One idempotency key per *attempt*: a double-click or a network retry of
  // the SAME attempt reuses it (no duplicate operation); a deliberate retry
  // after a failure generates a fresh one.
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
      if (outcome.status === "done") {
        attemptKeyRef.current = newKey(); // finished: a deliberate re-send is a NEW operation
        loadHistory();
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "تعذّر متابعة حالة الطلب. تحقق من اتصالك ثم أعد المحاولة.");
    }
  }, [loadHistory]);

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

  const retry = () => {
    attemptKeyRef.current = newKey(); // a deliberate retry is a NEW operation
    submit();
  };

  const openFromHistory = (item) => {
    setPrompt(item.prompt);
    setOp(item);
    setError(null);
    if (!AI_TERMINAL.has(item.status)) track(item.id);
  };

  const inFlight = op && !AI_TERMINAL.has(op.status);

  return (
    <>
      <PageHeader infoKey={infoKey} title="المساعد الذكي" />

      <Banner tone="info">
        مساعد تعليمي عام للمعلّم — لا يطّلع على بيانات أي طالب. الإجابات قد تحتوي على أخطاء، راجعها قبل الاعتماد عليها.
      </Banner>

      <form onSubmit={submit} className="dash-form" style={{ marginTop: 16 }}>
        <textarea
          className="inp" rows={4} maxLength={MAX_PROMPT} value={prompt} disabled={submitting || inFlight}
          placeholder="اسأل عن شرح مفهوم، فكرة لتمرين، أو طريقة لتبسيط درس…"
          onChange={(e) => { setPrompt(e.target.value); attemptKeyRef.current = newKey(); }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <span className="field-msg" style={{ margin: 0 }}>{prompt.length} / {MAX_PROMPT}</span>
          <Btn type="submit" loading={submitting} loadingText="جارٍ الإرسال…" disabled={!prompt.trim() || inFlight}>
            <Send size={16} /> إرسال
          </Btn>
        </div>
      </form>

      {error && <div style={{ marginTop: 14 }}><Banner tone="err">{error}</Banner></div>}

      {op && (
        <div className="dash-card" style={{ marginTop: 18 }} aria-live="polite">
          <div className="k"><Sparkles size={14} /> {STATUS_LABEL[op.status]}</div>
          {inFlight && !timedOut && <p className="field-msg">يتم تنفيذ الطلب في الخلفية — يمكنك البقاء في هذه الصفحة.</p>}
          {inFlight && timedOut && (
            <p className="field-msg">
              ما زال الطلب قيد المعالجة. يمكنك العودة لاحقًا وفتحه من السجل أدناه.
            </p>
          )}
          {op.status === "completed" && <div style={{ whiteSpace: "pre-wrap", marginTop: 8, lineHeight: 1.8 }}>{op.result}</div>}
          {op.status === "failed" && (
            <>
              <Banner tone="err">{op.error || "تعذّر إكمال الطلب."}</Banner>
              <div style={{ marginTop: 10 }}>
                <Btn variant="ghost" onClick={retry}><RotateCcw size={14} /> إعادة المحاولة</Btn>
              </div>
            </>
          )}
        </div>
      )}

      {history.length > 0 && (
        <>
          <div className="dash-section-head" style={{ marginTop: 28 }}><h2 style={{ fontSize: "1rem" }}>السجل</h2></div>
          <div className="dash-cards" style={{ gridTemplateColumns: "1fr" }}>
            {history.map((h) => (
              <button key={h.id} className="dash-card dash-card-btn dash-session-row" onClick={() => openFromHistory(h)}>
                <div className="dash-session-info" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4, minWidth: 0 }}>
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "100%" }}>{h.prompt}</div>
                  <div className="k">{fmt(h.created_at)}</div>
                </div>
                <span className={"dash-pill" + (h.status === "completed" ? " on" : "")}>{STATUS_LABEL[h.status].replace("…", "")}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </>
  );
}
