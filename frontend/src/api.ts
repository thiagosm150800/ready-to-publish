import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

const BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

export type AppKey = "rapido" | "moove" | "urbano" | "log";
export const APP_KEYS: AppKey[] = ["rapido", "moove", "urbano", "log"];
export const APP_LABELS: Record<AppKey, string> = { rapido: "RapidoCar", moove: "MooveCar", urbano: "Urbano Norte", log: "LOG Urbano" };

export type AppFilters = {
  enabled: boolean;
  min_price_per_km: number;
  min_fare: number;
  max_pickup_km: number;
  accept_texts: string[];
  reject_enabled: boolean;
  reject_texts: string[];
  finish_texts: string[];
  target_package: string;
};

export type Settings = {
  apps: Record<AppKey, AppFilters>;
  schedule_enabled: boolean;
  schedule_start: string;
  schedule_end: string;
  schedule_days: number[];
  alert_enabled: boolean;
  notify_enabled: boolean;
  exclusive_enabled: boolean;
  bubble_enabled: boolean;
  blocked_places: string[];
};

export type SettingsUpdate = Partial<Omit<Settings, "apps">> & { apps?: Partial<Record<AppKey, Partial<AppFilters>>> };

export type Ride = {
  id: string;
  app: AppKey;
  price: number;
  trip_km: number;
  pickup_km: number;
  price_per_km: number;
  accepted: boolean;
  reasons: string[];
  source: "rapidocar" | "moovecar" | "urbanonorte" | "logurbano";
  created_at: string;
};

export type RideIn = Omit<Ride, "id">;
export type RideStatus = "all" | "accepted" | "rejected";
export type RideAppFilter = "all" | AppKey;

type HttpError = Error & { status?: number };

async function send<T>(path: string, token: string | null, init?: RequestInit): Promise<{ res: Response; data?: T; error?: HttpError }> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  });
  if (res.ok) return { res, data: (await res.json()) as T };
  let detail = `Erro ${res.status}`;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
    else if (Array.isArray(body?.detail)) detail = "Verifique os dados informados.";
  } catch {
    // keep generic message
  }
  return { res, error: Object.assign(new Error(detail), { status: res.status }) };
}

/** Driver requests (uses the signed-in driver's token). */
async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const sentToken = authToken;
  const { res, data, error } = await send<T>(path, sentToken, init);
  // Only sign out if the token that was rejected is still the active one.
  if (res.status === 401 && sentToken && sentToken === authToken) onUnauthorized?.(error?.message);
  if (error) throw error;
  return data as T;
}

/** Admin requests (separate admin token, never signs the driver out). */
async function adminReq<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const { data, error } = await send<T>(path, token, init);
  if (error) throw error;
  return data as T;
}

// ---------- Auth ----------
let authToken: string | null = null;
let onUnauthorized: ((reason?: string) => void) | null = null;
export function setAuthToken(t: string | null) {
  authToken = t;
}
export function setOnUnauthorized(fn: ((reason?: string) => void) | null) {
  onUnauthorized = fn;
}

export type UserStatus = "pending" | "approved" | "blocked";
export type User = { id: string; cpf: string; name: string; status: UserStatus; expires_at: string | null };
export type CpfLoginResponse =
  | { status: "approved"; access_token: string; token_type: string; user: User }
  | { status: "pending" | "blocked" | "expired" | "other_device" };

export const PRIVACY_URL = `${BASE}/privacy`;

export const apiCpfLogin = (cpf: string, deviceId: string) =>
  req<CpfLoginResponse>("/auth/cpf", { method: "POST", body: JSON.stringify({ cpf, device_id: deviceId }) });
export const apiDeleteAccount = () => req<{ deleted: boolean }>("/auth/account", { method: "DELETE" });
export const apiClearHistory = () => req<{ deleted: number }>("/rides", { method: "DELETE" });

// ---------- Admin ----------
export type AdminUser = User & {
  created_at: string;
  status_changed_at: string | null;
  last_login_at: string | null;
  expired: boolean;
  has_device: boolean;
  device_bound_at: string | null;
  trial_used?: boolean;
  trial_at?: string | null;
};
export type AdminFilter = "all" | UserStatus | "expired";
export type AdminUsers = { users: AdminUser[]; counts: Record<Exclude<AdminFilter, "all">, number> };

export const adminLogin = (password: string) =>
  adminReq<{ access_token: string }>("/admin/login", "", { method: "POST", body: JSON.stringify({ password }) });
export const adminListUsers = (token: string, status: AdminFilter) => adminReq<AdminUsers>(`/admin/users?status=${status}`, token);
export type AdminUserUpdate = { status?: UserStatus; name?: string; access_days?: number; reset_device?: boolean; trial?: boolean };
export const adminUpdateUser = (token: string, id: string, body: AdminUserUpdate) =>
  adminReq<AdminUser>(`/admin/users/${id}`, token, { method: "PATCH", body: JSON.stringify(body) });
export const adminDeleteUser = (token: string, id: string) => adminReq<{ deleted: boolean }>(`/admin/users/${id}`, token, { method: "DELETE" });

// ---------- Formatting ----------
export const brl = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;
export const num = (v: number, d = 1) => v.toFixed(d).replace(".", ",");

export function maskCpf(v: string) {
  const d = v.replace(/\D/g, "").slice(0, 11);
  return d
    .replace(/^(\d{3})(\d)/, "$1.$2")
    .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d{1,2})$/, ".$1-$2");
}

export function isValidCpf(v: string) {
  const c = v.replace(/\D/g, "");
  if (c.length !== 11 || /^(\d)\1{10}$/.test(c)) return false;
  for (const n of [9, 10]) {
    let s = 0;
    for (let i = 0; i < n; i++) s += Number(c[i]) * (n + 1 - i);
    if (((s * 10) % 11) % 10 !== Number(c[n])) return false;
  }
  return true;
}

// ---------- Hooks ----------
export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => req<User>("/auth/me") });
}

export function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: () => req<Settings>("/settings") });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsUpdate) => req<Settings>("/settings", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: (data) => qc.setQueryData(["settings"], data),
  });
}

export function useRides(status: RideStatus, app: RideAppFilter) {
  return useQuery({ queryKey: ["rides", status, app], queryFn: () => req<Ride[]>(`/rides?status=${status}&app=${app}`) });
}

export type DaySummary = Record<AppKey, { accepted: number; rejected: number; earned: number }>;

export function useTodaySummary() {
  return useQuery({
    queryKey: ["rides", "summary"],
    queryFn: () => {
      const midnight = new Date();
      midnight.setHours(0, 0, 0, 0);
      return req<DaySummary>(`/rides/summary?since=${encodeURIComponent(midnight.toISOString())}`);
    },
  });
}

export function uploadRides(items: RideIn[]) {
  return req<{ inserted: number }>("/rides/bulk", { method: "POST", body: JSON.stringify(items) });
}
