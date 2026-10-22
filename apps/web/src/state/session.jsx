// Session store (Phase 1) — who is logged in, backed by the existing token
// client in lib/api.js. This replaces each screen re-deriving "am I logged
// in" from isAuthenticated() ad hoc; ProtectedRoute and the dashboard shell
// both read from here.
//
// The user object itself is never persisted to localStorage (only the
// tokens are, via lib/api.js) — on every fresh load with existing tokens we
// re-fetch GET /auth/me/, so a change made server-side (e.g. name updated
// elsewhere) is never served stale, and there's one less copy of user data
// sitting in browser storage.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { authApi, saveSession as persistTokens } from "../auth/api.js";
import { isAuthenticated } from "../lib/api.js";
import { clearAllDrafts } from "../lib/quizDraft.js";

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  // status: "loading" | "authenticated" | "anonymous"
  const [state, setState] = useState({ status: "loading", user: null });

  const bootstrap = useCallback(async () => {
    if (!isAuthenticated()) {
      setState({ status: "anonymous", user: null });
      return;
    }
    try {
      const user = await authApi.me();
      setState({ status: "authenticated", user });
    } catch (e) {
      // Both tokens are dead (refresh already failed inside apiFetch and
      // cleared them) — nothing to recover here.
      setState({ status: "anonymous", user: null });
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  // Call after a successful login/signup/claim response (which already has
  // { access, refresh, user }) — stores the tokens and updates state in one
  // step so the very next render sees status: "authenticated".
  const login = useCallback((data) => {
    const user = persistTokens(data);
    setState({ status: "authenticated", user });
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    clearAllDrafts();
    setState({ status: "anonymous", user: null });
  }, []);

  return (
    <SessionContext.Provider value={{ ...state, login, logout, refresh: bootstrap }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession() must be called within a <SessionProvider>.");
  return ctx;
}
