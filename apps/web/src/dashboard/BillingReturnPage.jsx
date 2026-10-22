import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CircleX, Clock3 } from "lucide-react";
import { Btn, OrbitBig, SuccessRing } from "../auth/ui.jsx";
import { billingApi } from "../lib/billingApi.js";
import { forgetAttempt, readAttempt, isTerminalAttempt } from "../lib/billing.js";
import { pollUntilDone } from "../lib/poll.js";
import "./billing.css";

/** Where Kashier sends the browser. It deliberately TRUSTS NOTHING in the URL
 *  (ADR-016): it only asks our server what happened to the attempt we started,
 *  and shows "success" only when the server says the payment succeeded. */
export default function BillingReturnPage() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [state, setState] = useState("checking"); // checking | succeeded | failed | waiting | missing
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return undefined;
    ran.current = true;
    const fromQuery = params.get("attempt_id");
    const attemptId =
      (fromQuery && /^\d{1,18}$/.test(fromQuery) ? fromQuery : null) || readAttempt();
    if (!attemptId) {
      setState("missing");
      return undefined;
    }
    const ctrl = new AbortController();
    pollUntilDone(() => billingApi.checkoutStatus(attemptId), {
      isDone: (r) => isTerminalAttempt(r?.status) || r?.attempt_id === null,
      intervalMs: 3000,
      maxAttempts: 40,
      signal: ctrl.signal,
    })
      .then((out) => {
        if (out.status === "aborted") return;
        if (out.status === "timeout") {
          setState("waiting");
          return;
        }
        const r = out.op;
        if (r?.status === "succeeded") {
          forgetAttempt();
          setState("succeeded");
        } else if (r?.status === "failed") {
          forgetAttempt();
          setState("failed");
        } else setState("missing");
      })
      .catch(() => setState("waiting"));
    return () => ctrl.abort();
  }, [params]);

  const back = (
    <Btn onClick={() => nav("/app/billing", { replace: true })}>العودة إلى الاشتراك</Btn>
  );
  return (
    <div className="bill-return" role="status" aria-live="polite">
      {state === "checking" && (
        <>
          <OrbitBig />
          <h2>نتأكد من عملية الدفع</h2>
          <p>
            العودة من صفحة الدفع وحدها لا تعني أن العملية نجحت، لذلك نسأل البوابة مباشرة. قد يستغرق
            ذلك لحظات.
          </p>
          <span className="safe">لا تُعِد الدفع ولا تغلق هذه الصفحة.</span>
        </>
      )}
      {state === "succeeded" && (
        <>
          <SuccessRing />
          <h2>تم الدفع وتفعيل اشتراكك</h2>
          <p>شكرًا لك. تم تأكيد الدفع من بوابة الدفع وفُعِّلت باقتك.</p>
          {back}
        </>
      )}
      {state === "failed" && (
        <>
          <CircleX size={52} color="#b3261e" />
          <h2>لم تنجح عملية الدفع</h2>
          <p>لم يتم خصم أي مبلغ. يمكنك المحاولة مرة أخرى بنفس البطاقة أو ببطاقة أخرى.</p>
          {back}
        </>
      )}
      {state === "waiting" && (
        <>
          <Clock3 size={52} color="#8a5a00" />
          <h2>ما زلنا ننتظر تأكيد البنك</h2>
          <p>
            لم يصلنا تأكيد الدفع بعد. إن كان قد تم الخصم فسيُفعَّل اشتراكك تلقائيًا بمجرد وصول
            التأكيد؛ لا داعي لإعادة الدفع.
          </p>
          {back}
        </>
      )}
      {state === "missing" && (
        <>
          <Clock3 size={52} color="#6B7280" />
          <h2>لا توجد عملية دفع قيد المتابعة</h2>
          <p>إن كنت قد دفعت للتو فتحقق من سجل المدفوعات في صفحة الاشتراك.</p>
          {back}
        </>
      )}
    </div>
  );
}
