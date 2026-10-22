import test from "node:test";
import assert from "node:assert/strict";
import {
  accessSummary,
  attemptIdFromSearch,
  attemptNarrative,
  bannerFor,
  checkoutErrorMessage,
  cycleInfo,
  daysLeft,
  splitRemaining,
  formatCap,
  formatMoney,
  isAttemptDone,
  isEntitlementError,
  safeCheckoutUrl,
  sortPlans,
  PLAN_FEATURES,
  FEATURES,
} from "./billing.js";

const DAY = 86_400_000;
const NOW = Date.UTC(2026, 9, 20, 12, 0, 0);
const iso = (offsetDays) => new Date(NOW + offsetDays * DAY).toISOString();
const sub = (basis, extra = {}, ent = {}) => ({
  plan_key: "plan_2",
  trial_end: null,
  current_period_end: null,
  cancel_at_period_end: false,
  pending_checkout: null,
  entitlement: {
    access_granted: true,
    basis,
    reason_code: basis,
    capabilities: [],
    student_cap: 800,
    ...ent,
  },
  ...extra,
});

test("money is rendered from minor units with Arabic digits", () => {
  assert.equal(formatMoney(100000), "١٬٠٠٠ ج.م");
  assert.equal(formatMoney(150050), "١٬٥٠٠٫٥ ج.م");
  assert.equal(formatCap(null), "بدون حد");
  assert.equal(formatCap(400), "٤٠٠");
});

test("daysLeft rounds UP and never goes negative", () => {
  assert.equal(daysLeft(iso(5), NOW), 5);
  assert.equal(daysLeft(iso(0.2), NOW), 1); // 5 hours left is still "1 day", never 0 while access is on
  assert.equal(daysLeft(iso(-1), NOW), 0);
  assert.equal(daysLeft(null, NOW), 0);
});

test("cycleInfo: the trial is 16 ticks, a paid period 30, anything else nothing", () => {
  const trial = cycleInfo(sub("trial", { trial_end: iso(6) }), NOW);
  assert.deepEqual([trial.kind, trial.total, trial.left, trial.elapsed], ["trial", 16, 6, 10]);
  const paid = cycleInfo(sub("paid_active", { current_period_end: iso(12) }), NOW);
  assert.deepEqual([paid.kind, paid.total, paid.left, paid.elapsed], ["paid", 30, 12, 18]);
  assert.equal(cycleInfo(sub("none", {}, { access_granted: false }), NOW), null);
  assert.equal(cycleInfo(null, NOW), null);
  assert.equal(cycleInfo(sub("trial", { trial_end: iso(40) }), NOW).elapsed, 0); // clamped
});

test("accessSummary speaks for every server basis and never invents a state", () => {
  assert.equal(
    accessSummary(sub("trial", { trial_end: iso(10) }, { student_cap: 250 }), NOW).tone,
    "good"
  );
  assert.equal(
    accessSummary(sub("trial", { trial_end: iso(2) }, { student_cap: 250 }), NOW).tone,
    "warn"
  );
  assert.match(
    accessSummary(sub("paid_active", { current_period_end: iso(9) }), NOW).title,
    /الباقة الثانية/
  );
  assert.equal(
    accessSummary(sub("cancelled_but_paid_through", { current_period_end: iso(9) }), NOW).tone,
    "warn"
  );
  assert.equal(
    accessSummary(sub("payment_failed_pending_policy", { current_period_end: iso(-1) }), NOW).tone,
    "bad"
  );
  assert.match(
    accessSummary(sub("none", {}, { access_granted: false, reason_code: "trial_expired" }), NOW)
      .title,
    /انتهت الفترة التجريبية/
  );
  assert.match(
    accessSummary(sub("none", {}, { access_granted: false, reason_code: "period_ended" }), NOW)
      .title,
    /انتهت مدة اشتراكك/
  );
  assert.equal(accessSummary(null, NOW).tone, "neutral");
});

test("a data-preserving promise is made whenever access is off", () => {
  for (const rc of ["trial_expired", "period_ended"]) {
    assert.match(
      accessSummary(sub("none", {}, { access_granted: false, reason_code: rc }), NOW).text,
      /بياناتك محفوظة/
    );
  }
});

test("safeCheckoutUrl only lets the browser go to https on a trusted host", () => {
  assert.equal(
    safeCheckoutUrl("https://payments.kashier.io/session/abc"),
    "https://payments.kashier.io/session/abc"
  );
  assert.equal(safeCheckoutUrl("https://kashier.io/x"), "https://kashier.io/x");
  for (const bad of [
    "http://payments.kashier.io/x",
    "https://evil.com/kashier.io",
    "https://kashier.io.evil.com/x",
    "https://notkashier.io/x",
    "javascript:alert(1)",
    "data:text/html,x",
    "//evil.com",
    "",
    null,
    undefined,
    "https://evil.com@kashier.io.attacker.com/",
  ]) {
    assert.equal(safeCheckoutUrl(bad), null, String(bad));
  }
  assert.equal(safeCheckoutUrl("https://fake-kashier.test/pay/1"), null);
  assert.equal(
    safeCheckoutUrl("https://fake-kashier.test/pay/1", ["fake-kashier.test"]),
    "https://fake-kashier.test/pay/1"
  );
});

test("the redirect back never claims success on its own: only the server's status does", () => {
  assert.equal(attemptIdFromSearch("?attempt_id=12&status=success&paid=true"), 12);
  assert.equal(attemptIdFromSearch("?attempt_id=abc"), null);
  assert.equal(attemptIdFromSearch("?attempt_id=1;DROP"), null);
  assert.equal(attemptIdFromSearch("?attempt_id=-3"), null);
  assert.equal(attemptIdFromSearch(""), null);
  for (const s of ["pending", "initiated", "unknown"])
    assert.equal(attemptNarrative(s).tone, "info");
  assert.equal(attemptNarrative("pending").title.includes("تم الدفع"), false);
  assert.equal(attemptNarrative("succeeded").tone, "good");
  assert.equal(attemptNarrative("failed").tone, "bad");
  assert.equal(isAttemptDone({ status: "pending" }), false);
  assert.equal(isAttemptDone({ status: "succeeded" }), true);
  assert.equal(isAttemptDone({ status: "failed" }), true);
  assert.equal(isAttemptDone(null), false);
});

test("error codes become actionable Arabic messages", () => {
  assert.match(checkoutErrorMessage({ code: "paid_period_active" }), /ما زال ساريًا/);
  assert.match(checkoutErrorMessage({ code: "checkout_in_progress" }), /قيد الإتمام/);
  assert.match(checkoutErrorMessage({ code: "provider_unavailable" }), /لم يُسحب/);
  assert.match(checkoutErrorMessage(new Error("boom")), /تعذّر بدء/);
  assert.equal(isEntitlementError({ code: "student_cap_reached" }), true);
  assert.equal(isEntitlementError({ code: "capability_not_in_plan" }), true);
  assert.equal(isEntitlementError({ code: "other" }), false);
  assert.equal(isEntitlementError(null), false);
});

test("plans are shown in a fixed order and plan 3 includes everything", () => {
  const plans = sortPlans([{ key: "plan_3" }, { key: "plan_1" }, { key: "plan_2" }]);
  assert.deepEqual(
    plans.map((p) => p.key),
    ["plan_1", "plan_2", "plan_3"]
  );
  assert.equal(PLAN_FEATURES.plan_3.length, FEATURES.length);
  assert.ok(PLAN_FEATURES.plan_1.length < PLAN_FEATURES.plan_2.length);
});

test("bannerFor appears only when the teacher needs to act", () => {
  assert.equal(bannerFor(sub("trial", { trial_end: iso(10) }), NOW), null);
  assert.equal(bannerFor(sub("trial", { trial_end: iso(2) }), NOW).tone, "warn");
  assert.equal(bannerFor(sub("paid_active", { current_period_end: iso(20) }), NOW), null);
  assert.equal(
    bannerFor(sub("payment_failed_pending_policy", { current_period_end: iso(-1) }), NOW).tone,
    "bad"
  );
  assert.equal(
    bannerFor(sub("cancelled_but_paid_through", { current_period_end: iso(3) }), NOW).tone,
    "warn"
  );
  assert.equal(
    bannerFor(sub("cancelled_but_paid_through", { current_period_end: iso(25) }), NOW),
    null
  );
  assert.match(
    bannerFor(sub("none", {}, { access_granted: false, reason_code: "trial_expired" }), NOW).text,
    /بياناتك محفوظة/
  );
  assert.equal(bannerFor(null, NOW), null);
});

test("cycleInfo exposes an hour-precise fraction and splitRemaining breaks it into d/h/m", () => {
  const half = cycleInfo(sub("trial", { trial_end: iso(8) }), NOW);
  assert.equal(half.fraction, 0.5);
  assert.equal(half.remainingMs, 8 * 86_400_000);
  // one hour later the ring must be strictly smaller
  const later = cycleInfo(sub("trial", { trial_end: iso(8) }), NOW + 3_600_000);
  assert.ok(later.fraction < half.fraction);
  assert.deepEqual(splitRemaining(2 * 86_400_000 + 5 * 3_600_000 + 7 * 60_000), {
    days: 2,
    hours: 5,
    minutes: 7,
  });
  assert.deepEqual(splitRemaining(-5), { days: 0, hours: 0, minutes: 0 });
});
