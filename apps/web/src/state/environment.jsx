// Active-environment store (Phase 1). Holds which Teacher Environment the
// current session is "in", for the dashboard shell and every tenant-scoped
// API call the frontend will make from Phase 2 onward.
//
// THE RULE: the id persisted in localStorage (lib/api.js) is only ever a
// convenience — the frontend never treats it as authorized on its own. On
// every fresh mount (and whenever the session becomes authenticated), a
// persisted id is re-checked against the backend via GET
// /environments/context/ (environments/tenancy.py on the server — the only
// place that actually decides membership). If the backend rejects it —
// revoked access, wrong account, tampered localStorage — the local value is
// dropped and the person is sent back to pick an environment from the list
// the backend actually authorizes (envApi.teacherList/studentList).
// `select()` below is only ever called with an id that just came back from
// one of those authorized lists (or from the enter/ endpoints, which
// validate ownership server-side) — never with a value the UI invented.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { envApi } from "../auth/api.js";
import { clearActiveEnvironmentId, getActiveEnvironmentId, setActiveEnvironmentId } from "../lib/api.js";
import { useSession } from "./session.jsx";

const EnvironmentContext = createContext(null);

export function EnvironmentProvider({ children }) {
  const { status: sessionStatus } = useSession();
  // status: "idle" | "checking" | "ready" | "none"
  const [state, setState] = useState({ status: "idle", environment: null });

  const revalidate = useCallback(async () => {
    const id = getActiveEnvironmentId();
    if (!id) {
      setState({ status: "none", environment: null });
      return;
    }
    setState((s) => ({ ...s, status: "checking" }));
    try {
      const data = await envApi.context(); // reads the id back out of storage itself
      setState({ status: "ready", environment: data });
    } catch {
      clearActiveEnvironmentId();
      setState({ status: "none", environment: null });
    }
  }, []);

  useEffect(() => {
    if (sessionStatus === "authenticated") revalidate();
    if (sessionStatus === "anonymous") {
      clearActiveEnvironmentId();
      setState({ status: "none", environment: null });
    }
    // sessionStatus === "loading": leave environment state as-is until we know.
  }, [sessionStatus, revalidate]);

  // `env` must come from an authorized source — see file header. `role`
  // defaults to "owner" since today only teachers reach the dashboard.
  const select = useCallback((env, role = "owner") => {
    setActiveEnvironmentId(env.id);
    setState({ status: "ready", environment: { id: env.id, name: env.name, initials: env.initials, role } });
  }, []);

  const clear = useCallback(() => {
    clearActiveEnvironmentId();
    setState({ status: "none", environment: null });
  }, []);

  return (
    <EnvironmentContext.Provider value={{ ...state, select, clear, revalidate }}>
      {children}
    </EnvironmentContext.Provider>
  );
}

export function useEnvironment() {
  const ctx = useContext(EnvironmentContext);
  if (!ctx) throw new Error("useEnvironment() must be called within an <EnvironmentProvider>.");
  return ctx;
}
