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
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { authApi, saveSession as persistTokens } from "../auth/api.js";
import { isAuthenticated, refreshAccessToken } from "../lib/api.js";
import { clearAllDrafts } from "../lib/quizDraft.js";
import { startKeepAlive } from "../lib/keepalive.js";
import { detachDevice, syncPush } from "../lib/push.js";

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  // status: "loading" | "authenticated" | "anonymous"; `offline` = still "loading" because the server cannot
  // be reached right now (the page says so and keeps trying — it never turns a bad connection into a logout).
  const [state, setState] = useState({ status: "loading", user: null, offline: false });
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true; // (React StrictMode mounts, unmounts and mounts again in development)
    return () => {
      alive.current = false;
    };
  }, []);

  const bootstrap = useCallback(async () => {
    if (!isAuthenticated()) {
      setState({ status: "anonymous", user: null });
      return;
    }
    // Only the SERVER refusing the credentials ends a session here. A network drop or a 5xx (the phone just
    // woke up, the server restarted) must never look like a logout: keep the tokens and keep retrying.
    for (let attempt = 0; alive.current; attempt += 1) {
      try {
        const user = await authApi.me();
        if (alive.current) setState({ status: "authenticated", user, offline: false });
        return;
      } catch (e) {
        if (!isAuthenticated()) break; // refresh was rejected and cleared the tokens: really signed out
        if (e?.status === 401 || e?.status === 403) break;
        if (attempt >= 1) setState((s) => (s.status === "loading" ? { ...s, offline: true } : s));
        await new Promise((r) => setTimeout(r, Math.min(1200 * (attempt + 1), 8000)));
      }
    }
    if (alive.current) setState({ status: "anonymous", user: null, offline: false });
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  // Call after a successful login/signup/claim response (which already has
  // { access, refresh, user }) — stores the tokens and updates state in one
  // step so the very next render sees status: "authenticated".
  const login = useCallback((data) => {
    const user = persistTokens(data);
    setState({ status: "authenticated", user, offline: false });
  }, []);

  const logout = useCallback(async () => {
    await detachDevice(); // this device must stop receiving the signed-out user's notifications
    await authApi.logout();
    clearAllDrafts();
    setState({ status: "anonymous", user: null, offline: false });
  }, []);

  // Signed in: re-attach this device to the account if the user enabled notifications here before.
  useEffect(() => {
    if (state.status === "authenticated" && state.user?.id) syncPush(state.user.id);
  }, [state.status, state.user?.id]);

  // Signed in: there is NO idle sign-out. The person stays signed in for as long as the page is open (and
  // across closing it, within the refresh token's life) and leaves only by pressing "log out". While the page
  // is open the credentials are renewed in the background so they never run out under someone who is reading.
  // Only if the server really refuses the renewal (password reset elsewhere, account disabled) do we send the
  // person back to the login page.
  useEffect(() => {
    if (state.status !== "authenticated") return undefined;
    return startKeepAlive(async () => {
      await refreshAccessToken();
      if (alive.current && !isAuthenticated()) setState({ status: "anonymous", user: null, offline: false });
    });
  }, [state.status]);

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
