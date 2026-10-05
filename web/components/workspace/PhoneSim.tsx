"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Action, type Button } from "@/lib/api";
import { Icon, fa } from "../ui";

type Msg = { from: "bot" | "me" | "admin" | "note"; text: string; buttons?: Button[] };
const rid = () => Math.random().toString(36).slice(2, 10);

const STATUS: Record<string, string> = { confirmed: "ثبت شد", waitlisted: "در لیست انتظار", new: "سفارش جدید", cancelled: "لغو شد" };
const HIDDEN = new Set(["id", "slot", "status", "items", "date", "time", "staff"]);

/** The engine's notification is "title\n[status] key: value\n…"; show it with the owner's own field labels, no ids. */
function prettyAdmin(text: string, labels: Record<string, string>): string {
  const [title, ...rest] = text.split("\n");
  let status = "";
  const rows: string[] = [];
  for (let line of rest) {
    const tag = line.match(/^\[(\w+)\]\s*(.*)$/);
    if (tag) { status = STATUS[tag[1]] ?? ""; line = tag[2]; }
    const kv = line.match(/^([a-z][a-z0-9_]*):\s*(.*)$/);
    if (!kv) { if (line.trim()) rows.push(line); continue; }
    const [, k, v] = kv;
    if (HIDDEN.has(k)) continue;
    if (k === "total") rows.push(`مبلغ: ${(+v).toLocaleString("fa-IR")} تومان`);
    else rows.push(`${labels[k] ?? k}: ${v}`);
  }
  return [status ? `${title} · ${status}` : title, ...rows].join("\n");
}

/** Phone-shaped chat with the bot's latest version (sandbox). */
export function PhoneSim({ botId, version, labels, onActivity, className = "" }: { botId: string; version: number; labels: Record<string, string>; onActivity: () => void; className?: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [session, setSession] = useState(rid);
  const scroller = useRef<HTMLDivElement>(null);
  const started = useRef("");

  const send = useCallback(async (t: string, shown?: string | null) => {
    setBusy(true);
    setError("");
    if (shown !== null) setMsgs((m) => [...m.map((x) => ({ ...x, buttons: undefined })), { from: "me", text: shown ?? t }]);
    try {
      const r = await api<{ actions: Action[] }>(`/bots/${botId}/simulate`, { body: { session_id: session, text: t } });
      setMsgs((m) => {
        const mapped = r.actions.map((a): Msg => {
          if (a.type === "send") return { from: "bot", text: a.text, buttons: a.buttons };
          if (a.type === "media") {
            const what = a.kind === "image" ? "عکس" : "فایل";
            return { from: "bot", text: a.uploaded ? `📎 ${what}: ${a.filename}` : `📎 ${what} (هنوز در تب «فایل‌ها» بارگذاری نشده)` };
          }
          if (a.type === "location") return { from: "bot", text: `📍 موقعیت روی نقشه (${a.latitude}, ${a.longitude})` };
          if (a.type === "notify_customer") return { from: "note", text: "📨 پیام به مشتریِ دیگر در بله: " + a.text };
          return { from: "admin", text: a.text };
        });
        const first = r.actions[0];
        // like Bale: navigation (next page, category, back) edits the clicked message instead of adding one
        if (first?.type === "send" && first.edit && m.length && m[m.length - 1].from === "me") {
          const base = m.slice(0, -1); // drop the echoed click: a real button press shows no user bubble
          let i = base.length - 1;
          while (i >= 0 && base[i].from !== "bot") i--;
          if (i >= 0) {
            base[i] = mapped[0];
            return [...base, ...mapped.slice(1)];
          }
        }
        return [...m, ...mapped];
      });
      onActivity();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [botId, session, onActivity]);

  useEffect(() => {
    if (version && started.current !== session + version) {
      started.current = session + version;
      setMsgs([]);
      send("/start", null);
    }
  }, [version, session, send]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  async function restart() {
    await api(`/bots/${botId}/simulate/reset`, { method: "POST", body: {} }).catch(() => {});
    onActivity();
    setSession(rid());
  }

  return (
    <section aria-label="پیش‌نمایش ربات" className={`flex h-[640px] w-[320px] max-w-full flex-col gap-2.5 rounded-[40px] border-8 border-line bg-panel px-3 py-4 ${className}`}>
      <div className="flex items-center justify-between border-b border-line px-1.5 pb-2.5 text-[13px]">
        <span className="font-bold">امتحانش کن <span className="font-normal text-mint">· نسخه {version.toLocaleString("fa-IR")}</span></span>
        <button onClick={restart} className="flex min-h-8 items-center gap-1 rounded-lg border border-line-2 px-2.5 text-xs text-mute hover:text-fg">
          <Icon name="refresh" size={13} /> شروع دوباره
        </button>
      </div>
      <div ref={scroller} className="flex flex-1 flex-col gap-2.5 overflow-y-auto px-0.5">
        {msgs.map((m, i) => (
          <div key={i} className={`anim-rise flex max-w-[88%] flex-col gap-1.5 ${m.from === "me" ? "self-end" : "self-start"} ${m.from === "admin" || m.from === "note" ? "max-w-full self-stretch" : ""}`}>
            <div className={`whitespace-pre-line px-3 py-2 text-[13px] leading-7 ${
              m.from === "me" ? "rounded-[14px_14px_4px_14px] bg-saffron text-ink"
              : m.from === "admin" ? "rounded-xl border border-amber-line bg-amber-bg text-amber-fg"
              : m.from === "note" ? "rounded-xl border border-dashed border-line-3 text-xs text-dim"
              : "rounded-[14px_14px_14px_4px] bg-raised"}`}>
              {m.from === "admin" && <div className="mb-0.5 flex items-center gap-1.5 text-xs font-bold"><Icon name="bell" size={14} /> اعلان به مدیر</div>}
              {m.from === "admin" ? prettyAdmin(m.text, labels) : m.from === "bot" ? fa(m.text) : m.text}
            </div>
            {m.buttons && m.buttons.length > 0 && (
              <div className="flex flex-col gap-1.5">
                {m.buttons.map((b) => {
                  const full = /\(تکمیل\)$/.test(b.text);
                  return (
                    <button key={b.data} disabled={busy} onClick={() => send(b.data, b.text)}
                      className={`min-h-10 rounded-[10px] border px-2.5 py-1.5 text-[13px] disabled:opacity-50 ${full ? "border-line-2 text-dim" : "border-line-3 hover:border-saffron hover:text-saffron"}`}>
                      {fa(b.text)}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ))}
        {busy && <span className="self-start px-2 text-dim">…</span>}
      </div>
      {error && <p className="px-1 text-xs text-bad-fg">{error}</p>}
      <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) { send(text.trim()); setText(""); } }}
        className="flex items-center gap-2 rounded-full bg-ink py-1 pl-1 pr-3">
        <label htmlFor="sim-in" className="sr-only">پیام به ربات</label>
        <input id="sim-in" value={text} onChange={(e) => setText(e.target.value)} placeholder="پیام…" className="min-w-0 flex-1 bg-transparent py-2 text-[13px] outline-none placeholder:text-dim" />
        <button disabled={busy} aria-label="ارسال" className="flex h-10 w-10 items-center justify-center rounded-full bg-saffron text-ink disabled:opacity-50">
          <Icon name="send" size={16} strokeWidth={2.4} />
        </button>
      </form>
    </section>
  );
}
