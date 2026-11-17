import { PermissionsAndroid, Platform } from "react-native";

export type NotifyPermission = "granted" | "undetermined" | "denied" | "blocked" | "unsupported";

// Read lazily: PermissionsAndroid is undefined on web (react-native-web), so a top-level access crashes.
const perm = () => PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS;
// Android 13 (API 33)+ asks at runtime; older versions allow notifications by default.
const needsRuntime = Platform.OS === "android" && Number(Platform.Version) >= 33;

export async function checkNotifyPermission(): Promise<NotifyPermission> {
  if (Platform.OS !== "android") return "unsupported";
  if (!needsRuntime) return "granted";
  return (await PermissionsAndroid.check(perm())) ? "granted" : "undetermined";
}

export async function requestNotifyPermission(): Promise<NotifyPermission> {
  if (Platform.OS !== "android") return "unsupported";
  if (!needsRuntime) return "granted";
  const r = await PermissionsAndroid.request(perm());
  if (r === PermissionsAndroid.RESULTS.GRANTED) return "granted";
  return r === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN ? "blocked" : "denied";
}
