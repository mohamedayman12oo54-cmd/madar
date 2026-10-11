import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { studentApi } from "../lib/studentApi.js";
import { pollUntilDone } from "../lib/poll.js";
import { ApiError } from "../lib/api.js";

const newKey = () => globalThis.crypto?.randomUUID?.() ?? `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;

/** "اختبرني" for a video: one idempotency key per video per attempt, so a
 *  double tap never makes two quizzes. Shared by the list and the detail page. */
export function useQuiz() {
  const nav = useNavigate();
  const [busyId, setBusyId] = useState(null);
  const [notice, setNotice] = useState(null);
  const keys = useRef({});
  const abort = useRef(null);

  const quiz = async (item) => {
    setBusyId(item.id); setNotice(null);
    keys.current[item.id] ||= newKey();
    const controller = new AbortController(); abort.current = controller;
    try {
      const op = await studentApi.quizzes.request(item.id, keys.current[item.id]);
      const out = await pollUntilDone(() => studentApi.quizzes.operation(op.id), { isDone: (o) => o.status === "completed" || o.status === "failed", signal: controller.signal });
      if (out.status === "done" && out.op.status === "completed" && out.op.quiz_id) { delete keys.current[item.id]; nav(`/learn/quizzes/${out.op.quiz_id}`); return; }
      delete keys.current[item.id];
      setNotice({ tone: "err", text: out.status === "timeout" ? "استغرق إعداد الاختبار وقتًا أطول من المتوقع. حاول لاحقًا." : (out.op?.error || "تعذّر إعداد الاختبار. حاول مرة أخرى.") });
    } catch (e) {
      setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر طلب الاختبار." });
    } finally { setBusyId(null); }
  };
  return { quiz, busyId, notice, cancel: () => abort.current?.abort() };
}
