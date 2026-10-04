// Shapes returned by the API, plus helpers that turn them into words an owner understands.
import { fa } from "../ui";

export type Field = { key: string; label: string; kind: "text" | "phone" | "number" | "choice"; choices: string[]; required: boolean };
export type Schedule = {
  days: { weekday: number; start: string; end: string }[]; duration_minutes: number; capacity: number; days_ahead: number;
  staff: string[]; break_start?: string | null; break_end?: string | null;
};
export type Slot = { id: string; label: string; capacity: number; weekday?: number | null; time?: string | null };
export type Item = { id: string; name: string; price: number; options: { name: string; choices: string[] }[] };
export type Block =
  | { type: "message"; id: string; text: string }
  | { type: "form"; id: string; title: string; fields: Field[]; done_text: string }
  | { type: "booking"; id: string; title: string; slots: Slot[]; waitlist: boolean; schedule?: Schedule | null; allow_cancel?: boolean; cancel_deadline_hours?: number; occurrences?: number; fields: Field[]; confirm_text: string; full_text: string; waitlist_text: string }
  | { type: "catalog_order"; id: string; title: string; items: Item[]; max_items: number; min_total: number; fields: Field[]; confirm_text: string; delivery_fee?: number; free_delivery_over?: number; discount_codes?: { code: string; percent: number; amount: number; min_total: number; max_uses: number }[] }
  | { type: "contact"; id: string; title: string; prompt_text?: string; sent_text?: string }
  | { type: "faq"; id: string; title: string; entries: { question: string; answer: string }[]; prompt_text?: string; not_found_text?: string }
  | { type: "admin_notify"; id: string; on: string; text: string };
export type Spec = { name: string; welcome: string; menu: { label: string; block: string }[]; blocks: Block[] };
export type Bot = { id: number; name: string; version: number; spec: Spec | null };

export type Rec = { id: number; collection: string; data: Record<string, any>; created_at: string };
export type TestRes = { name: string; passed: boolean; failures: string[]; transcript: { user: string; bot: string }[] };
export type DiffRow = { path: string; before: any; after: any };
export type Ver = { version: number; note: string; created_at: string; diff: DiffRow[]; tests_passed: number; tests_total: number };
export type ChatMsg = { role: "user" | "assistant"; content: string };
export type RunResult = { message: string; version?: number; tests?: TestRes[]; cost_usd?: number };
export type RunStatus = "running" | "needs_input" | "done" | "failed" | "declined";

export const BLOCK_KIND: Record<Block["type"], string> = {
  message: "پیام", form: "فرم", booking: "نوبت‌دهی", catalog_order: "سفارش", admin_notify: "اعلان به مدیر", faq: "پرسش‌های متداول", contact: "پیام به مدیر",
};
export const FIELD_KIND: Record<Field["kind"], string> = { text: "متن", phone: "موبایل · بررسی قالب", number: "عدد", choice: "انتخابی" };

export function blockTitle(b: Block): string {
  if (b.type === "message") return b.text.length > 36 ? b.text.slice(0, 36) + "…" : b.text;
  if (b.type === "admin_notify") return b.text?.trim() || "اعلان به مدیر";
  return b.title;
}

export const toman = (n: number) => `${n.toLocaleString("fa-IR")} تومان`;

/** Turn button data the simulator sent ("s:sat9", "m:0", "i:latte") back into the label the user tapped. */
export const WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]; // 0 = Saturday

/** Gregorian -> Jalali (same algorithm as the backend's app/dates.py). */
export function toJalali(gy: number, gm: number, gd: number): [number, number, number] {
  const gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  let jy: number;
  if (gy > 1600) { jy = 979; gy -= 1600; } else { jy = 0; gy -= 621; }
  const gy2 = gm > 2 ? gy + 1 : gy;
  let days = 365 * gy + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) - 80 + gd + gdm[gm - 1];
  jy += 33 * Math.floor(days / 12053); days %= 12053;
  jy += 4 * Math.floor(days / 1461); days %= 1461;
  if (days > 365) { jy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
  const jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
  const jd = days < 186 ? 1 + (days % 31) : 1 + ((days - 186) % 30);
  return [jy, jm, jd];
}
export function jalaliFromYmd(ymd: string): string {
  const [jy, jm, jd] = toJalali(+ymd.slice(0, 4), +ymd.slice(4, 6), +ymd.slice(6, 8));
  return `${jy}/${String(jm).padStart(2, "0")}/${String(jd).padStart(2, "0")}`;
}
/** Plain-Persian lines describing an appointment schedule, e.g. «شنبه تا چهارشنبه · ۰۹:۰۰ تا ۱۸:۰۰». */
export function scheduleLines(sc: Schedule): string[] {
  const days = [...sc.days].sort((a, b) => a.weekday - b.weekday);
  const groups: { from: number; to: number; start: string; end: string }[] = [];
  for (const d of days) {
    const last = groups[groups.length - 1];
    if (last && last.start === d.start && last.end === d.end && d.weekday === last.to + 1) last.to = d.weekday;
    else groups.push({ from: d.weekday, to: d.weekday, start: d.start, end: d.end });
  }
  const lines = groups.map((g) => `${g.from === g.to ? WEEKDAYS[g.from] : `${WEEKDAYS[g.from]} تا ${WEEKDAYS[g.to]}`} · ${g.start} تا ${g.end}`);
  lines.push(`هر نوبت ${sc.duration_minutes} دقیقه · ظرفیت هر ساعت ${sc.capacity}${sc.break_start ? ` · استراحت ${sc.break_start} تا ${sc.break_end}` : ""} · رزرو تا ${sc.days_ahead} روز آینده`);
  if (sc.staff.length) lines.push(`تقویم جدا برای: ${sc.staff.join("، ")}`);
  return lines;
}

/** «هر هفته · پنجشنبه ساعت ۱۰:۰۰» for a weekly slot, null for a one-off. */
export function weeklyText(s: Slot): string | null {
  return s.weekday == null ? null : `هر هفته · ${WEEKDAYS[s.weekday]} ساعت ${s.time ?? ""}`;
}

export function readableInput(spec: Spec | null, s: string): string {
  if (s === "/start") return "شروع گفت‌وگو";
  if (!spec) return s;
  const [k, v] = [s.slice(0, 2), s.slice(2)];
  if (k === "m:") return spec.menu[+v]?.label ?? s;
  for (const b of spec.blocks) {
    if (k === "s:" && b.type === "booking") {
      const [sid, ymd] = v.split("@"); // weekly slots carry their date: "s:thu@20261008"
      const x = b.slots.find((x) => x.id === sid);
      if (x) return ymd && /^\d{8}$/.test(ymd) ? `${x.label} — ${jalaliFromYmd(ymd)}` : x.label;
    }
    if (k === "i:" && b.type === "catalog_order") { const x = b.items.find((x) => x.id === v); if (x) return x.name; }
  }
  return s;
}

export function parseDate(iso: string) {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z");
}

export function ago(iso: string): string {
  const mins = Math.round((Date.now() - parseDate(iso).getTime()) / 60000);
  if (mins < 1) return "همین الان";
  if (mins < 60) return `${fa(mins)} دقیقه پیش`;
  if (mins < 60 * 24) return `${fa(Math.round(mins / 60))} ساعت پیش`;
  return parseDate(iso).toLocaleDateString("fa-IR", { month: "long", day: "numeric" });
}

// ---------- agent run events → timeline ----------
export type Step = { text: string; subs: string[]; fail: boolean };

export function toSteps(events: string[]): Step[] {
  const out: Step[] = [];
  for (const e of events) {
    if (e.startsWith("✗") && out.length) out[out.length - 1].subs.push(e.replace(/^✗\s*/, ""));
    else out.push({ text: e.replace(/\s*✅$/, ""), subs: [], fail: /ناموفق|ممکن نشد/.test(e) });
  }
  return out;
}

const PHASES: [RegExp, number][] = [
  [/ذخیره شد/, 1], [/همه تست‌ها موفق/, 0.92], [/رفع خطا/, 0.78], [/ناموفق/, 0.7], [/اجرای .* تست/, 0.62],
  [/سناریوهای تست/, 0.48], [/ساختار/, 0.3], [/بررسی/, 0.1],
];
export function progressOf(events: string[]): number {
  const last = events.at(-1) ?? "";
  return PHASES.find(([re]) => re.test(last))?.[1] ?? 0.05;
}

/** "❓ ...\n1. q\n2. q" → ["q", "q"] */
export function parseQuestions(content: string): string[] | null {
  if (!content.startsWith("❓")) return null;
  const qs = content.split("\n").map((l) => l.match(/^\s*[\d۰-۹]+[.)]\s*(.+)$/)?.[1]).filter(Boolean) as string[];
  return qs.length ? qs : null;
}

// ---------- version diff → sentences ----------
const FIELD_NAME: Record<string, string> = {
  name: "نام ربات", welcome: "پیام خوش‌آمد", menu: "منو", waitlist: "لیست انتظار", capacity: "ظرفیت", allow_cancel: "لغو توسط مشتری", cancel_deadline_hours: "مهلت لغو (ساعت)", cancel_window_minutes: "مهلت لغو سفارش (دقیقه)", weekday: "روز هفته", time: "ساعت", occurrences: "تعداد تاریخ‌های پیشنهادی", label: "عنوان",
  text: "متن", title: "عنوان", confirm_text: "پیام تأیید", full_text: "پیام تکمیل ظرفیت", waitlist_text: "پیام لیست انتظار",
  done_text: "پیام پایان فرم", price: "قیمت", min_total: "حداقل مبلغ سفارش", max_items: "حداکثر تعداد آیتم", fields: "سؤال‌های فرم",
  slots: "زمان‌ها", items: "آیتم‌ها", on: "زمان ارسال اعلان", kind: "نوع", required: "اجباری", choices: "گزینه‌ها", options: "گزینه‌ها",
  block: "مقصد", blocks: "بخش‌ها", type: "نوع",
};

export function showValue(v: any, key?: string): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "فعال" : "غیرفعال";
  if (typeof v === "number") return key === "price" || key === "min_total" ? toman(v) : fa(v);
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.map((x) => showValue(x)).join("، ") || "خالی";
  return v.label ?? v.name ?? v.title ?? (v.text ? String(v.text).slice(0, 40) : "یک مورد");
}

export type Change = { where: string; field: string; before: string; after: string; kind: "changed" | "added" | "removed"; long: boolean };

export function humanizeDiff(rows: DiffRow[], spec: Spec | null): Change[] {
  const blocks = new Map((spec?.blocks ?? []).map((b) => [b.id, b]));
  return rows.map(({ path, before, after }) => {
    const parts = path.match(/[^.[\]]+/g) ?? [path];
    const where: string[] = [];
    let field = "";
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (parts[i - 1] === "blocks") { const b = blocks.get(p); where.push(b ? blockTitle(b) : p); continue; }
      if (parts[i - 1] === "slots") {
        const s = [...blocks.values()].flatMap((b) => (b.type === "booking" ? b.slots : [])).find((s) => s.id === p);
        where.push(s?.label ?? p); continue;
      }
      if (parts[i - 1] === "items") {
        const it = [...blocks.values()].flatMap((b) => (b.type === "catalog_order" ? b.items : [])).find((s) => s.id === p);
        where.push(it?.name ?? p); continue;
      }
      if (p === "blocks" || p === "slots" || p === "items") { field = FIELD_NAME[p]; continue; }
      field = FIELD_NAME[p] ?? (/^\d+$/.test(p) ? `${field} ${fa(+p + 1)}` : p);
    }
    const key = parts.at(-1);
    const kind = before == null ? "added" : after == null ? "removed" : "changed";
    const b = showValue(before, key), a = showValue(after, key);
    return { where: where.join(" › "), field: field || "ربات", before: b, after: a, kind, long: a.length + b.length > 60 };
  });
}
