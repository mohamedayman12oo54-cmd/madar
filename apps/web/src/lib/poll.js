// Generic poll-until-terminal helper for asynchronous backend operations
// (the AI submit -> poll -> result flow). Pure and dependency-free so it is
// unit-testable under Node; the React page just wires it to state.
//
//   const outcome = await pollUntilDone(() => aiApi.get(id), {
//     isDone: (op) => AI_TERMINAL.has(op.status),
//     onUpdate: setOp, signal: controller.signal,
//   });
//   outcome.status === "done" | "timeout" | "aborted"
//
// - A transient failure (network blip, 5xx) does NOT abandon the operation —
//   it keeps polling; only `maxConsecutiveErrors` failures IN A ROW give up
//   (the last error is thrown). The operation itself is server-side state:
//   losing a poll never loses the operation.
// - It never assumes success: it only returns "done" when `isDone(op)` says
//   the server reported a terminal state (which may be "failed").
const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function pollUntilDone(
  getOp,
  {
    isDone,
    intervalMs = 2000,
    maxAttempts = 60,
    maxConsecutiveErrors = 3,
    onUpdate,
    signal,
    sleep = defaultSleep,
  } = {}
) {
  let consecutiveErrors = 0;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (signal?.aborted) return { status: "aborted" };
    try {
      const op = await getOp();
      consecutiveErrors = 0;
      if (signal?.aborted) return { status: "aborted" };
      onUpdate?.(op);
      if (isDone(op)) return { status: "done", op };
    } catch (err) {
      consecutiveErrors += 1;
      if (consecutiveErrors >= maxConsecutiveErrors) throw err;
    }
    if (attempt < maxAttempts - 1) await sleep(intervalMs);
  }
  return { status: "timeout" };
}
