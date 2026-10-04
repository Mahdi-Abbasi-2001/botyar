"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fa } from "@/components/ui";

type Msg = { id: number; from: "customer" | "owner"; text: string; at: string };
type Thread = { thread: string; collection: string; who: string; unanswered: boolean; messages: Msg[] };

const card = "rounded-2xl border border-line-2 bg-panel p-4";

export function InboxTab({ botId }: { botId: string }) {
  const [sandbox, setSandbox] = useState(false);
  const [threads, setThreads] = useState<Thread[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setThreads(await api<Thread[]>(`/bots/${botId}/inbox?sandbox=${sandbox}`));
    } catch (e: any) {
      setError(e.message);
    }
  }, [botId, sandbox]);
  useEffect(() => {
    load();
  }, [load]);

  async function reply(t: Thread) {
    const key = `${t.collection}/${t.thread}`;
    const text = (drafts[key] || "").trim();
    if (!text) return;
    setBusy(key);
    setError("");
    setNote("");
    try {
      const r = await api<{ delivered: number; wanted: number; sandbox: boolean }>(`/bots/${botId}/inbox/${t.collection}/${t.thread}/reply?sandbox=${sandbox}`, { body: { text } });
      setDrafts({ ...drafts, [key]: "" });
      setNote(r.sandbox ? "پاسخ ذخیره شد (گفتگوی آزمایشی به مشتری واقعی نمی‌رسد)." : r.delivered < r.wanted ? "پاسخ ذخیره شد ولی به چت مشتری نرسید (شاید ربات را مسدود کرده)." : "پاسخ برای مشتری ارسال شد ✓");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="m-0 text-base">پیام‌های مشتری‌ها</h3>
        <label className="flex items-center gap-2 text-sm text-mute">
          <input type="checkbox" checked={sandbox} onChange={(e) => setSandbox(e.target.checked)} /> فقط آزمایشی
        </label>
      </div>
      {error && <p role="alert" className="m-0 text-sm text-red-400">{error}</p>}
      {note && <p className="m-0 text-sm text-mint">{note}</p>}
      {threads && threads.length === 0 && <p className={`${card} m-0 text-sm text-mute`}>هنوز پیامی نیامده است.</p>}
      {threads?.map((t) => {
        const key = `${t.collection}/${t.thread}`;
        return (
          <section key={key} className={`${card} flex flex-col gap-2`}>
            <header className="flex items-center justify-between">
              <strong>{t.who}</strong>
              {t.unanswered && <span className="rounded-full bg-saffron px-2 py-0.5 text-xs font-bold text-ink">بدون پاسخ</span>}
            </header>
            <div className="flex flex-col gap-1.5">
              {t.messages.map((m) => (
                <p key={m.id} className={`m-0 max-w-[85%] whitespace-pre-line rounded-xl px-3 py-2 text-sm leading-7 ${m.from === "owner" ? "self-end bg-raised" : "self-start border border-line-2"}`}>
                  {m.text}
                  <span className="mt-1 block text-xs text-mute">{m.from === "owner" ? "شما" : t.who} · {fa(new Date(m.at).toLocaleString("fa-IR"))}</span>
                </p>
              ))}
            </div>
            <div className="flex gap-2">
              <input aria-label="پاسخ" className="min-h-11 flex-1 rounded-xl border border-line-2 bg-raised px-3" maxLength={1000} value={drafts[key] || ""} placeholder="پاسخ شما…"
                onChange={(e) => setDrafts({ ...drafts, [key]: e.target.value })} onKeyDown={(e) => e.key === "Enter" && reply(t)} />
              <button className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50" disabled={busy === key || !(drafts[key] || "").trim()} onClick={() => reply(t)}>ارسال</button>
            </div>
          </section>
        );
      })}
    </div>
  );
}
