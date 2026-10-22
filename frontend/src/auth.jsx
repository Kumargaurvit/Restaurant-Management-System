import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, getToken, request, setToken } from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // "loading" while we check a saved token, then "ready".
  const [phase, setPhase] = useState(getToken() ? "loading" : "ready");

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    if (!getToken()) return undefined;
    const controller = new AbortController();
    request("/api/auth/me", { signal: controller.signal })
      .then(setUser)
      .catch((error) => {
        if (error.name === "AbortError") return;
        if (error instanceof ApiError && error.status === 401) setToken(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setPhase("ready");
      });
    return () => controller.abort();
  }, []);

  const signIn = useCallback(async (path, body) => {
    const result = await request(path, { method: "POST", body });
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const value = useMemo(
    () => ({
      user,
      phase,
      logout,
      login: (email, password) => signIn("/api/auth/login", { email, password }),
      setup: (name, email, password) => signIn("/api/auth/bootstrap", { name, email, password }),
    }),
    [user, phase, logout, signIn],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

// Mirrors the backend role rules so the UI hides actions the server would refuse.
export const canManage = (user) => ["owner", "manager"].includes(user?.role);
export const canBill = (user) => ["owner", "manager", "cashier"].includes(user?.role);
