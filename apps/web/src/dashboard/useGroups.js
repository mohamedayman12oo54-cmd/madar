import { useCallback, useEffect, useState } from "react";
import { groupsApi } from "../lib/academicsApi.js";
import { ApiError } from "../lib/api.js";

/** Every group in the active environment, across all grades — Sessions and
 * Attendance both need a flat "pick a group" selector rather than the
 * Groups page's grade-first tabs. */
export function useGroups() {
  const [groups, setGroups] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);

  const reload = useCallback(() => {
    setStatus((s) => (s === "ready" ? "ready" : "loading"));
    groupsApi.list()
      .then((data) => { setGroups(Array.isArray(data) ? data : data.results || []); setStatus("ready"); })
      .catch((e) => { setError(e instanceof ApiError ? e.message : "تعذّر تحميل المجموعات."); setStatus("error"); });
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return { groups, status, error, reload };
}
