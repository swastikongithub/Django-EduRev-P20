// Money and time helpers. FoodLoop shows every time in India Standard Time (IST), whatever the
// browser's own time zone, because pickup times belong to the kitchen's clock.

const IST = "Asia/Kolkata";
const IST_OFFSET = "+05:30";

const rupees = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

export function formatRupees(paise: number): string {
  const text = rupees.format(paise / 100);
  return text.endsWith(".00") ? text.slice(0, -3) : text;
}

export function rupeesToPaise(value: string): number {
  return Math.round(Number.parseFloat(value || "0") * 100);
}

export function paiseToRupeesInput(paise: number): string {
  return (paise / 100).toString();
}

const timeFormat = new Intl.DateTimeFormat("en-IN", { timeZone: IST, hour: "numeric", minute: "2-digit" });
const dayFormat = new Intl.DateTimeFormat("en-IN", { timeZone: IST, weekday: "short", day: "numeric", month: "short" });
const dateKeyFormat = new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" });

export function formatTime(iso: string): string {
  // Some browsers use a narrow no-break space before "pm", or "PM"; normalise to "3:45 pm".
  return timeFormat.format(new Date(iso)).replace(/[\u202f\u00a0]/g, " ").toLowerCase();
}

function dayLabel(date: Date, now = new Date()): string {
  const key = dateKeyFormat.format(date);
  if (key === dateKeyFormat.format(now)) return "Today";
  const tomorrow = new Date(now.getTime() + 86_400_000);
  if (key === dateKeyFormat.format(tomorrow)) return "Tomorrow";
  const yesterday = new Date(now.getTime() - 86_400_000);
  if (key === dateKeyFormat.format(yesterday)) return "Yesterday";
  return dayFormat.format(date);
}

export function formatDateTime(iso: string, now = new Date()): string {
  return `${dayLabel(new Date(iso), now)}, ${formatTime(iso)}`;
}

export function formatWindow(startIso: string, endIso: string, now = new Date()): string {
  return `${dayLabel(new Date(startIso), now)}, ${formatTime(startIso)} – ${formatTime(endIso)}`;
}

/** "in 42 min", "in 1 h 5 min", "5 min ago". */
export function relativeTime(iso: string, now = new Date()): string {
  const diffMinutes = Math.round((new Date(iso).getTime() - now.getTime()) / 60_000);
  const minutes = Math.abs(diffMinutes);
  let text: string;
  if (minutes < 1) text = "under a minute";
  else if (minutes < 60) text = `${minutes} min`;
  else text = minutes % 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes / 60} h`;
  return diffMinutes >= 0 ? `in ${text}` : `${text} ago`;
}

export function minutesUntil(iso: string, now = new Date()): number {
  return (new Date(iso).getTime() - now.getTime()) / 60_000;
}

/** Value for <input type="datetime-local">, expressed in IST: "2026-10-11T15:30". */
export function toIstInput(date: Date | string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: IST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(date));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

/** Read a datetime-local value as IST and return an ISO string with the offset. */
export function fromIstInput(value: string): string {
  return new Date(`${value}:00${IST_OFFSET}`).toISOString();
}

export function addMinutes(date: Date, minutes: number): Date {
  return new Date(date.getTime() + minutes * 60_000);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}
