import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { setAuthToken, setOnUnauthorized, User } from "@/src/api";
import { resetNativeForLogout } from "@/src/native/rideFilter";
import { queryClient } from "@/src/query-client";
import { storage } from "@/src/utils/storage";

const TOKEN_KEY = "auth_token";
const USER_KEY = "auth_user";

type AuthState = {
  ready: boolean;
  token: string | null;
  user: User | null;
  signIn: (token: string, user: User) => Promise<void>;
  signOut: () => Promise<void>;
  /** Why the app signed the driver out on its own (e.g. access expired). */
  exitReason: string | null;
  clearExitReason: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [exitReason, setExitReason] = useState<string | null>(null);
  const clearExitReason = useCallback(() => setExitReason(null), []);

  const signOut = useCallback(async () => {
    resetNativeForLogout();
    setAuthToken(null);
    setToken(null);
    setUser(null);
    queryClient.clear();
    await storage.secureRemove(TOKEN_KEY);
    await storage.removeItem(USER_KEY);
  }, []);

  const signIn = useCallback(async (t: string, u: User) => {
    setAuthToken(t);
    queryClient.clear();
    await storage.secureSet(TOKEN_KEY, t);
    await storage.setItem(USER_KEY, JSON.stringify(u));
    setUser(u);
    setToken(t);
  }, []);

  useEffect(() => {
    setOnUnauthorized((reason) => {
      setExitReason(reason ?? null);
      signOut();
    });
    (async () => {
      const t = await storage.secureGet<string | null>(TOKEN_KEY, null);
      const raw = await storage.getItem<string | null>(USER_KEY, null);
      if (t) {
        setAuthToken(t);
        setToken(t);
        if (raw) {
          try {
            setUser(JSON.parse(raw) as User);
          } catch {
            // ignore corrupt cache
          }
        }
      }
      setReady(true);
    })();
    return () => setOnUnauthorized(null);
  }, [signOut]);

  const value = useMemo(
    () => ({ ready, token, user, signIn, signOut, exitReason, clearExitReason }),
    [ready, token, user, signIn, signOut, exitReason, clearExitReason],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
