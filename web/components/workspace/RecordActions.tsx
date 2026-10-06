"use client";
import { useState } from "react";
import { api, downloadFile } from "@/lib/api";
import { fa } from "@/components/ui";

type Rec = { id: number; collection: string; data: Record<string, any>; files?: Record<string, { name: string }> };
type Reply = { status: string; customer_messages: { wanted: number; sent: number; sandbox: boolean }; promoted: { name?: string } | null; refund_needed?: boolean };

/** Orders move forward one step at a time; the customer is told at "preparing" and "ready". */
const NEXT: Record<string, [string, string][]> = {
  new: [["preparing", "شروع آماده‌سازی"], ["ready", "آماده شد"], ["done", "تحویل شد"]],
  preparing: [["ready", "آماده شد"], ["done", "تحویل شد"]],
  ready: [["done", "تحویل شد"]],
};
const btn = "min-h-8 rounded-lg border border-line-3 px-2.5 text-xs hover:border-saffron hover:text-saffron disabled:opacity-50";

/** Owner actions for one booking/order: move an order along, or cancel (the reason is sent to the customer). */
export function RecordActions({ botId, rec, onChanged }: { botId: string | number; rec: Rec; onChanged: () => void }) {
  const isOrder = Array.isArray(rec.data.items);
  const isFaq = "question" in rec.data;
  const isReview = ["received", "reviewing"].includes(rec.data.status);  // an application waiting for the owner's decision
  const files = Object.entries(rec.files ?? {});  // files the customer sent for a form question
  const [decision, setDecision] = useState<string | null>(null);
  const [answering, setAnswering] = useState(false);
  const [answer, setAnswer] = useState("");
  const [question, setQuestion] = useState<string>(rec.data.question ?? "");
  const [teach, setTeach] = useState(true);
  const st: string = rec.data.status;
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const reported = st === "reported" && rec.data.reported_id != null;
  const transfer = isOrder && (st === "transfer_sent" || st === "awaiting_transfer");  // card-to-card: the owner checks the money
  const open = isFaq ? st === "unanswered" : isOrder ? st in NEXT || transfer : isReview || st === "confirmed" || st === "waitlisted";
  // a booking whose time has come can be marked «حاضر نشد» (Tehran time; undated events any time)
  const started = !rec.data.date || new Date(`${rec.data.date}T${rec.data.time || "00:00"}:00+03:30`).getTime() <= Date.now();
  if (reported) {
    return (
      <div className="flex flex-col gap-1.5">
        <button className={btn + " hover:!border-bad hover:!text-bad-soft"} disabled={busy}
          onClick={async () => { setBusy(true); try { await api(`/bots/${botId}/customers/${rec.data.reported_id}/ban`, { method: "POST", body: {} }); setNote("مشتری مسدود شد و دیگر نمی‌تواند از ربات استفاده کند."); } catch (e: any) { setError(e.message); } finally { setBusy(false); } }}>
          مسدود کردن مشتری گزارش‌شده ({rec.data.reported_name})
        </button>
        {note && <span className="text-xs text-mint-fg">{note}</span>}
        {error && <span className="text-xs text-bad-soft">{error}</span>}
      </div>
    );
  }
  const fileLinks = files.length > 0 && (
    <div className="flex flex-wrap gap-1.5">
      {files.map(([key, f]) => (
        <button key={key} className={btn} onClick={() => downloadFile(`/bots/${botId}/records/${rec.id}/files/${key}`, f.name).catch((e) => setError(e.message))}>📎 {f.name}</button>
      ))}
    </div>
  );
  if (!open && !note) return fileLinks ? <div className="flex flex-col gap-1.5">{fileLinks}{error && <span className="text-xs text-bad-soft">{error}</span>}</div> : null;

  async function reply() {
    setBusy(true);
    setError("");
    try {
      const r = await api<{ customer_messages: Reply["customer_messages"]; added_version: number | null; not_added: string }>(
        `/bots/${botId}/records/${rec.id}/answer`, { body: { answer, add_to_faq: teach, question } });
      const m = r.customer_messages;
      const parts = [m.sandbox ? "در شبیه‌ساز پیامی به مشتری ارسال نمی‌شود" : m.sent ? "پاسخ برای مشتری ارسال شد ✓" : m.wanted ? "پاسخ به مشتری نرسید" : "این سؤال مشتری مشخصی ندارد"];
      if (r.added_version) parts.push(`به پرسش‌های متداول اضافه شد (نسخه‌ی ${fa(r.added_version)})`);
      else if (r.not_added) parts.push(`⚠️ به پرسش‌های متداول اضافه نشد: ${r.not_added}`);
      setNote(parts.join(" · "));
      setAnswering(false);
      onChanged();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function go(body: Record<string, unknown>) {
    setBusy(true);
    setError("");
    try {
      const r = await api<Reply>(`/bots/${botId}/records/${rec.id}`, { method: "PATCH", body });
      const m = r.customer_messages;
      const parts: string[] = [];
      if (r.refund_needed) parts.push("⚠️ هزینه‌ی این سفارش پرداخت شده بود؛ بازگرداندن وجه را خودتان از کیف پول انجام دهید");
      if (r.promoted) parts.push(`${r.promoted.name ?? "نفر بعدی"} از لیست انتظار تأیید شد`);
      if (isFaq) { /* closing a question messages nobody */ }
      else if (m.sandbox) parts.push("در شبیه‌ساز پیامی به مشتری ارسال نمی‌شود");
      else if (m.wanted && m.sent === m.wanted) parts.push(`برای ${fa(m.sent)} مشتری پیام ارسال شد ✓`);
      else if (m.wanted) parts.push("پیام به مشتری نرسید؛ ممکن است ربات را مسدود کرده باشد");
      else parts.push("برای این ثبت، امکان ارسال پیام به مشتری وجود ندارد");
      setNote(parts.join(" · "));
      setAsking(false);
      onChanged();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      {fileLinks}
      {open && isFaq && !answering && (
        <div className="flex flex-wrap gap-1.5">
          <button className={btn + " !border-saffron !text-saffron"} disabled={busy} onClick={() => setAnswering(true)}>پاسخ دادن</button>
          <button className={btn} disabled={busy} onClick={() => go({ action: "status", status: "handled" })}>رسیدگی شد</button>
        </div>
      )}
      {answering && (
        <div className="flex min-w-64 flex-col gap-1.5 rounded-lg border border-line-3 p-2">
          <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={1500} rows={3} placeholder="پاسخ شما (برای مشتری ارسال می‌شود)"
            className="rounded-md border border-line-2 bg-ink p-2 text-xs outline-none focus:border-saffron" />
          <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={teach} onChange={(e) => setTeach(e.target.checked)} />به پرسش‌های متداول هم اضافه شود</label>
          {teach && (
            <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={200} placeholder="سؤال، همان‌طور که در فهرست دیده می‌شود"
              className="min-h-8 rounded-md border border-line-2 bg-ink px-2 text-xs outline-none focus:border-saffron" />
          )}
          <div className="flex gap-1.5">
            <button className={btn + " !border-saffron !text-saffron"} disabled={busy || !answer.trim() || (teach && question.trim().length < 3)} onClick={reply}>{busy ? "…" : "ارسال پاسخ"}</button>
            <button className={btn} disabled={busy} onClick={() => setAnswering(false)}>انصراف</button>
          </div>
        </div>
      )}
      {open && isReview && !decision && (
        <div className="flex flex-wrap gap-1.5">
          <button className={btn + " !border-mint !text-mint-fg"} disabled={busy} onClick={() => setDecision("accepted")}>پذیرفتن</button>
          <button className={btn + " hover:!border-bad hover:!text-bad-soft"} disabled={busy} onClick={() => setDecision("rejected")}>رد کردن</button>
          {st !== "reviewing" && <button className={btn} disabled={busy} onClick={() => setDecision("reviewing")}>در حال بررسی</button>}
        </div>
      )}
      {decision && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-line-3 p-2">
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} placeholder="پیام شما به متقاضی (اختیاری؛ مثلاً زمان مصاحبه)"
            className="min-h-8 rounded-md border border-line-2 bg-ink px-2 text-xs outline-none focus:border-saffron" />
          <div className="flex gap-1.5">
            <button className={btn} disabled={busy} onClick={async () => { await go({ action: "status", status: decision, reason }); setDecision(null); }}>
              {busy ? "…" : { accepted: "ثبت «پذیرفته شد»", rejected: "ثبت «رد شد»", reviewing: "ثبت «در حال بررسی»" }[decision]}
            </button>
            <button className={btn} disabled={busy} onClick={() => setDecision(null)}>انصراف</button>
          </div>
        </div>
      )}
      {open && !isFaq && !isReview && !asking && (
        <div className="flex flex-wrap gap-1.5">
          {transfer && <button className={btn + " !border-mint !text-mint-fg"} disabled={busy} onClick={() => go({ action: "confirm_payment" })}>واریز را دیدم، تأیید</button>}
          {isOrder && (NEXT[st] ?? []).map(([s, label]) => <button key={s} className={btn} disabled={busy} onClick={() => go({ action: "status", status: s })}>{label}</button>)}
          {!isOrder && st === "confirmed" && started && <button className={btn} disabled={busy} onClick={() => go({ action: "status", status: "no_show" })}>حاضر نشد</button>}
          <button className={btn + " hover:!border-bad hover:!text-bad-soft"} disabled={busy} onClick={() => setAsking(true)}>لغو</button>
        </div>
      )}
      {asking && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-line-3 p-2">
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} placeholder="دلیل لغو (اختیاری، برای مشتری ارسال می‌شود)"
            className="min-h-8 rounded-md border border-line-2 bg-ink px-2 text-xs outline-none focus:border-saffron" />
          <div className="flex gap-1.5">
            <button className={btn + " !border-bad !text-bad-soft"} disabled={busy} onClick={() => go({ action: "cancel", reason })}>{busy ? "…" : isOrder ? "لغو سفارش" : "لغو ثبت‌نام"}</button>
            <button className={btn} disabled={busy} onClick={() => setAsking(false)}>انصراف</button>
          </div>
        </div>
      )}
      {note && <span className="text-xs text-mint-fg">{note}</span>}
      {error && <span className="text-xs text-bad-soft">{error}</span>}
    </div>
  );
}
