"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fa } from "@/components/ui";

type Rule = { delete_links: boolean; delete_forwards: boolean; banned_words: string[]; max_warnings: number; welcome_text: string; deleted: number; banned: number };
type Chat = { id: number; messenger: "bale" | "tg"; kind: "channel" | "group"; title: string; rule: Rule | null };
type Fwd = { id: number; source: number; dest: number; active: boolean; forwarded: number; last_error: string };
type Gate = { configured: boolean; channel?: string; messengers: { messenger: string; ok?: boolean; status?: string; error?: string }[] };

const card = "rounded-2xl border border-line-2 bg-panel p-4";
const input = "min-h-11 rounded-xl border border-line-2 bg-raised px-3";
const MSG = { bale: "بله", tg: "تلگرام" } as const;

function GroupRules({ botId, chat, onSaved }: { botId: string; chat: Chat; onSaved: () => void }) {
  const r = chat.rule!;
  const [links, setLinks] = useState(r.delete_links);
  const [fwd, setFwd] = useState(r.delete_forwards);
  const [words, setWords] = useState(r.banned_words.join("، "));
  const [warns, setWarns] = useState(r.max_warnings);
  const [welcome, setWelcome] = useState(r.welcome_text);
  const [msg, setMsg] = useState("");
  async function save() {
    setMsg("");
    try {
      await api(`/bots/${botId}/chats/${chat.id}/moderation`, { method: "PUT", body: { delete_links: links, delete_forwards: fwd, banned_words: words.split(/[،,\n]/).map((w) => w.trim()).filter(Boolean), max_warnings: warns, welcome_text: welcome } });
      setMsg("ذخیره شد ✓");
      onSaved();
    } catch (e: any) {
      setMsg(e.message);
    }
  }
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-xl border border-line-2 p-3 text-sm">
      <strong>مدیریت پیام‌های گروه</strong>
      <label className="flex items-center gap-2"><input type="checkbox" checked={links} onChange={(e) => setLinks(e.target.checked)} /> پیام‌های دارای لینک یا @شناسه حذف شوند</label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={fwd} onChange={(e) => setFwd(e.target.checked)} /> پیام‌های بازارسال‌شده (فوروارد) حذف شوند</label>
      <label className="flex flex-col gap-1">کلمه‌های ممنوع (با ویرگول جدا کنید)<input className={input} value={words} onChange={(e) => setWords(e.target.value)} /></label>
      <label className="flex items-center gap-2">پس از <input type="number" min={0} max={20} className={input + " w-20"} value={warns} onChange={(e) => setWarns(Number(e.target.value))} /> اخطار، کاربر از گروه حذف شود (عدد ۰ یعنی فقط پیام حذف شود)</label>
      <label className="flex flex-col gap-1">پیام خوش‌آمد (عبارت {"{name}"} با نام عضو تازه جایگزین می‌شود)<input className={input} maxLength={500} value={welcome} onChange={(e) => setWelcome(e.target.value)} /></label>
      <div className="flex items-center gap-3"><button onClick={save} className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink">ذخیره</button><span className="text-mute">{msg}</span></div>
      <span className="text-xs text-mute">تا این لحظه {fa(r.deleted)} پیام و {fa(r.banned)} عضو حذف شده‌اند. پیام‌های مدیران گروه بررسی نمی‌شوند. فرمان‌های مدیر در پاسخ به پیام یک عضو: /ban ، /unban ، /warns</span>
    </div>
  );
}

export function ChannelsTab({ botId }: { botId: string }) {
  const [data, setData] = useState<{ chats: Chat[]; forwards: Fwd[] } | null>(null);
  const [gate, setGate] = useState<Gate | null>(null);
  const [code, setCode] = useState<{ command: string; expires_minutes: number } | null>(null);
  const [username, setUsername] = useState("");
  const [src, setSrc] = useState("");
  const [dst, setDst] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await api(`/bots/${botId}/chats`));
      setGate(await api(`/bots/${botId}/gate`));
      const p = await api<{ shared_bot_username?: string; bot_username?: string; mode?: string }>(`/bots/${botId}/publication`);
      setUsername((p.mode === "own" ? p.bot_username : p.shared_bot_username) || "");
    } catch (e: any) {
      setError(e.message);
    }
  }, [botId]);
  useEffect(() => {
    load();
  }, [load]);

  async function newCode() {
    setError("");
    try {
      setCode(await api(`/bots/${botId}/link-token`, { method: "POST", body: {} }));
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function unlink(id: number) {
    try {
      await api(`/bots/${botId}/chats/${id}`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function addFwd() {
    setError("");
    try {
      await api(`/bots/${botId}/forwards`, { body: { source: Number(src), dest: Number(dst) } });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function delFwd(id: number) {
    try {
      await api(`/bots/${botId}/forwards/${id}`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  const title = (id: number) => data?.chats.find((c) => c.id === id)?.title ?? "—";
  const channels = data?.chats.filter((c) => c.kind === "channel") ?? [];

  return (
    <div className="flex flex-col gap-3">
      <h3 className="m-0 text-base">کانال و گروه</h3>
      {error && <p role="alert" className="m-0 text-sm text-red-400">{error}</p>}

      {gate?.configured && (
        <section className={`${card} flex flex-col gap-1 text-sm`}>
          <strong>عضویت اجباری در کانال {gate.channel}</strong>
          {gate.messengers.length === 0 && <span className="text-mute">ربات هنوز منتشر نشده است.</span>}
          {gate.messengers.map((m) => (
            <span key={m.messenger} className={m.ok ? "text-mint" : "text-amber-fg"}>
              {m.ok ? "✓" : "⚠"} {m.messenger === "tg" ? "تلگرام" : "بله"}: {m.ok ? "ربات مدیر کانال است و بررسی عضویت کار می‌کند." : `ربات را مدیر کانال کنید و نام کانال را بررسی کنید (${m.error || m.status || "پاسخی دریافت نشد"}). تا آن زمان، مشتریان بدون بررسی عضویت وارد می‌شوند.`}
            </span>
          ))}
          <button onClick={load} className="w-fit text-xs text-saffron underline">بررسی دوباره</button>
        </section>
      )}

      <section className={`${card} flex flex-col gap-2 text-sm leading-7`}>
        <strong>اتصال کانال یا گروه</strong>
        <ol className="m-0 list-decimal space-y-1 pr-5">
          <li>ربات {username ? <b dir="ltr">@{username}</b> : "منتشرشده‌ی خود"} را به کانال یا گروه اضافه کنید و آن را <b>مدیر (ادمین)</b> کنید. برای حذف پیام و اخراج اعضا، دسترسی «حذف پیام» و «مسدود کردن» را هم بدهید.</li>
          <li>در همین صفحه «کد اتصال» بگیرید و فرمان آن را در همان کانال یا گروه بفرستید. کد یک‌بارمصرف است و ۱۵ دقیقه اعتبار دارد؛ ربات پیام حاوی کد را بلافاصله پاک می‌کند.</li>
        </ol>
        <button onClick={newCode} className="min-h-11 w-fit rounded-xl bg-saffron px-5 font-bold text-ink">دریافت کد اتصال</button>
        {code && <p className="m-0">این فرمان را بفرستید: <span dir="ltr" className="mr-2 inline-block rounded-lg bg-ink px-3 py-1 font-mono text-fg">{code.command}</span> (اعتبار: {fa(code.expires_minutes)} دقیقه)</p>}
        <p className="m-0 text-xs text-mute">محدودیت‌ها: در بله امکان «بی‌صدا کردن» عضو وجود ندارد (فقط حذف پیام، اخطار و حذف عضو)، فقط پیام‌های کمتر از ۴۸ ساعت قابل حذف‌اند، و دریافت پیام‌های کانال و گروه در بله هنوز باید روی کانال واقعی شما امتحان شود. همه‌ی این امکانات در تلگرام هم کار می‌کنند.</p>
      </section>

      {data?.chats.map((c) => (
        <section key={c.id} className={card}>
          <div className="flex items-center justify-between gap-2">
            <span><strong>{c.title}</strong> <span className="text-xs text-mute">· {MSG[c.messenger]} · {c.kind === "channel" ? "کانال" : "گروه"}</span></span>
            <button onClick={() => unlink(c.id)} className="text-xs text-mute underline hover:text-bad">قطع اتصال</button>
          </div>
          {c.rule && <GroupRules botId={botId} chat={c} onSaved={load} />}
        </section>
      ))}
      {data && data.chats.length === 0 && <p className={`${card} m-0 text-sm text-mute`}>هنوز کانال یا گروهی متصل نشده است.</p>}

      {channels.length > 0 && (
        <section className={`${card} flex flex-col gap-2 text-sm`}>
          <strong>بازنشر خودکار پست‌ها</strong>
          <span className="text-xs text-mute">پست‌های تازه‌ی یک کانال به‌طور خودکار در کانال یا گروه دیگری منتشر می‌شوند (میان بله و تلگرام فقط متن). ربات باید مدیر هر دو باشد.</span>
          <div className="flex flex-wrap items-center gap-2">
            <select aria-label="مبدأ" className={input} value={src} onChange={(e) => setSrc(e.target.value)}><option value="">کانال مبدأ…</option>{channels.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</select>
            <span>←</span>
            <select aria-label="مقصد" className={input} value={dst} onChange={(e) => setDst(e.target.value)}><option value="">مقصد…</option>{data?.chats.filter((c) => String(c.id) !== src).map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</select>
            <button disabled={!src || !dst} onClick={addFwd} className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50">افزودن</button>
          </div>
          {data?.forwards.map((f) => (
            <div key={f.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line-2 p-3">
              <span>{title(f.source)} ← {title(f.dest)} · {fa(f.forwarded)} پست بازنشر شد{f.last_error ? ` · ⚠ ${f.last_error}` : ""}</span>
              <button onClick={() => delFwd(f.id)} className="text-xs text-mute underline hover:text-bad">حذف</button>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
