import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Gift, Minus } from "lucide-react";
import { Btn, Modal } from "../auth/ui.jsx";
import { billingApi } from "../lib/dashboardApi.js";
import { useSession } from "../state/session.jsx";
import {
  FEATURES,
  PERIOD_DAYS,
  PLAN_FEATURES,
  TRIAL_DAYS,
  daysLeft,
  formatCap,
  formatMoney,
  planLabel,
} from "../lib/billing.js";

const seenKey = (userId) => `madar.plansWelcome.seen.${userId}`;
const wasSeen = (userId) => {
  try {
    return localStorage.getItem(seenKey(userId)) === "1";
  } catch {
    return true; // storage blocked: never nag on every page load
  }
};
const markSeen = (userId) => {
  try {
    localStorage.setItem(seenKey(userId), "1");
  } catch {
    /* best effort */
  }
};

/**
 * Shown ONCE, the first time a teacher opens the dashboard: the free trial first, then the paid plans
 * that follow it. Everything shown (prices, caps, trial end) comes from the server; nothing is
 * computed here. It only appears while the teacher is on the trial, never over a paying teacher,
 * and a failed fetch shows nothing (a broken welcome must never block teaching).
 */
export default function PlansWelcome() {
  const { user } = useSession();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const userId = user?.id;

  useEffect(() => {
    if (!userId || wasSeen(userId)) return undefined;
    let live = true;
    Promise.all([billingApi.subscription(), billingApi.plans()])
      .then(([sub, plans]) => {
        if (!live) return;
        if (sub?.entitlement?.basis !== "trial") {
          markSeen(userId); // not a trial teacher: nothing to introduce
          return;
        }
        if (!Array.isArray(plans) || plans.length === 0) return; // nothing sensible to show
        setData({ sub, plans });
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [userId]);

  if (!data) return null;
  const close = () => {
    markSeen(userId);
    setData(null);
  };
  const seePlans = () => {
    markSeen(userId);
    setData(null);
    nav("/app/billing");
  };
  const left = daysLeft(data.sub.trial_end) || TRIAL_DAYS;

  return (
    <Modal
      size="lg"
      title="أهلًا بك في مدار"
      text="ابدأ بتجربة مجانية كاملة، ثم اختر الباقة التي تناسب عدد طلابك."
      onClose={close}
      footer={
        <>
          <Btn variant="ghost" type="button" onClick={seePlans}>
            عرض الباقات والاشتراك
          </Btn>
          <Btn type="button" onClick={close}>
            ابدأ تجربتك المجانية
          </Btn>
        </>
      }
    >
      <section className="pw-trial" aria-label="التجربة المجانية">
        <span className="pw-ic" aria-hidden="true">
          <Gift size={22} />
        </span>
        <div>
          <h3>
            تجربة مجانية {TRIAL_DAYS.toLocaleString("ar-EG")} يومًا · متبقٍ {left.toLocaleString("ar-EG")}
          </h3>
          <p>جميع مزايا الباقة الثالثة متاحة لك بدون بطاقة، ولا يُخصم منك شيء تلقائيًا.</p>
        </div>
      </section>

      <h4 className="pw-h">الباقات بعد انتهاء التجربة</h4>
      <div className="pw-plans">
        {data.plans.map((p) => {
          const inc = new Set(PLAN_FEATURES[p.key] || []);
          return (
            <div key={p.key} className="pw-plan">
              <strong>{planLabel(p.key)}</strong>
              <div className="pw-price">
                <b>{formatMoney(p.price_minor_units, p.currency)}</b>
                <span>كل {PERIOD_DAYS.toLocaleString("ar-EG")} يومًا</span>
              </div>
              <div className="pw-cap">
                حتى {formatCap(p.max_students)} {p.max_students == null ? "" : "طالب"}
              </div>
              <ul>
                {FEATURES.map((f) => (
                  <li key={f.key} data-off={inc.has(f.key) ? 0 : 1}>
                    {inc.has(f.key) ? <Check size={14} aria-hidden="true" /> : <Minus size={14} aria-hidden="true" />}
                    <span>{f.label}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
