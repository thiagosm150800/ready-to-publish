import * as Application from "expo-application";
import { Platform } from "react-native";

import { storage } from "@/src/utils/storage";

const KEY = "device_id";
let cached: string | null = null;

function randomId() {
  return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
}

/**
 * Stable id of this phone, used to lock each CPF to one device.
 * Android: the Android ID (survives reinstalling the app). Others: a random id kept in secure storage.
 */
export async function getDeviceId(): Promise<string> {
  if (cached) return cached;
  if (Platform.OS === "android") {
    const id = Application.getAndroidId();
    if (id) return (cached = `a-${id}`);
  }
  let id = await storage.secureGet<string | null>(KEY, null);
  if (!id) {
    id = `r-${randomId()}`;
    await storage.secureSet(KEY, id);
  }
  return (cached = id);
}
