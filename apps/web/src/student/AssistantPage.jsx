/**
 * AI Study Assistant (student area) — a chat-style screen.
 *
 * Documented contract this screen implements:
 *  - a GENERAL educational tutor, grounded in the central curated Knowledge
 *    Base, with a bounded source contract (scope.md, glossary.md);
 *  - NOT scoped to the student's records or identity in V1 — so nothing on
 *    this screen reads or sends any record;
 *  - asynchronous and failure-tolerant (ADR-006): submit returns an operation
 *    id, the worker answers, the page polls.
 *
 * Every question is answered INDEPENDENTLY: the backend keeps no conversation context, so the thread
 * below is a readable log of past question/answer pairs, not a memory the tutor draws on. The screen
 * says so rather than implying a ChatGPT-style continuous dialogue.
 *
 * The "المصادر" block is NOT decoration: `op.sources` is the exact set of PUBLISHED KB documents the
 * backend retrieved and fed to the provider for this answer. When the KB has nothing relevant the
 * operation fails and the tutor says so, rather than answering from memory.
 *
 * Answers are rendered as plain text (`white-space: pre-wrap`), never as HTML or markdown.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, BookOpen, Check, ChevronDown, Copy, RotateCcw, Sparkles } from "lucide-react";
import { studentApi } from "../lib/studentApi.js";
import { AI_TERMINAL } from "../lib/aiApi.js";
import { pollUntilDone } from "../lib/poll.js";
import { ApiError } from "../lib/api.js";
import { PageHeader } from "../dashboard/common.jsx";
import { fmtDateTime } from "../lib/dates.js";
import "./chat.css";

const STATUS_LABEL = {
  pending: "في الانتظار…",
  processing: "جارٍ البحث في قاعدة المعرفة…",
  completed: "تمت الإجابة",
  failed: "تعذّرت الإجابة",
};
const MAX_PROMPT = 2000;
const SUGGESTIONS = [
  "اشرح لي مفهومًا لم أفهمه في الدرس",
  "ما الفرق بين مصطلحين تعلمتهما؟",
  "لخّص لي موضوعًا بإيجاز",
];

const newKey = () =>
  globalThis.crypto?.randomUUID?.() ?? `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function Avatar() {
  return (
    <span className="chat-avatar" aria-hidden="true">
      <Sparkles size={15} />
    </span>
  );
}

/** The curated material this specific answer was built from. */
function Sources({ sources }) {
  if (!sources?.length) return null;
  return (
    <details className="chat-sources">
      <summary>
        <BookOpen size={14} aria-hidden="true" />
        <span>المصادر ({sources.length})</span>
        <ChevronDown size={14} className="chev" aria-hidden="true" />
      </summary>
      <ul>
        {sources.map((s) => (
          <li key={`${s.id}-${s.version}`}>
            <span className="t">{s.title}</span>
            {s.topic && <span className="chip-s">{s.topic}</span>}
            <span className="v">نسخة {s.version}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function Typing({ label }) {
  return (
    <div className="chat-wait">
      <span className="chat-dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span>{label}</span>
    </div>
  );
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setDone(false), 1800);
    } catch {
      /* clipboard unavailable (insecure context / permission): nothing to confirm */
    }
  };
  return (
    <button type="button" className="chat-act" onClick={copy} aria-label="نسخ الإجابة">
      {done ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
      <span aria-live="polite">{done ? "تم النسخ" : "نسخ"}</span>
    </button>
  );
}

function Exchange({ item, live, timedOut, onRetry, busy }) {
  const inFlight = !item.status || !AI_TERMINAL.has(item.status);
  return (
    <section className="chat-x">
      <div className="chat-user">
        <div className="chat-bubble" dir="auto">
          {item.prompt}
        </div>
      </div>
      <div className="chat-bot">
        <Avatar />
        <div className="chat-bot-body">
          {inFlight && (
            <>
              <Typing label={STATUS_LABEL[item.status] || STATUS_LABEL.pending} />
              {live && timedOut && (
                <p className="chat-hint">
                  ما زال سؤالك قيد المعالجة. يمكنك مغادرة الصفحة والعودة لاحقًا، وستجد الإجابة هنا.
                </p>
              )}
            </>
          )}

          {item.status === "completed" && (
            <>
              <div className="chat-answer" dir="auto">
                {item.result}
              </div>
              <Sources sources={item.sources} />
              <div className="chat-acts">
                <CopyButton text={item.result || ""} />
                {item.created_at && <time className="chat-time">{fmtDateTime(item.created_at)}</time>}
              </div>
            </>
          )}

          {item.status === "failed" && (
            <div className="chat-fail" role="alert">
              <p>{item.error || "تعذّرت الإجابة."}</p>
              <button type="button" className="chat-act" onClick={() => onRetry(item)} disabled={busy}>
                <RotateCcw size={14} aria-hidden="true" /> إعادة المحاولة
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export default function AssistantPage() {
  const api = studentApi.assistant;
  const [prompt, setPrompt] = useState("");
  const [op, setOp] = useState(null);
  const [pendingPrompt, setPendingPrompt] = useState(null); // shown while the submit request is in flight
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [timedOut, setTimedOut] = useState(false);
  const [history, setHistory] = useState([]); // newest first, as the API returns it
  const [loaded, setLoaded] = useState(false);
  const controllerRef = useRef(null);
  const resumedRef = useRef(false);
  const endRef = useRef(null);
  const areaRef = useRef(null);
  // One idempotency key per *attempt*: a double-tap reuses it (no duplicate
  // operation); a deliberate retry after a failure gets a fresh one.
  const attemptKeyRef = useRef(newKey());

  const track = useCallback(
    async (id) => {
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
          attemptKeyRef.current = newKey();
          api
            .list()
            .then((d) => setHistory(d.results || d))
            .catch(() => {});
        }
      } catch (e) {
        setError(
          e instanceof ApiError
            ? e.message
            : "تعذّر متابعة حالة السؤال. تحقّق من اتصالك ثم أعد المحاولة."
        );
      }
    },
    [api]
  );

  useEffect(() => {
    let live = true;
    api
      .list()
      .then((d) => {
        if (!live) return;
        const rows = d.results || d;
        setHistory(rows);
        setLoaded(true);
        // A question asked before the student left the page may still be running: pick it back up.
        const running = rows.find((r) => !AI_TERMINAL.has(r.status));
        if (running && !resumedRef.current) {
          resumedRef.current = true;
          setOp(running);
          track(running.id);
        }
      })
      .catch(() => live && setLoaded(true));
    return () => {
      live = false;
      controllerRef.current?.abort();
    };
  }, [api, track]);

  // Oldest → newest, with the live operation replacing its own history row (same id, same position).
  const thread = useMemo(() => {
    const byId = new Map();
    [...history].reverse().forEach((h) => byId.set(h.id, h));
    if (op) byId.set(op.id, op);
    return [...byId.values()];
  }, [history, op]);

  const inFlight = Boolean(pendingPrompt) || Boolean(op && !AI_TERMINAL.has(op.status));

  // Keep the newest message in view as it arrives or changes state.
  useEffect(() => {
    if (!thread.length && !pendingPrompt) return; // welcome state: leave the page where it is
    endRef.current?.scrollIntoView?.({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "end",
    });
  }, [thread.length, op?.status, pendingPrompt]);

  const grow = useCallback(() => {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, []);
  useEffect(grow, [prompt, grow]);

  const send = async (text) => {
    const value = text.trim();
    if (!value || submitting || inFlight) return;
    setSubmitting(true);
    setError(null);
    setPendingPrompt(value);
    try {
      const created = await api.submit(value, attemptKeyRef.current);
      setOp(created);
      setPrompt("");
      setPendingPrompt(null);
      setSubmitting(false);
      track(created.id);
    } catch (e2) {
      setPendingPrompt(null);
      setSubmitting(false);
      setError(e2 instanceof ApiError ? e2.message : "تعذّر إرسال السؤال.");
    }
  };

  const onSubmit = (e) => {
    e.preventDefault();
    send(prompt);
  };

  const onKeyDown = (e) => {
    // Desktop: Enter sends, Shift+Enter adds a line. Phones keep Enter as a newline (the send button sends).
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      if (window.matchMedia?.("(pointer: fine)").matches) {
        e.preventDefault();
        send(prompt);
      }
    }
  };

  const retry = (item) => {
    attemptKeyRef.current = newKey();
    send(item.prompt);
  };

  const pickSuggestion = (text) => {
    setPrompt(text);
    attemptKeyRef.current = newKey();
    areaRef.current?.focus();
  };

  const empty = loaded && thread.length === 0 && !pendingPrompt;
  const nearLimit = prompt.length > MAX_PROMPT * 0.8;

  return (
    <>
      <PageHeader infoKey="student_assistant" title="المساعد الدراسي" />

      <div className="chat">
        <div
          className="chat-thread"
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          aria-label="أسئلتك وإجابات المساعد"
        >
          {empty && (
            <div className="chat-welcome">
              <span className="chat-hero-ic" aria-hidden="true">
                <Sparkles size={26} />
              </span>
              <h2>كيف أساعدك في دراستك اليوم؟</h2>
              <p>
                مدرّس عام يجيب من <strong>قاعدة المعرفة المعتمدة في مدار</strong> فقط، ويعرض لك
                المصادر التي استعان بها. لا يطّلع على حضورك أو درجاتك أو أي من سجلاتك.
              </p>
              <div className="chat-suggest">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" onClick={() => pickSuggestion(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {thread.map((item) => (
            <Exchange
              key={item.id}
              item={item}
              live={op?.id === item.id}
              timedOut={timedOut}
              onRetry={retry}
              busy={submitting || inFlight}
            />
          ))}

          {pendingPrompt && <Exchange item={{ prompt: pendingPrompt }} busy />}

          <div ref={endRef} className="chat-end" />
        </div>

        <div className="chat-dock">
          {error && (
            <p className="chat-error" role="alert">
              {error}
            </p>
          )}
          <form className="chat-composer" onSubmit={onSubmit}>
            <textarea
              ref={areaRef}
              rows={1}
              maxLength={MAX_PROMPT}
              value={prompt}
              disabled={submitting || inFlight}
              aria-label="اكتب سؤالك التعليمي"
              placeholder={inFlight ? "جارٍ تحضير الإجابة…" : "اسأل عن أي شيء في دراستك…"}
              onChange={(e) => {
                setPrompt(e.target.value);
                attemptKeyRef.current = newKey();
              }}
              onKeyDown={onKeyDown}
            />
            <button
              type="submit"
              className="chat-send"
              aria-label="إرسال السؤال"
              disabled={!prompt.trim() || submitting || inFlight}
            >
              <ArrowUp size={18} aria-hidden="true" />
            </button>
          </form>
          <p className="chat-note">
            {nearLimit ? (
              <span className="count">
                {prompt.length} / {MAX_PROMPT}
              </span>
            ) : (
              "كل سؤال يُجاب بشكل مستقل، وقد يخطئ المساعد — راجع المصادر المعروضة."
            )}
          </p>
        </div>
      </div>
    </>
  );
}
