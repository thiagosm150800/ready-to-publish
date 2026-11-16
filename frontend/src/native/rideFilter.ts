import { Platform } from "react-native";
import { requireOptionalNativeModule } from "expo";

import type { RideIn, Settings } from "@/src/api";

type RideFilterNative = {
  setConfig(json: string): void;
  isServiceEnabled(): boolean;
  openAccessibilitySettings(): void;
  getPendingEvents(): string;
  clearPendingEvents(): void;
  setLearning(on: boolean): void;
  getCapturedScreens(): string;
};

// Only present in an Android build (APK). Null in Expo Go, iOS and web.
const mod = Platform.OS === "android" ? requireOptionalNativeModule<RideFilterNative>("RideFilter") : null;

export const nativeAvailable = !!mod;

// Set once the driver accepts the in-app accessibility disclosure (app/aviso.tsx).
export const DISCLOSURE_KEY = "a11y_disclosure_ok";

export type CapturedScreen = { package: string; at: number; texts: string[] };
export type CapturedScreens = { learning: boolean; rapido: CapturedScreen | null; moove: CapturedScreen | null };

export function getCapturedScreens(): CapturedScreens | null {
  return mod ? (JSON.parse(mod.getCapturedScreens()) as CapturedScreens) : null;
}

export function setLearning(on: boolean) {
  mod?.setLearning(on);
}

export function pushConfig(s: Settings) {
  mod?.setConfig(JSON.stringify(s));
}

export function isServiceEnabled(): boolean {
  return mod ? mod.isServiceEnabled() : false;
}

export function openAccessibilitySettings() {
  mod?.openAccessibilitySettings();
}

export function takePendingEvents(): RideIn[] {
  if (!mod) return [];
  return JSON.parse(mod.getPendingEvents() || "[]") as RideIn[];
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
