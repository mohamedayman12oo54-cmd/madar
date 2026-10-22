// Pure billing helpers for the teacher dashboard. Dependency-free so they are unit-tested under Node.
//
// Rules this file enforces for the UI (they mirror the Backend's guarantees, ADR-016/018):
//  * A redirect back from the payment page is NEVER "paid". Only the server's attempt status counts.
//  * The browser is only ever sent to an https checkout URL on a trusted host.
//  * Every number shown (price, student cap, dates) comes from the server; nothing is computed
//    from the URL or from client-held state.

export const PLAN_ORDER = ["plan_1", "plan_2", "plan_3"];
export const TRIAL_DAYS = 16;
export const PERIOD_DAYS = 30;
const DAY_MS = 86_400_000;

export const PLAN_LABELS = {
  plan_1: "الباقة الأولى",
  plan_2: "الباقة الثانية",
  plan_3: "الباقة الثالثة",
};

// Feature keys come from the Backend's capability registry (billing/capabilities.py).
export const FEATURES = [
  { key: "ai.quiz_from_video", label: "اختبارات تُولَّد تلقائيًا من فيديوهات الدرس", soon: false },
  { key: "ai.video_content_chat", label: "محادثة ذكية حول محتوى الفيديو", soon: true },
  { key: "ai.performance_analysis", label: "تحليل أداء الطلاب وتوصيات الحالة", soon: false },
];
// Which plan includes which feature (commercial-model §Plans). The trial equals plan 3.
export const PLAN_FEATURES = {
  plan_1: ["ai.quiz_from_video"],
  plan_2: ["ai.quiz_from_video", "ai.video_content_chat"],
  plan_3: ["ai.quiz_from_video", "ai.video_content_chat", "ai.performance_analysis"],
};

export const planLabel = (key) => PLAN_LABELS[key] || "—";

export function formatMoney(minorUnits, currency = "EGP") {
  const major = Number(minorUnits) / 100;
  const text = major.toLocaleString("ar-EG", { maximumFractionDigits: 2 });
  return currency === "EGP" ? `${text} ج.م` : `${text} ${currency}`;
}

export const formatCap = (cap) => (cap == null ? "بدون حد" : Number(cap).toLocaleString("ar-EG"));

/** Whole days left until `endIso` (rounded UP, so "0.2 days" reads as 1 day, never 0 while access is on). */
export function daysLeft(endIso, now = Date.now()) {
  if (!endIso) return 0;
  const ms = new Date(endIso).getTime() - now;
  return ms <= 0 ? 0 : Math.ceil(ms / DAY_MS);
}

/** Break a remaining duration into whole days / hours / minutes for the live countdown. */
export function splitRemaining(remainingMs) {
  const totalMin = Math.max(0, Math.floor(Number(remainingMs) / 60_000)) || 0;
  return {
    days: Math.floor(totalMin / 1440),
    hours: Math.floor((totalMin % 1440) / 60),
    minutes: totalMin % 60,
  };
}

/**
 * The cycle track: how far through the trial / the current paid period we are.
 * Returns null when there is nothing to show.
 */
export function cycleInfo(sub, now = Date.now()) {
  const ent = sub?.entitlement;
  if (!ent) return null;
  const build = (kind, endIso, total) => {
    const left = daysLeft(endIso, now);
    const elapsed = Math.min(total, Math.max(0, total - left));
    // Hour-level precision for the depleting ring: share of the whole cycle still remaining (0..1).
    const remainingMs = endIso ? Math.max(0, new Date(endIso).getTime() - now) : 0;
    const fraction = Math.min(1, remainingMs / (total * DAY_MS));
    return { kind, total, left, elapsed, endIso, remainingMs, fraction };
  };
  if (ent.basis === "trial" && sub.trial_end) return build("trial", sub.trial_end, TRIAL_DAYS);
  if (
    ["paid_active", "cancelled_but_paid_through", "payment_failed_pending_policy"].includes(
      ent.basis
    ) &&
    sub.current_period_end
  ) {
    return build("paid", sub.current_period_end, PERIOD_DAYS);
  }
  return null;
}

/** One headline for the page, derived only from the server's entitlement decision. */
export function accessSummary(sub, now = Date.now()) {
  const ent = sub?.entitlement;
  if (!ent) return { tone: "neutral", title: "جاري التحقق من حالة اشتراكك", text: "" };
  const cycle = cycleInfo(sub, now);
  switch (ent.basis) {
    case "trial":
      return {
        tone: cycle.left <= 3 ? "warn" : "good",
        title: "أنت في الفترة التجريبية",
        text: `متبقٍّ ${cycle.left.toLocaleString("ar-EG")} ${cycle.left === 1 ? "يوم" : "أيام"}، وبها كل مزايا الباقة الثالثة (حتى ${formatCap(ent.student_cap)} طالبًا). لا يُسحب منك شيء تلقائيًا.`,
      };
    case "paid_active":
      return {
        tone: "good",
        title: `باقتك الحالية: ${planLabel(sub.plan_key)}`,
        text: `تتجدّد بعد ${cycle.left.toLocaleString("ar-EG")} ${cycle.left === 1 ? "يوم" : "أيام"}.`,
      };
    case "cancelled_but_paid_through":
      return {
        tone: "warn",
        title: "تم إلغاء التجديد",
        text: `ستستمر كل المزايا حتى نهاية الفترة المدفوعة بعد ${cycle.left.toLocaleString("ar-EG")} ${cycle.left === 1 ? "يوم" : "أيام"}، ثم يتوقف الاشتراك.`,
      };
    case "payment_failed_pending_policy":
      return {
        tone: "bad",
        title: "تعذّر تجديد اشتراكك",
        text: "لم تنجح عملية الدفع الأخيرة. ما زال حسابك يعمل، لكن اشترِ باقة الآن لتفادي توقف الخدمة.",
      };
    default:
      if (ent.reason_code === "trial_expired")
        return {
          tone: "bad",
          title: "انتهت الفترة التجريبية",
          text: "بياناتك محفوظة بالكامل. اشترِ باقة لاستعادة مزايا الذكاء الاصطناعي وإضافة طلاب جدد.",
        };
      if (ent.reason_code === "period_ended")
        return {
          tone: "bad",
          title: "انتهت مدة اشتراكك",
          text: "بياناتك محفوظة بالكامل. جدّد اشتراكك لاستعادة المزايا.",
        };
      return { tone: "bad", title: "لا يوجد اشتراك فعّال", text: "اختر باقة للبدء." };
  }
}

/** Is the (server-reported) attempt status finished one way or the other? */
export const ATTEMPT_TERMINAL = new Set(["succeeded", "failed"]);
export const isAttemptDone = (a) => !!a && ATTEMPT_TERMINAL.has(a.status);

export function attemptNarrative(status) {
  switch (status) {
    case "succeeded":
      return {
        tone: "good",
        title: "تم الدفع وتفعيل اشتراكك",
        text: "شكرًا لك. كل مزايا باقتك متاحة الآن.",
      };
    case "failed":
      return {
        tone: "bad",
        title: "لم تكتمل عملية الدفع",
        text: "لم يُسحب أي مبلغ. يمكنك المحاولة مرة أخرى ببطاقة أخرى.",
      };
    case "unknown":
    case "pending":
    case "initiated":
      return {
        tone: "info",
        title: "بانتظار تأكيد الدفع",
        text: "نتأكد من نتيجة العملية مع بوابة الدفع. لا تعيد الدفع؛ سيتفعّل اشتراكك تلقائيًا فور التأكيد.",
      };
    default:
      return { tone: "info", title: "لا توجد عملية دفع قيد المتابعة", text: "" };
  }
}

export const HISTORY_STATUS = {
  succeeded: { label: "ناجحة", tone: "good" },
  failed: { label: "فاشلة", tone: "bad" },
  pending: { label: "قيد التأكيد", tone: "warn" },
  initiated: { label: "قيد التأكيد", tone: "warn" },
  unknown: { label: "قيد التأكيد", tone: "warn" },
};

/** Only an https URL on a trusted payment host may receive the browser. */
const TRUSTED_HOSTS = ["kashier.io"];
export function safeCheckoutUrl(url, extraHosts = []) {
  try {
    const u = new URL(String(url));
    if (u.protocol !== "https:") return null;
    const host = u.hostname.toLowerCase();
    const ok = [...TRUSTED_HOSTS, ...extraHosts].some((h) => host === h || host.endsWith(`.${h}`));
    return ok ? u.toString() : null;
  } catch {
    return null;
  }
}

const CHECKOUT_ERRORS = {
  paid_period_active: "اشتراكك الحالي ما زال ساريًا. يمكنك تغيير الباقة بعد انتهائه.",
  checkout_in_progress:
    "لديك عملية دفع قيد الإتمام لباقة أخرى. أكملها أو انتظر انتهاءها قبل اختيار باقة مختلفة.",
  provider_unavailable: "بوابة الدفع غير متاحة الآن. لم يُسحب منك أي مبلغ، حاول بعد قليل.",
};
export function checkoutErrorMessage(e, fallback = "تعذّر بدء عملية الدفع. حاول مرة أخرى.") {
  return CHECKOUT_ERRORS[e?.code] || (e?.status && e?.message) || fallback;
}

export const ENTITLEMENT_CODES = new Set([
  "entitlement_required",
  "capability_not_in_plan",
  "student_cap_reached",
]);
export const isEntitlementError = (e) => ENTITLEMENT_CODES.has(e?.code);

/** Student-capacity rows for the plan ladder (cap comes from the server's plan list). */
export function sortPlans(plans) {
  return [...(plans || [])].sort((a, b) => PLAN_ORDER.indexOf(a.key) - PLAN_ORDER.indexOf(b.key));
}

/** Read `attempt_id` from the return URL's query string; anything non-numeric is ignored. */
export function attemptIdFromSearch(search) {
  const raw = new URLSearchParams(search || "").get("attempt_id");
  return raw && /^\d{1,12}$/.test(raw) ? Number(raw) : null;
}

/** The one-line notice shown above every dashboard page (null = say nothing). */
export function bannerFor(sub, now = Date.now()) {
  const ent = sub?.entitlement;
  if (!ent) return null;
  const cycle = cycleInfo(sub, now);
  if (ent.basis === "trial" && cycle && cycle.left <= 3) {
    return {
      tone: "warn",
      cta: "اختر باقة",
      text: `تنتهي فترتك التجريبية خلال ${cycle.left.toLocaleString("ar-EG")} ${cycle.left === 1 ? "يوم" : "أيام"}.`,
    };
  }
  if (ent.basis === "payment_failed_pending_policy")
    return { tone: "bad", cta: "جدّد الآن", text: "تعذّر تجديد اشتراكك. حسابك يعمل حاليًا." };
  if (ent.basis === "cancelled_but_paid_through" && cycle && cycle.left <= 5) {
    return {
      tone: "warn",
      cta: "إدارة الاشتراك",
      text: `ينتهي اشتراكك خلال ${cycle.left.toLocaleString("ar-EG")} ${cycle.left === 1 ? "يوم" : "أيام"}.`,
    };
  }
  if (!ent.access_granted)
    return {
      tone: "bad",
      cta: "اختر باقة",
      text: "لا يوجد اشتراك فعّال: ميزات الذكاء الاصطناعي وإضافة طلاب جدد متوقفة. بياناتك محفوظة.",
    };
  return null;
}
