// Shapes returned by the API, plus helpers that turn them into words an owner understands.
import { fa } from "../ui";

export type Field = { key: string; label: string; kind: "text" | "phone" | "number" | "choice" | "multi" | "email" | "national_id" | "date" | "location" | "file"; choices: string[]; required: boolean;
  min_value?: number | null; max_value?: number | null; show_if?: { field: string; equals: string[] } | null; scores?: number[] };
export type FaqEntry = { question: string; answer: string; then?: string; then_label?: string; alternates?: string[]; category?: string; media?: "none" | "image"; location?: { latitude: number; longitude: number } | null };
export type Schedule = {
  days: { weekday: number; start: string; end: string }[]; duration_minutes: number; capacity: number; days_ahead: number;
  staff: string[]; break_start?: string | null; break_end?: string | null;
  services?: { id: string; name: string; duration_minutes: number; price: number; staff?: string[] }[];
  staff_hours?: { staff: string; days: { weekday: number; start: string; end: string }[] }[];
};
export type Slot = { id: string; label: string; capacity: number; price?: number; weekday?: number | null; time?: string | null };
export type Item = { id: string; name: string; price: number; options: { name: string; choices: string[]; prices?: number[] }[] };
export type Block =
  | { type: "message"; id: string; text: string; variants?: string[]; media?: "none" | "image" | "document" | "album"; album_size?: number; location?: { latitude: number; longitude: number } | null; links?: { label: string; url: string }[];
      contact?: { phone: string; name: string } | null; hours?: { weekday: number; start: string; end: string }[];
      join?: { channel: string; title?: string }[]; join_text?: string }
  | { type: "form"; id: string; title: string; fields: Field[]; done_text: string; confirm_before_submit?: boolean; one_per_customer?: boolean; max_submissions?: number; closes_on?: string; review?: boolean; hot_score?: number }
  | { type: "booking"; id: string; title: string; reminder_hours?: number; slots: Slot[]; waitlist: boolean; schedule?: Schedule | null; allow_cancel?: boolean; cancel_deadline_hours?: number; occurrences?: number; fields: Field[]; confirm_text: string; full_text: string; waitlist_text: string;
      closed_dates?: string[]; min_notice_hours?: number; max_active_per_customer?: number; max_party?: number;
      reminder_confirm?: boolean; no_show_limit?: number; repeat_weeks?: number; deposit?: number }
  | { type: "catalog_order"; id: string; title: string; items: Item[]; max_items: number; min_total: number; fields: Field[]; confirm_text: string; payment?: "none" | "online" | "card"; card_number?: string; card_holder?: string; card_wait_minutes?: number; source?: "inline" | "table"; delivery_fee?: number; delivery_zones?: { label: string; fee: number }[]; free_delivery_over?: number; discount_codes?: { code: string; percent: number; amount: number; min_total: number; max_uses: number; visible?: boolean }[];
      ask_quantity?: boolean; order_hours?: { weekday: number; start: string; end: string }[];
      time_windows?: { start: string; end: string }[]; per_window?: number; window_days?: number; min_lead_minutes?: number;
      restock_alerts?: boolean; low_stock_alert?: number; repeat_order?: boolean }
  | { type: "menu"; id: string; title: string; items: { label: string; block: string }[] }
  | { type: "quiz"; id: string; title: string; questions: { question: string; options: string[]; correct: number; outcomes?: string[]; media?: "none" | "image" }[]; result_text?: string; show_answers?: boolean; shuffle?: boolean; pick?: number; pass_percent?: number; one_attempt?: boolean;
      pass_code?: string; show_history?: boolean; personality?: { id: string; title: string; text: string }[] }
  | { type: "referral"; id: string; title: string; text?: string; goal: number; reward_text?: string; reward_code?: string; tiers?: { goal: number; reward_text: string; reward_code?: string }[]; count_after?: "join" | "order" }
  | { type: "anon_chat"; id: string; title: string; intro_text?: string; topics?: string[]; max_minutes?: number }
  | { type: "feedback"; id: string; title: string; prompt_text?: string; comment_text?: string; thanks_text?: string; aspects?: string[]; follow_up_below?: number; after?: string; after_hours?: number }
  | { type: "contact"; id: string; title: string; prompt_text?: string; sent_text?: string; topics?: string[]; hours?: { weekday: number; start: string; end: string }[]; away_text?: string }
  | { type: "faq"; id: string; title: string; entries: FaqEntry[]; prompt_text?: string; not_found_text?: string }
  | { type: "admin_notify"; id: string; on: string; text: string; min_total?: number; max_rating?: number };
export type Spec = { name: string; welcome: string; menu: { label: string; block: string }[]; blocks: Block[]; gate?: { channel: string; text: string; join_url?: string } | null };
export type Bot = { id: number; name: string; version: number; spec: Spec | null };

export type Rec = { id: number; collection: string; data: Record<string, any>; created_at: string; files?: Record<string, { name: string }> };
export type TestRes = { name: string; passed: boolean; failures: string[]; transcript: { user: string; bot: string }[] };
export type DiffRow = { path: string; before: any; after: any };
export type Ver = { version: number; note: string; created_at: string; diff: DiffRow[]; tests_passed: number; tests_total: number };
export type ChatMsg = { role: "user" | "assistant"; content: string };
export type RunResult = { message: string; version?: number; tests?: TestRes[]; cost_usd?: number };
export type RunStatus = "running" | "needs_input" | "done" | "failed" | "declined";

export const BLOCK_KIND: Record<Block["type"], string> = {
  message: "پیام", form: "فرم", booking: "نوبت‌دهی", catalog_order: "سفارش", admin_notify: "اطلاع به مدیر", faq: "پرسش‌های متداول", contact: "پیام به مدیر", feedback: "نظرسنجی", menu: "زیرمنو", quiz: "آزمون", referral: "دعوت دوستان", anon_chat: "چت ناشناس",
};
export const FIELD_KIND: Record<Field["kind"], string> = {
  text: "متن", phone: "شماره‌ی موبایل (با بررسی قالب)", number: "عدد", choice: "انتخابی", multi: "چندانتخابی", email: "ایمیل", national_id: "کد ملی (با بررسی)", date: "تاریخ شمسی", location: "موقعیت روی نقشه یا نشانی", file: "فایل (PDF، Word یا عکس)",
};

export function blockTitle(b: Block): string {
  if (b.type === "message") return b.text.length > 36 ? b.text.slice(0, 36) + "…" : b.text;
  if (b.type === "admin_notify") return b.text?.trim() || "اطلاع به مدیر";
  return b.title;
}

export const toman = (n: number) => `${n.toLocaleString("fa-IR")} تومان`;

/** The optional settings of a block, as plain Persian lines for the structure tab (empty when none are set). */
export function blockExtras(b: Block): string[] {
  const out: string[] = [];
  const n = (x: number) => x.toLocaleString("fa-IR");
  if (b.type === "form") {
    if (b.confirm_before_submit) out.push("پیش از ثبت، پاسخ‌ها برای تأیید به مشتری نشان داده می‌شود");
    if (b.one_per_customer) out.push("هر مشتری فقط یک بار می‌تواند ثبت کند");
    if (b.max_submissions) out.push(`حداکثر ${n(b.max_submissions)} ثبت؛ پس از آن فرم بسته می‌شود`);
    if (b.closes_on) out.push(`مهلت ثبت تا ${b.closes_on.replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[+d])}`);
    if (b.review) out.push("هر درخواست را در «ثبت‌ها» بررسی می‌کنید (پذیرفته / رد / در حال بررسی) و نتیجه برای مشتری ارسال می‌شود");
    if (b.hot_score) out.push(`امتیازدهی: ثبت‌هایی با امتیاز ${n(b.hot_score)} یا بیشتر با 🔥 به شما اطلاع داده می‌شوند`);
    else if (b.fields.some((f) => f.scores?.length)) out.push("امتیازدهی به پاسخ‌ها: امتیاز هر ثبت در «ثبت‌ها» دیده می‌شود");
    if (b.fields.some((f) => f.kind === "file")) out.push("فایل‌های مشتری در چت مدیر ارسال می‌شوند و در «ثبت‌ها» قابل دریافت‌اند");
  }
  if (b.type === "booking") {
    const sv = b.schedule?.services ?? [];
    if (sv.length) out.push("خدمت‌ها: " + sv.map((s) => `${s.name} (${n(s.duration_minutes)} دقیقه${s.price ? `، ${toman(s.price)}` : ""}${s.staff?.length ? `، فقط ${s.staff.join(" و ")}` : ""})`).join("، "));
    for (const h of b.schedule?.staff_hours ?? [])
      out.push(`ساعت کاری ${h.staff}: ` + h.days.map((w) => `${WEEKDAYS[w.weekday]} ${w.start} تا ${w.end}`).join("؛ ").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[+d]));
    if (b.deposit) out.push(`بیعانه‌ی آنلاین ${toman(b.deposit)} برای قطعی شدن نوبت`);
    if ((b.repeat_weeks ?? 0) > 1) out.push(`رزرو هفتگی پشت سر هم تا ${n(b.repeat_weeks!)} هفته`);
    if (b.reminder_hours && b.reminder_confirm !== false) out.push("یادآوری با دکمه‌ی «می‌آیم / نمی‌توانم بیایم»");
    if (b.no_show_limit) out.push(`پس از ${n(b.no_show_limit)} بار «حاضر نشد»، رزرو آنلاین برای آن مشتری بسته می‌شود`);
    const priced = b.slots.filter((s) => s.price);
    if (priced.length) out.push("قیمت: " + priced.map((s) => `${s.label} ${toman(s.price!)}`).join("، "));
    if (b.closed_dates?.length) out.push("روزهای تعطیل: " + b.closed_dates.join("، ").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[+d]));
    if (b.min_notice_hours) out.push(`دست‌کم ${n(b.min_notice_hours)} ساعت پیش از شروع`);
    if (b.max_active_per_customer) out.push(`حداکثر ${n(b.max_active_per_customer)} نوبت فعال برای هر مشتری`);
    if ((b.max_party ?? 1) > 1) out.push(`رزرو گروهی تا ${n(b.max_party!)} نفر`);
  }
  if (b.type === "catalog_order") {
    if (b.ask_quantity) out.push("تعداد هر قلم پرسیده می‌شود");
    if (b.repeat_order !== false) out.push("مشتری قبلی می‌تواند سفارش قبلی‌اش را با یک دکمه تکرار کند");
    if (b.source === "table" && b.restock_alerts !== false) out.push("زیر محصول ناموجود: «موجود شد خبرم کن»");
    if (b.order_hours?.length) out.push("ساعت سفارش‌گیری: " + b.order_hours.map((w) => `${WEEKDAYS[w.weekday]} ${w.start} تا ${w.end}`).join("؛ ").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[+d]));
  }
  const hours = (d: { weekday: number; start: string; end: string }[]) =>
    d.map((w) => `${WEEKDAYS[w.weekday]} ${w.start} تا ${w.end}`).join("؛ ").replace(/\d/g, (x) => "۰۱۲۳۴۵۶۷۸۹"[+x]);
  if (b.type === "message") {
    if (b.join?.length) out.push("قفل عضویت: محتوا فقط پس از عضویت در " + b.join.map((c) => c.channel).join("، ") + " ارسال می‌شود");
    if (b.links?.length) out.push("دکمه‌ی لینک: " + b.links.map((l) => l.label).join("، "));
    if (b.hours?.length) out.push(`«الان باز / بسته» از روی ساعت کاری: ${hours(b.hours)}`);
    if (b.contact) out.push(`کارت تماس: ${b.contact.name} (${b.contact.phone})`);
    if (b.media === "album") out.push(`آلبوم ${n(b.album_size ?? 0)} عکس؛ عکس‌ها را در «فایل‌ها» بارگذاری کنید`);
  }
  if (b.type === "contact") {
    if (b.topics?.length) out.push("موضوع پیام: " + b.topics.join("، "));
    if (b.hours?.length) out.push(`بیرون از ساعت پاسخ‌گویی (${hours(b.hours)}) پاسخ خودکار «${b.away_text ?? ""}» فرستاده می‌شود`);
  }
  if (b.type === "referral") {
    if (b.count_after === "order") out.push("هر دعوت پس از اولین سفارش یا نوبت دوست حساب می‌شود");
    if (b.reward_code) out.push(`در هدف، کد تخفیف ${b.reward_code} خودکار فرستاده می‌شود`);
    for (const t of b.tiers ?? []) out.push(`جایزه‌ی ${n(t.goal)} دعوت: ${t.reward_text}${t.reward_code ? ` (کد ${t.reward_code})` : ""}`);
  }
  if (b.type === "anon_chat") {
    if (b.topics?.length) out.push("اتاق‌های گفت‌وگو: " + b.topics.join("، "));
    if (b.max_minutes) out.push(`هر گفت‌وگو حداکثر ${n(b.max_minutes)} دقیقه`);
  }
  if (b.type === "admin_notify") {
    if (b.min_total) out.push(`فقط سفارش‌های ${toman(b.min_total)} و بیشتر`);
    if (b.max_rating) out.push(`فقط امتیازهای ${n(b.max_rating)} و کمتر`);
  }
  if (b.type === "feedback") {
    if (b.after) out.push(`${n(b.after_hours ?? 2)} ساعت پس از هر نوبت یا تحویل سفارش، نظر مشتری خودکار پرسیده می‌شود (با ستاره‌ها در همان پیام)`);
    if (b.aspects?.length) out.push("امتیاز جداگانه به: " + b.aspects.join("، "));
    if (b.follow_up_below) out.push(`امتیاز کمتر از ${n(b.follow_up_below)}: شماره‌ی مشتری برای تماس مدیر پرسیده می‌شود`);
  }
  if (b.type === "quiz") {
    if (b.pick) out.push(`هر بار ${n(b.pick)} سؤال تصادفی از ${n(b.questions.length)} سؤال`);
    else if (b.shuffle) out.push("ترتیب سؤال‌ها تصادفی است");
    if (b.pass_percent) out.push(`نمره‌ی قبولی ${n(b.pass_percent)}٪`);
    if (b.one_attempt) out.push("هر نفر فقط یک بار");
    if (b.pass_code) out.push(`قبول‌شدگان کد تخفیف ${b.pass_code} می‌گیرند`);
    if (b.personality?.length) out.push("آزمون شخصیت؛ نتیجه‌ها: " + b.personality.map((o) => o.title).join("، "));
    if (b.questions.some((q) => q.media === "image")) out.push("بعضی سؤال‌ها عکس دارند؛ عکس‌ها را در «فایل‌ها» بارگذاری کنید");
  }
  return out;
}

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
  if (sc.staff.length) lines.push(`تقویم جداگانه برای: ${sc.staff.join("، ")}`);
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
  [/ذخیره شد/, 1], [/همه(‌ی)? تست‌ها موفق/, 0.92], [/رفع خطا/, 0.78], [/ناموفق/, 0.7], [/اجرای .* تست/, 0.62],
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
  slots: "زمان‌ها", items: "آیتم‌ها", on: "زمان ارسال پیام به مدیر", kind: "نوع", required: "اجباری", choices: "گزینه‌ها", options: "گزینه‌ها",
  block: "مقصد", blocks: "بخش‌ها", type: "نوع", delivery_fee: "هزینه‌ی ارسال", delivery_zones: "مناطق ارسال", free_delivery_over: "ارسال رایگان از مبلغ", fee: "هزینه‌ی ارسال",
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
