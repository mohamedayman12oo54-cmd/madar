// Regression tests for the async-operation poller (Phase 5 / AI flow).
import { test } from "node:test";
import assert from "node:assert/strict";
import { pollUntilDone } from "./poll.js";

const noSleep = async () => {};
const isDone = (op) => op.status === "completed" || op.status === "failed";

function sequence(...items) {
  let i = 0;
  return async () => {
    const item = items[Math.min(i, items.length - 1)];
    i += 1;
    if (item instanceof Error) throw item;
    return item;
  };
}

test("polls through pending/processing until completed, reporting every update", async () => {
  const updates = [];
  const out = await pollUntilDone(
    sequence({ status: "pending" }, { status: "processing" }, { status: "completed", result: "x" }),
    { isDone, sleep: noSleep, onUpdate: (op) => updates.push(op.status) }
  );
  assert.equal(out.status, "done");
  assert.equal(out.op.result, "x");
  assert.deepEqual(updates, ["pending", "processing", "completed"]);
});

test("a server-reported failure is a normal terminal outcome, not an exception and never treated as success", async () => {
  const out = await pollUntilDone(
    sequence({ status: "pending" }, { status: "failed", error: "e" }),
    { isDone, sleep: noSleep }
  );
  assert.equal(out.status, "done");
  assert.equal(out.op.status, "failed");
});

test("gives up with 'timeout' (not an infinite loop) if it never finishes", async () => {
  let calls = 0;
  const out = await pollUntilDone(
    async () => {
      calls += 1;
      return { status: "pending" };
    },
    { isDone, sleep: noSleep, maxAttempts: 5 }
  );
  assert.equal(out.status, "timeout");
  assert.equal(calls, 5);
});

test("sleeps between polls but not after the last attempt", async () => {
  const sleeps = [];
  await pollUntilDone(async () => ({ status: "pending" }), {
    isDone,
    maxAttempts: 4,
    intervalMs: 123,
    sleep: async (ms) => sleeps.push(ms),
  });
  assert.deepEqual(sleeps, [123, 123, 123]);
});

test("a transient error does not abandon the operation — polling continues and succeeds", async () => {
  const out = await pollUntilDone(
    sequence({ status: "pending" }, new Error("network blip"), new Error("502"), {
      status: "completed",
    }),
    { isDone, sleep: noSleep }
  );
  assert.equal(out.status, "done");
});

test("the error counter resets after a good poll, so scattered errors never accumulate", async () => {
  const out = await pollUntilDone(
    sequence(
      new Error("a"),
      new Error("b"),
      { status: "pending" },
      new Error("c"),
      new Error("d"),
      { status: "completed" }
    ),
    { isDone, sleep: noSleep, maxConsecutiveErrors: 3 }
  );
  assert.equal(out.status, "done");
});

test("N consecutive errors give up and surface the last error", async () => {
  await assert.rejects(
    pollUntilDone(sequence(new Error("1"), new Error("2"), new Error("down")), {
      isDone,
      sleep: noSleep,
      maxConsecutiveErrors: 3,
    }),
    /down/
  );
});

test("aborting stops polling immediately and returns 'aborted' without calling the API again", async () => {
  const controller = new AbortController();
  let calls = 0;
  const out = await pollUntilDone(
    async () => {
      calls += 1;
      if (calls === 2) controller.abort();
      return { status: "pending" };
    },
    { isDone, sleep: noSleep, signal: controller.signal }
  );
  assert.equal(out.status, "aborted");
  assert.equal(calls, 2);
});

test("an already-aborted signal makes no requests at all", async () => {
  const controller = new AbortController();
  controller.abort();
  let calls = 0;
  const out = await pollUntilDone(
    async () => {
      calls += 1;
      return {};
    },
    { isDone, sleep: noSleep, signal: controller.signal }
  );
  assert.equal(out.status, "aborted");
  assert.equal(calls, 0);
});

test("an update that arrives after abort is not reported to the (possibly unmounted) UI", async () => {
  const controller = new AbortController();
  const updates = [];
  const out = await pollUntilDone(
    async () => {
      controller.abort();
      return { status: "completed" };
    },
    { isDone, sleep: noSleep, signal: controller.signal, onUpdate: (op) => updates.push(op) }
  );
  assert.equal(out.status, "aborted");
  assert.deepEqual(updates, []);
});
