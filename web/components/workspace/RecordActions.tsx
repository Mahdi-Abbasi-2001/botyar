"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { fa } from "@/components/ui";

type Rec = { id: number; collection: string; data: Record<string, any> };
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
  const st: string = rec.data.status;
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const open = isFaq ? st === "unanswered" : isOrder ? st in NEXT : st === "confirmed" || st === "waitlisted";
  if (!open && !note) return null;

  async function go(body: Record<string, unknown>) {
    setBusy(true);
    setError("");
    try {
      const r = await api<Reply>(`/bots/${botId}/records/${rec.id}`, { method: "PATCH", body });
      const m = r.customer_messages;
      const parts: string[] = [];
      if (r.refund_needed) parts.push("⚠️ این سفارش پرداخت شده بود؛ بازگشت وجه را خودتان از کیف پول انجام دهید");
      if (r.promoted) parts.push(`${r.promoted.name ?? "نفر بعدی"} از لیست انتظار تأیید شد`);
      if (isFaq) { /* closing a question messages nobody */ }
      else if (m.sandbox) parts.push("در شبیه‌ساز پیامی به مشتری ارسال نمی‌شود");
      else if (m.wanted && m.sent === m.wanted) parts.push(`به ${fa(m.sent)} مشتری پیام داده شد ✓`);
      else if (m.wanted) parts.push("پیام به مشتری ارسال نشد (شاید ربات را مسدود کرده است)");
      else parts.push("این ثبت مشتری قابل پیام‌دادن ندارد");
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
      {open && isFaq && (
        <div className="flex flex-wrap gap-1.5">
          <button className={btn} disabled={busy} onClick={() => go({ action: "status", status: "handled" })}>رسیدگی شد</button>
        </div>
      )}
      {open && !isFaq && !asking && (
        <div className="flex flex-wrap gap-1.5">
          {isOrder && NEXT[st].map(([s, label]) => <button key={s} className={btn} disabled={busy} onClick={() => go({ action: "status", status: s })}>{label}</button>)}
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
