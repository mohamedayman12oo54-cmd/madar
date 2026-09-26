import { useCallback, useEffect, useState } from "react";
import { gradesApi } from "../lib/academicsApi.js";
import { ApiError } from "../lib/api.js";

/** Grades change rarely and every other Phase 2 screen needs the list (for
 * filters, or to pick one when creating a group/enrollment) — one shared
 * loader instead of every page re-fetching/re-handling errors itself. */
export function useGrades() {
  const [grades, setGrades] = useState([]);
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [error, setError] = useState(null);

  const reload = useCallback(() => {
    setStatus((s) => (s === "ready" ? "ready" : "loading")); // don't flash a spinner on a silent refresh
    gradesApi.list()
      .then((data) => {
        setGrades(Array.isArray(data) ? data : data.results || []);
        setStatus("ready");
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e.message : "تعذّر تحميل الصفوف الدراسية.");
        setStatus("error");
      });
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return { grades, status, error, reload };
}
