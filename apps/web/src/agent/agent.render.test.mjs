// The agent pages (student + guardian) on their mock data: the data is internally consistent, both pages render
// without broken values, and the guardian's controls (approve / postpone / decline / undo, autonomy, child
// switcher, tabs) behave. Runs the real components in jsdom — no backend, no network.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:5173/preview/agent", pretendToBeVisual: true });
const w = dom.window;
for (const k of ["window", "document", "localStorage", "sessionStorage", "HTMLElement", "Element", "Node", "MutationObserver", "getComputedStyle", "requestAnimationFrame", "cancelAnimationFrame", "CustomEvent", "Event", "KeyboardEvent"]) {
  Object.defineProperty(globalThis, k, { value: k === "window" ? w : w[k], configurable: true, writable: true });
}
Object.defineProperty(globalThis, "navigator", { value: w.navigator, configurable: true });
w.Element.prototype.scrollIntoView = function () {};
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { createServer } = await import("vite");
const vite = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error", optimizeDeps: { noDiscovery: true },
  // React Router 7 ships dual CJS/ESM: bundle it through Vite so the harness sees the ESM build (as the other smoke tests do)
  ssr: { noExternal: ["react-router", "react-router-dom"], resolve: { conditions: ["module-sync", "import", "module", "node", "default"] } },
});
const data = await vite.ssrLoadModule("/src/agent/mockAgent.js");
const { default: StudentAgentView } = await vite.ssrLoadModule("/src/agent/StudentAgent.jsx");
const { ParentAgentView } = await vite.ssrLoadModule("/src/agent/ParentAgent.jsx");

const tick = (ms = 20) => new Promise((r) => setTimeout(r, ms));
const text = () => w.document.body.textContent;
const $$ = (sel) => [...w.document.querySelectorAll(sel)];
const byText = (sel, t) => $$(sel).find((e) => e.textContent.includes(t));
async function click(el) {
  assert.ok(el, "element to click exists");
  await act(async () => {
    el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    await tick();
  });
}
async function mount(Component) {
  w.document.body.innerHTML = "<div id='root'></div>";
  const root = createRoot(w.document.getElementById("root"));
  await act(async () => {
    root.render(React.createElement(Component));
    await tick();
  });
  return root;
}
const noBrokenValues = () => assert.doesNotMatch(text(), /undefined|NaN|\[object|null/);

// --------------------------------------------------------------------------------------- data
test("mock data: every child has the shape the pages read, with sane values", () => {
  assert.ok(data.AGENT_CHILDREN.length >= 2, "a guardian can have more than one child");
  for (const c of data.AGENT_CHILDREN) {
    assert.ok(data.STATE_LABEL[c.state.key] && data.STATE_LABEL[c.state.previous], `${c.id}: known states`);
    assert.ok(data.TREND_LABEL[c.state.trend]);
    assert.ok(c.state.confidence >= 0 && c.state.confidence <= 100);
    assert.equal(c.story.length, 4);
    for (const t of c.topics) {
      assert.equal(t.history.length, 6, `${t.id}: six weekly points`);
      assert.equal(t.history[5], t.mastery, `${t.id}: the last point IS the current mastery`);
      assert.ok(t.mastery >= 0 && t.mastery <= 100 && t.evidence.length > 0);
    }
    const ids = c.exams.map((e) => e.id);
    assert.equal(new Set(ids).size, ids.length, "exam ids are unique");
    for (const e of c.exams) {
      assert.ok(data.EXAM_STATUS[e.status], `${e.id}: known status`);
      if (e.status === "completed") assert.ok(e.score >= 0 && e.score <= e.max, `${e.id}: score within max`);
      else assert.equal(e.score, undefined, `${e.id}: only finished exams have a score`);
    }
    for (const d of c.decisions) {
      assert.ok(d.why && d.evidence, `${d.id}: every decision explains itself`);
      if (d.examId) assert.ok(ids.includes(d.examId), `${d.id}: points at a real exam`);
    }
    assert.ok(c.weeklyUsed <= c.defaults.weeklyLimit);
    assert.ok(data.AUTONOMY_LEVELS.some((l) => l.key === c.defaults.autonomy));
    // newest first, as the timeline promises
    const times = c.decisions.map((d) => Date.parse(d.at));
    assert.deepEqual(times, [...times].sort((a, b) => b - a), `${c.id}: decisions are newest first`);
  }
});

test("mock data: helpers agree with the thresholds the pages show", () => {
  assert.equal(data.masteryTone(80), "good");
  assert.equal(data.masteryTone(60), "warn");
  assert.equal(data.masteryTone(49), "bad");
  const yousef = data.AGENT_CHILDREN[0];
  assert.deepEqual(data.weakTopics(yousef).map((t) => t.id), ["factoring", "similarity"], "weakest first, only under 50%");
  assert.equal(data.averageExamPercent(yousef.exams), 55, "mean of 40% and 70%");
  assert.equal(data.averageExamPercent([]), null);
});

// ---------------------------------------------------------------------------------------- student
test("student page: hero, next step, weak topics and a start button, with no broken values", async () => {
  const root = await mount(StudentAgentView);
  assert.match(text(), /حالتك كما يراها الوكيل/);
  assert.match(text(), /يحتاج متابعة/);
  assert.match(text(), /الخطوة التالية/);
  assert.ok(byText("button", "ابدأ الاختبار"));
  assert.match(text(), /ينتظر موافقة ولي أمرك/, "the proposed exam is explained, not offered");
  assert.match(text(), /عرض تجريبي ببيانات وهمية/);
  noBrokenValues();
  await act(async () => root.unmount());
});

test("student page: the start button only confirms (mock) and tabs switch the panel", async () => {
  const root = await mount(StudentAgentView);
  await click(byText("button", "ابدأ الاختبار"));
  assert.match(w.document.querySelector(".ag-toast")?.textContent || "", /عرض تجريبي/);

  const tabs = $$('[role="tab"]');
  assert.equal(tabs.length, 4);
  assert.equal(tabs.filter((t) => t.getAttribute("aria-selected") === "true").length, 1);
  await click(byText('[role="tab"]', "التقوية"));
  assert.ok(w.document.querySelector('[role="tabpanel"]'), "one panel is shown");
  assert.match(text(), /تحتاج تقوية/);
  // filter: only the weak topics remain
  await click(byText(".ag-filter", "تحتاج تقوية"));
  assert.equal($$(".ag-topic").length, 2);
  await click(byText(".ag-filter", "متمكّن"));
  assert.equal($$(".ag-topic").length, 2);
  await click(byText('[role="tab"]', "القرارات"));
  assert.equal($$(".ag-tl").length, data.AGENT_CHILDREN[0].decisions.length);
  noBrokenValues();
  await act(async () => root.unmount());
});

// --------------------------------------------------------------------------------------- guardian
test("guardian page: a decision waits for approval; approve -> ready, undo -> waiting again", async () => {
  const root = await mount(ParentAgentView);
  assert.match(text(), /قرار واحد ينتظر موافقتك/);
  assert.equal(w.document.querySelector(".ag-tab-badge")?.textContent, "1");

  await click(byText('[role="tab"]', "الموافقات"));
  assert.match(text(), /تشابه المثلثات/);
  await click(byText("button", "موافقة"));
  assert.equal(w.document.querySelector(".ag-tab-badge"), null, "nothing is waiting any more");
  assert.match(text(), /جاهز للبدء/, "the approved exam is now ready");

  await click(byText("button", "تراجع"));
  assert.equal(w.document.querySelector(".ag-tab-badge")?.textContent, "1", "undo puts it back");

  await click(byText("button", "رفض"));
  assert.match(text(), /تم رفضه/);
  assert.equal(w.document.querySelector(".ag-tab-badge"), null);
  noBrokenValues();
  await act(async () => root.unmount());
});

test("guardian page: the decision log shows the approval once the guardian approved", async () => {
  const root = await mount(ParentAgentView);
  await click(byText('[role="tab"]', "الموافقات"));
  await click(byText("button", "موافقة"));
  await click(byText('[role="tab"]', "السجل"));
  assert.match(text(), /تمت الموافقة/);
  await act(async () => root.unmount());
});

test("guardian page: autonomy, weekly limit and switches are real controls with sane bounds", async () => {
  const root = await mount(ParentAgentView);
  await click(byText('[role="tab"]', "التحكم"));
  const radios = $$('[role="radio"]');
  assert.equal(radios.length, 3);
  assert.equal(radios.filter((r) => r.getAttribute("aria-checked") === "true").length, 1, "exactly one level is chosen");
  await click(byText('[role="radio"]', "اقتراح فقط"));
  assert.equal(byText('[role="radio"]', "اقتراح فقط").getAttribute("aria-checked"), "true");
  assert.equal($$('[role="radio"]').filter((r) => r.getAttribute("aria-checked") === "true").length, 1);

  const limit = () => w.document.querySelector(".ag-stepper output").textContent;
  assert.equal(limit(), "3");
  for (let i = 0; i < 6; i++) await click(w.document.querySelector('.ag-stepper button[aria-label="زيادة"]'));
  assert.equal(limit(), "5", "capped at 5");
  for (let i = 0; i < 8; i++) await click(w.document.querySelector('.ag-stepper button[aria-label="إنقاص"]'));
  assert.equal(limit(), "1", "never below 1");

  const sw = w.document.querySelector('[role="switch"]');
  const before = sw.getAttribute("aria-checked");
  await click(sw);
  assert.notEqual(sw.getAttribute("aria-checked"), before);

  await click(byText("button", "حفظ الإعدادات"));
  assert.match(w.document.querySelector(".ag-toast")?.textContent || "", /تجريبي/);
  assert.match(text(), /لا يغيّر أي درجة/, "the safety contract is on the same screen as the controls");
  await act(async () => root.unmount());
});

test("guardian page: settings are per child, and switching child resets to that child's overview", async () => {
  const root = await mount(ParentAgentView);
  await click(byText('[role="tab"]', "التحكم"));
  await click(byText('[role="radio"]', "اقتراح فقط"));
  await click(byText(".ag-kids button", "مريم"));
  assert.match(text(), /ملخص الوكيل عن مريم أحمد/);
  assert.equal(byText('[role="tab"]', "نظرة عامة").getAttribute("aria-selected"), "true");
  assert.doesNotMatch(text(), /ينتظر موافقتك/, "the other child has nothing waiting");
  await click(byText('[role="tab"]', "التحكم"));
  assert.equal(byText('[role="radio"]', "تلقائي").getAttribute("aria-checked"), "true", "her own level, untouched");
  await click(byText(".ag-kids button", "يوسف"));
  await click(byText('[role="tab"]', "التحكم"));
  assert.equal(byText('[role="radio"]', "اقتراح فقط").getAttribute("aria-checked"), "true", "his change was kept");
  await act(async () => root.unmount());
});

test("keyboard: arrow keys move between tabs (right-to-left) and keep one tab focusable", async () => {
  const root = await mount(ParentAgentView);
  const first = $$('[role="tab"]')[0];
  await act(async () => {
    first.dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    await tick();
  });
  const tabs = $$('[role="tab"]');
  assert.equal(tabs[1].getAttribute("aria-selected"), "true");
  assert.equal(tabs.filter((t) => t.tabIndex === 0).length, 1, "roving tabindex");
  await act(async () => root.unmount());
});

test.after(async () => {
  await vite.close();
});
