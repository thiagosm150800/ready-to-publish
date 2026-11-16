import type { Settings } from "@/src/api";

export const DAY_LABELS = ["D", "S", "T", "Q", "Q", "S", "S"];
export const DAY_NAMES = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

const toMin = (t: string) => {
  const [h, m] = t.split(":").map((x) => parseInt(x, 10));
  return (h || 0) * 60 + (m || 0);
};

export const isValidTime = (t: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(t);

/** Same rule as the Android service: days 0=Sunday, window may cross midnight. */
export function inSchedule(s: Pick<Settings, "schedule_enabled" | "schedule_start" | "schedule_end" | "schedule_days">, now = new Date()) {
  if (!s.schedule_enabled) return true;
  if (!s.schedule_days.includes(now.getDay())) return false;
  const m = now.getHours() * 60 + now.getMinutes();
  const start = toMin(s.schedule_start);
  const end = toMin(s.schedule_end);
  return start <= end ? m >= start && m < end : m >= start || m < end;
}

/** "às 06:00" if the window opens later today, else "seg às 06:00". */
export function nextStartLabel(s: Pick<Settings, "schedule_start" | "schedule_days">, now = new Date()) {
  const today = now.getDay();
  const startsLaterToday = s.schedule_days.includes(today) && now.getHours() * 60 + now.getMinutes() < toMin(s.schedule_start);
  if (startsLaterToday) return `às ${s.schedule_start}`;
  for (let i = 1; i <= 7; i++) {
    const d = (today + i) % 7;
    if (s.schedule_days.includes(d)) return `${i === 1 ? "amanhã" : DAY_NAMES[d].toLowerCase()} às ${s.schedule_start}`;
  }
  return "nenhum dia escolhido";
}

export function scheduleSummary(s: Pick<Settings, "schedule_start" | "schedule_end" | "schedule_days">) {
  const days = s.schedule_days.length === 7 ? "Todos os dias" : [...s.schedule_days].sort().map((d) => DAY_NAMES[d]).join(", ") || "Nenhum dia";
  return `${s.schedule_start}–${s.schedule_end} · ${days}`;
}
