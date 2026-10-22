import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CalendarClock, Check, Lock, Minus, RefreshCw, Users } from "lucide-react";
import { Btn } from "../auth/ui.jsx";
import { ApiError } from "../lib/api.js";
import { billingApi } from "../lib/dashboardApi.js";
import { pollUntilDone } from "../lib/poll.js";
import {
  FEATURES,
  PERIOD_DAYS,
  PLAN_FEATURES,
  accessSummary,
  attemptIdFromSearch,
  attemptNarrative,
  checkoutErrorMessage,
  cycleInfo,
  formatCap,
  formatMoney,
  isAttemptDone,
  planLabel,
  safeCheckoutUrl,
  sortPlans,
  splitRemaining,
  HISTORY_STATUS,
} from "../lib/billing.js";
import { Confirm, Empty, PageHeader, errMessage, fmtDate, fmtDateTime } from "./common.jsx";
import "./billing.css";

const defaultRedirect = (url) => window.location.assign(url);
const trustedExtra = () => (import.meta.env?.DEV ? ["fake-kashier.test"] : []);
const nf = (n) => Number(n).toLocaleString("ar-EG");
const two = (n) => nf(n).padStart(2, "٠");

/* ------------------------------------------------------------------ live clock */
// Re-renders every 20s so the ring and the countdown move without a page refresh.
// A fixed `now` (tests / previews) disables the ticker.
function useNow(fixed) {
  const [t, setT] = useState(() => Date.now());
  useEffect(() => {
    if (fixed != null) return undefined;
    const id = setInterval(() => setT(Date.now()), 20_000);
    return () => clearInterval(id);
  }, [fixed]);
  return fixed ?? t;
}

/* ------------------------------------------------------------------ cycle ring */
const RING_R = 52;
const RING_C = 2 * Math.PI * RING_R;

function CycleRing({ cycle, tone }) {
  if (!cycle) return null;
  const t = splitRemaining(cycle.remainingMs);
  const dash = RING_C * cycle.fraction; // shrinks hour by hour
  return (
    <div className="bl-clock" data-tone={tone}>
      <div
        className="bl-ring"
        role="img"
        aria-label={`متبقٍّ ${nf(t.days)} يومًا و${nf(t.hours)} ساعة و${nf(t.minutes)} دقيقة من ${nf(cycle.total)} يومًا`}
      >
        <svg viewBox="0 0 120 120" aria-hidden="true">
          <circle className="bl-ring-bg" cx="60" cy="60" r={RING_R} />
          <circle
            className="bl-ring-fg"
            cx="60"
            cy="60"
            r={RING_R}
            strokeDasharray={`${dash} ${RING_C}`}
            data-empty={dash <= 0 ? 1 : 0}
          />
        </svg>
        <div className="bl-ring-mid" aria-hidden="true">
          <span className="bl-days-n">{nf(cycle.left)}</span>
          <span className="bl-days-l">يوم متبقٍّ</span>
        </div>
      </div>
      <div className="bl-timer" aria-hidden="true">
        <div>
          <b>{nf(t.days)}</b>
          <small>يوم</small>
        </div>
        <i>:</i>
        <div>
          <b>{two(t.hours)}</b>
          <small>ساعة</small>
        </div>
        <i>:</i>
        <div>
          <b>{two(t.minutes)}</b>
          <small>دقيقة</small>
        </div>
      </div>
    </div>
  );
}

function StatusBand({ sub, now }) {
  const summary = accessSummary(sub, now);
  const cycle = cycleInfo(sub, now);
  const ent = sub?.entitlement;
  // Offer the plan picker whenever the teacher is not already on a paid plan.
  const showCta = ent?.basis !== "paid_active";
  const goPlans = () =>
    document.getElementById("bl-plans")?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  return (
    <section
      className={"bl-band" + (cycle ? "" : " bl-band--plain")}
      data-tone={summary.tone}
      aria-live="polite"
    >
      <div className="bl-band-main">
        <h2 className="bl-band-title">{summary.title}</h2>
        {summary.text && <p className="bl-band-text">{summary.text}</p>}
        <div className="bl-facts">
          {ent?.access_granted && (
            <span className="bl-pill">
              <Users size={15} aria-hidden="true" />
              حتى {formatCap(ent.student_cap)} {ent.student_cap == null ? "" : "طالب"}
            </span>
          )}
          {cycle && (
            <span className="bl-pill">
              <CalendarClock size={15} aria-hidden="true" />
              ينتهي {fmtDate(cycle.endIso)}
            </span>
          )}
          {sub?.cancel_at_period_end && (
            <span className="bl-pill">
              التجديد التلقائي: <b>ملغى</b>
            </span>
          )}
        </div>
      </div>
      <CycleRing cycle={cycle} tone={summary.tone} />
      {showCta && (
        <button type="button" className="bl-band-cta" onClick={goPlans}>
          اختر باقتك
        </button>
      )}
    </section>
  );
}

/* ------------------------------------------------------------ return from payment */
function ReturnPanel({ attemptId, onSettled, onDismiss }) {
  const [attempt, setAttempt] = useState({ status: "pending" });
  const [gaveUp, setGaveUp] = useState(false);
  const settled = useRef(onSettled);
  settled.current = onSettled;

  useEffect(() => {
    const ctl = new AbortController();
    pollUntilDone(() => billingApi.checkoutStatus(attemptId), {
      isDone: isAttemptDone,
      intervalMs: 3000,
      maxAttempts: 60,
      onUpdate: setAttempt,
      signal: ctl.signal,
    })
      .then((out) => {
        if (out.status === "done") settled.current?.(out.op);
        else if (out.status === "timeout") setGaveUp(true);
      })
      .catch(() => setGaveUp(true));
    return () => ctl.abort();
  }, [attemptId]);

  // IMPORTANT: this panel shows ONLY what the server reports. The redirect itself proves nothing.
  const n = attemptNarrative(attempt?.status);
  return (
    <div className="bl-note" data-tone={n.tone} role="status">
      <strong>{n.title}</strong>
      <span>
        {gaveUp
          ? "ما زلنا ننتظر تأكيد البوابة. لا تعيد الدفع؛ سيظهر اشتراكك هنا فور وصول التأكيد، ويمكنك تحديث الصفحة لاحقًا."
          : n.text}
      </span>
      {(isAttemptDone(attempt) || gaveUp) && (
        <div className="bl-note-row">
          <Btn variant="ghost" onClick={onDismiss}>
            إخفاء
          </Btn>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------- plan ladder */
function PlanColumn({ plan, maxCap, sub, busyKey, onChoose }) {
  const included = new Set(PLAN_FEATURES[plan.key] || []);
  const paidActive =
    sub?.entitlement?.basis === "paid_active" ||
    sub?.entitlement?.basis === "cancelled_but_paid_through";
  const isCurrent = paidActive && sub.plan_key === plan.key;
  const pending = sub?.pending_checkout;
  const pendingOther = pending && pending.plan_key && pending.plan_key !== plan.key;
  const pendingSame = pending && pending.plan_key === plan.key;

  let label = `اشترك في ${planLabel(plan.key)}`;
  let disabled = false;
  let hint = null;
  if (isCurrent) {
    label = "باقتك الحالية";
    disabled = true;
  } else if (paidActive) {
    disabled = true;
    hint = "يمكنك تغيير الباقة بعد انتهاء اشتراكك الحالي.";
  } else if (pendingSame) {
    label = "أكمل الدفع";
  } else if (pendingOther) {
    disabled = true;
    hint = "لديك عملية دفع قيد الإتمام لباقة أخرى.";
  }

  const capPct =
    plan.max_students == null ? 100 : Math.max(8, Math.round((plan.max_students / maxCap) * 100));
  return (
    <div className="bl-plan" data-current={isCurrent ? 1 : 0}>
      <div className="bl-plan-name">
        {planLabel(plan.key)}
        {isCurrent && (
          <span className="bl-chip" data-tone="good">
            الحالية
          </span>
        )}
      </div>
      <div className="bl-price">
        <b>{formatMoney(plan.price_minor_units, plan.currency)}</b>
        <span>كل {nf(PERIOD_DAYS)} يومًا</span>
      </div>
      <div className="bl-cap">
        <span>
          حتى <b>{formatCap(plan.max_students)}</b> {plan.max_students == null ? "" : "طالب"}
        </span>
        <div className="bl-cap-bar" aria-hidden="true">
          <i style={{ width: `${capPct}%` }} />
        </div>
      </div>
      <ul className="bl-feats">
        {FEATURES.map((f) => {
          const on = included.has(f.key);
          return (
            <li key={f.key} data-off={on ? 0 : 1}>
              {on ? <Check size={16} aria-hidden="true" /> : <Minus size={16} aria-hidden="true" />}
              <span>
                {f.label}
                {on && f.soon && <span className="bl-soon">قريبًا</span>}
                <span className="sr-only">{on ? "" : " (غير متاحة)"}</span>
              </span>
            </li>
          );
        })}
      </ul>
      <div className="bl-cta">
        <Btn
          disabled={disabled || !!busyKey}
          loading={busyKey === plan.key}
          onClick={() => onChoose(plan.key)}
        >
          {label}
        </Btn>
        {hint && <p className="bl-hint">{hint}</p>}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- history */
function History() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  useEffect(() => {
    let live = true;
    billingApi
      .history(page)
      .then((d) => live && setData(d))
      .catch(() => live && setData({ results: [], failed: true }));
    return () => {
      live = false;
    };
  }, [page]);
  if (data === null) return <p className="field-msg">جاري تحميل سجل المدفوعات...</p>;
  if (data.failed) return <Empty title="تعذّر تحميل السجل" text="حاول تحديث الصفحة." />;
  const rows = data.results || [];
  if (rows.length === 0)
    return (
      <Empty
        title="لا توجد مدفوعات بعد"
        text="ستظهر هنا كل عملية دفع لاشتراكك بعد إتمام أول عملية."
      />
    );
  return (
    <div className="bl-hist">
      {rows.map((r) => {
        const st = HISTORY_STATUS[r.status] || HISTORY_STATUS.unknown;
        return (
          <div key={r.id} className="bl-hist-row">
            <div>
              <strong>{formatMoney(r.amount_minor_units, r.currency)}</strong>
              <small>{fmtDateTime(r.created_at)}</small>
            </div>
            <div>
              {r.period_start ? (
                <small>
                  الفترة: {fmtDate(r.period_start)} – {fmtDate(r.period_end)}
                </small>
              ) : (
                <small>اشتراك جديد</small>
              )}
            </div>
            <span className="bl-chip" data-tone={st.tone}>
              {st.label}
            </span>
          </div>
        );
      })}
      {(data.next || data.previous) && (
        <div className="bl-pager">
          <Btn variant="ghost" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>
            السابق
          </Btn>
          <Btn variant="ghost" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>
            التالي
          </Btn>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------- page */
export default function BillingPage({ redirect = defaultRedirect, now: nowProp }) {
  const [params, setParams] = useSearchParams();
  const [sub, setSub] = useState(null);
  const [plans, setPlans] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busyKey, setBusyKey] = useState(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [returning, setReturning] = useState(attemptIdFromSearch(params.toString()));
  const now = useNow(nowProp);

  const load = useCallback(
    () =>
      Promise.all([billingApi.subscription(), billingApi.plans()])
        .then(([s, p]) => {
          setSub(s);
          setPlans(sortPlans(Array.isArray(p) ? p : p.results || []));
          setError(null);
        })
        .catch((e) => setError(e instanceof ApiError ? e.message : "تعذّر تحميل بيانات الاشتراك.")),
    []
  );
  useEffect(() => {
    load();
  }, [load]);

  const dismissReturn = () => {
    setReturning(null);
    setParams({}, { replace: true });
  };
  const choose = async (planKey) => {
    setBusyKey(planKey);
    setNotice(null);
    try {
      const r = await billingApi.checkout(planKey);
      const url = safeCheckoutUrl(r?.session_url, trustedExtra());
      if (!url) {
        setNotice({ tone: "bad", text: "تعذّر تحويلك إلى بوابة الدفع بأمان. لم يُسحب أي مبلغ." });
        return;
      }
      redirect(url);
    } catch (e) {
      setNotice({ tone: "bad", text: checkoutErrorMessage(e) });
      load();
    } finally {
      setBusyKey(null);
    }
  };
  const cancel = async () => {
    try {
      const r = await billingApi.cancel();
      setNotice(
        r?.renewal_already_in_progress
          ? {
              tone: "warn",
              text: "تم إلغاء التجديد، لكن عملية تجديد كانت قد بدأت بالفعل. إن نجحت ستمتد مزايا اشتراكك لفترة إضافية ثم يتوقف.",
            }
          : {
              tone: "good",
              text: "تم إلغاء التجديد التلقائي. تستمر مزاياك حتى نهاية الفترة المدفوعة.",
            }
      );
      setConfirmCancel(false);
      await load();
    } catch (e) {
      setConfirmCancel(false);
      setNotice({ tone: "bad", text: errMessage(e, "تعذّر إلغاء التجديد.") });
    }
  };

  if (error)
    return (
      <>
        <PageHeader infoKey="billing" title="الاشتراك والباقات" />
        <Empty title="تعذّر التحميل" text={error} />
      </>
    );
  if (!sub || !plans)
    return (
      <>
        <PageHeader infoKey="billing" title="الاشتراك والباقات" />
        <p className="field-msg">جاري التحميل...</p>
      </>
    );

  const maxCap = Math.max(...plans.map((p) => p.max_students || 0), 1);
  const canCancel = sub.entitlement?.basis === "paid_active" && !sub.cancel_at_period_end;
  const hasPending = !!sub.pending_checkout;

  return (
    <div className="bl">
      <PageHeader infoKey="billing" title="الاشتراك والباقات" />
      {returning && (
        <ReturnPanel attemptId={returning} onDismiss={dismissReturn} onSettled={() => load()} />
      )}
      {notice && (
        <div className="bl-note" data-tone={notice.tone} role="status">
          <span>{notice.text}</span>
        </div>
      )}
      <StatusBand sub={sub} now={now} />

      <section aria-labelledby="bl-plans">
        <div className="dash-section-head">
          <h3 id="bl-plans">الباقات</h3>
          {hasPending && (
            <span className="bl-hint">
              <RefreshCw size={13} aria-hidden="true" /> لديك عملية دفع غير مكتملة
            </span>
          )}
        </div>
        <div className="bl-ladder">
          {plans.map((p) => (
            <PlanColumn
              key={p.key}
              plan={p}
              maxCap={maxCap}
              sub={sub}
              busyKey={busyKey}
              onChoose={choose}
            />
          ))}
        </div>
        <p className="bl-consent" style={{ marginBlockStart: 14 }}>
          <Lock size={15} aria-hidden="true" />
          <span>
            عند الاشتراك تُحفظ بطاقتك لدى بوابة الدفع (كاشير) وليس لدينا، ويُسحب سعر الباقة تلقائيًا
            كل {nf(PERIOD_DAYS)} يومًا حتى تلغي التجديد. يمكنك الإلغاء في أي وقت وتستمر مزاياك حتى
            نهاية الفترة المدفوعة. لا نخزّن رقم بطاقتك أبدًا.
          </span>
        </p>
      </section>

      {canCancel && (
        <div className="bl-danger-zone">
          <p>
            التجديد التلقائي مفعّل. إن ألغيته تستمر مزاياك حتى {fmtDate(sub.current_period_end)} ثم
            يتوقف الاشتراك، وتبقى بياناتك محفوظة.
          </p>
          <Btn variant="danger" onClick={() => setConfirmCancel(true)}>
            إلغاء التجديد التلقائي
          </Btn>
        </div>
      )}

      <section aria-labelledby="bl-hist">
        <div className="dash-section-head">
          <h3 id="bl-hist">سجل المدفوعات</h3>
        </div>
        <History />
      </section>

      {confirmCancel && (
        <Confirm
          danger
          title="إلغاء التجديد التلقائي؟"
          confirmLabel="نعم، ألغِ التجديد"
          text={`لن يُسحب منك أي مبلغ بعد ${fmtDate(sub.current_period_end)}. ستبقى كل المزايا حتى ذلك التاريخ.`}
          onConfirm={cancel}
          onClose={() => setConfirmCancel(false)}
        />
      )}
    </div>
  );
}
