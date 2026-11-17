import { Platform } from "react-native";
import { requireOptionalNativeModule } from "expo";

import { APP_KEYS, type AppKey, type RideIn, type Settings } from "@/src/api";

type RideFilterNative = {
  setConfig(json: string): void;
  isServiceEnabled(): boolean;
  openAccessibilitySettings(): void;
  getPendingEvents(): string;
  clearPendingEvents(): void;
  setLearning(on: boolean): void;
  getCapturedScreens(): string;
  getDiagnostics?(): string;
  getBusy?(): string;
  clearBusy?(): void;
};

// Only present in an Android build (APK). Null in Expo Go, iOS and web.
const mod = Platform.OS === "android" ? requireOptionalNativeModule<RideFilterNative>("RideFilter") : null;

export const nativeAvailable = !!mod;

// Set once the driver accepts the in-app accessibility disclosure (app/aviso.tsx).
export const DISCLOSURE_KEY = "a11y_disclosure_ok";

export type CapturedScreen = { package: string; at: number; texts: string[] };
export type CapturedScreens = { learning: boolean } & Partial<Record<AppKey, CapturedScreen | null>>;

export function getCapturedScreens(): CapturedScreens | null {
  return mod ? (JSON.parse(mod.getCapturedScreens()) as CapturedScreens) : null;
}

export function setLearning(on: boolean) {
  mod?.setLearning(on);
}

export type AppDiag = { at: number; status: string; event_pkg: string; roots: string[]; texts?: string[] };
export type Diagnostics = { listening?: string[]; connected_at?: number; last_pkg?: string; last_pkg_at?: number; } & Partial<Record<AppKey, AppDiag>>;

/** What the Android service last saw for each app (null outside the APK or on older builds). */
export function getDiagnostics(): Diagnostics | null {
  if (!mod?.getDiagnostics) return null;
  try {
    return JSON.parse(mod.getDiagnostics() || "{}") as Diagnostics;
  } catch {
    return null;
  }
}

export function pushConfig(s: Settings) {
  mod?.setConfig(JSON.stringify(s));
}

export type Busy = { app: AppKey; since: number; notification_id?: number };

/** Ride in progress accepted by the bot: the other app's bot is off-line until it ends. */
export function getBusy(): Busy | null {
  const raw = mod?.getBusy?.();
  if (!raw) return null;
  try {
    const b = JSON.parse(raw) as Busy;
    // Same 2h safety expiry as the Android service; ignore apps that were removed (99).
    if (!APP_KEYS.includes(b.app)) return null;
    return Date.now() - b.since > 2 * 60 * 60 * 1000 ? null : b;
  } catch {
    return null;
  }
}

/** Ride finished (or driver tapped "Voltar online"): both bots online again. */
export function clearBusy() {
  mod?.clearBusy?.();
}

export function isServiceEnabled(): boolean {
  return mod ? mod.isServiceEnabled() : false;
}

export function openAccessibilitySettings() {
  mod?.openAccessibilitySettings();
}

export function takePendingEvents(): RideIn[] {
  if (!mod) return [];
  // Rides of removed apps (99) left on the phone would make the whole upload fail.
  return (JSON.parse(mod.getPendingEvents() || "[]") as RideIn[]).filter((e) => APP_KEYS.includes(e.app));
}

export function clearPendingEvents() {
  mod?.clearPendingEvents();
}

/** On logout: stop the service from acting with the previous driver's settings. */
export function resetNativeForLogout() {
  if (!mod) return;
  mod.setConfig(JSON.stringify({ apps: {} }));
  mod.clearPendingEvents();
  mod.setLearning(false);
}
