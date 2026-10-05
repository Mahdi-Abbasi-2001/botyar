"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fa } from "@/components/ui";

type Item = { id: number; text: string; audience: number; sent: number; failed: number; done: boolean; created_at: string };
type Info = { published: boolean; audience: number; per_day: number; items: Item[] };

const card = "rounded-2xl border border-line-2 bg-panel p-4";

type Sched = { id: number; text: string; mode: "once" | "daily"; time: string; active: boolean; next_run: string; last_run: string | null; last_status: string };

function Scheduled({ botId, enabled }: { botId: string; enabled: boolean }) {
  const [items, setItems] = useState<Sched[]>([]);
  const [max, setMax] = useState(5);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"once" | "daily">("daily");
  const [at, setAt] = useState("");
  const [time, setTime] = useState("09:00");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api<{ max: number; items: Sched[] }>(`/bots/${botId}/scheduled`);
      setItems(r.items);
      setMax(r.max);
    } catch (e: any) {
      setError(e.message);
    }
  }, [botId]);
  useEffect(() => {
    load();
  }, [load]);

  async function add() {
    setBusy(true);
    setError("");
    try {
      await api(`/bots/${botId}/scheduled`, { body: mode === "once" ? { text, mode, at } : { text, mode, time } });
      setText("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel(id: number) {
    try {
      await api(`/bots/${botId}/scheduled/${id}`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  const when = (iso: string) => fa(new Date(iso).toLocaleString("fa-IR", { timeZone: "Asia/Tehran" }));

  return (
    <section className={`${card} flex flex-col gap-2`}>
      <h3 className="m-0 text-base">اطلاعیه‌ی زمان‌بندی‌شده</h3>
      <p className="m-0 text-sm text-mute">متن را یک بار بنویسید؛ یا در زمان مشخص (یک بار) یا هر روز در ساعت مشخص (به وقت تهران) برای مشتری‌ها ارسال می‌شود. سقف {fa(max)} زمان‌بندی فعال؛ این ارسال‌ها هم در سقف ۳ اطلاعیه در شبانه‌روز حساب می‌شوند.</p>
      <textarea aria-label="متن اطلاعیه زمان‌بندی‌شده" className="min-h-20 rounded-xl border border-line-2 bg-raised p-3" maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} placeholder="مثلاً: صبح بخیر! پیشنهاد امروز ما کیک شکلاتی است." />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <select aria-label="نوع زمان‌بندی" value={mode} onChange={(e) => setMode(e.target.value as "once" | "daily")} className="min-h-11 rounded-xl border border-line-2 bg-raised px-3">
          <option value="daily">هر روز</option>
          <option value="once">یک بار</option>
        </select>
        {mode === "daily" ? <input type="time" aria-label="ساعت" value={time} onChange={(e) => setTime(e.target.value)} className="min-h-11 rounded-xl border border-line-2 bg-raised px-3" /> : <input type="datetime-local" aria-label="تاریخ و ساعت" value={at} onChange={(e) => setAt(e.target.value)} className="min-h-11 rounded-xl border border-line-2 bg-raised px-3" />}
        <button disabled={busy || !enabled || !text.trim() || (mode === "once" ? !at : !time)} onClick={add} className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50">زمان‌بندی کن</button>
      </div>
      {error && <p role="alert" className="m-0 text-sm text-red-400">{error}</p>}
      {items.map((r) => (
        <div key={r.id} className="flex flex-col gap-1 rounded-xl border border-line-2 p-3 text-sm">
          <p className="m-0 whitespace-pre-line leading-7">{r.text}</p>
          <span className="text-xs text-mute">
            {r.mode === "daily" ? `هر روز ساعت ${fa(r.time)}` : "یک بار"} · {r.active ? `بعدی: ${when(r.next_run)}` : "تمام شد/لغو شد"}{r.last_run ? ` · آخرین اجرا: ${r.last_status}` : ""}
          </span>
          {r.active && <button onClick={() => cancel(r.id)} className="w-fit text-xs text-saffron underline">لغو زمان‌بندی</button>}
        </div>
      ))}
    </section>
  );
}

export function AnnounceTab({ botId }: { botId: string }) {
  const [info, setInfo] = useState<Info | null>(null);
  const [text, setText] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setInfo(await api<Info>(`/bots/${botId}/broadcasts`));
    } catch (e: any) {
      setError(e.message);
    }
  }, [botId]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!info?.items.some((i) => !i.done)) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [info, load]);

  async function send() {
    setBusy(true);
    setError("");
    try {
      await api(`/bots/${botId}/broadcasts`, { body: { text } });
      setText("");
      setConfirm(false);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!info) return <p className="text-sm text-mute">{error || "در حال بارگذاری…"}</p>;
  if (!info.published) return <p className={`${card} m-0 text-sm text-mute`}>اول ربات را در بخش «انتشار» منتشر کنید؛ بعد می‌توانید برای مشتری‌ها اطلاعیه بفرستید.</p>;
  return (
    <div className="flex flex-col gap-3">
      <section className={`${card} flex flex-col gap-2`}>
        <h3 className="m-0 text-base">اطلاعیه برای مشتری‌ها</h3>
        <p className="m-0 text-sm text-mute">
          به {fa(info.audience)} نفری که با ربات شما گفتگو کرده‌اند فرستاده می‌شود. هر مشتری با /stop می‌تواند اطلاعیه‌ها را خاموش کند. حداکثر {fa(info.per_day)} اطلاعیه در هر شبانه‌روز.
        </p>
        <textarea aria-label="متن اطلاعیه" className="min-h-24 rounded-xl border border-line-2 bg-raised p-3" maxLength={1000} value={text} placeholder="مثلاً: این هفته همه‌ی دسرها ۲۰٪ تخفیف دارند."
          onChange={(e) => { setText(e.target.value); setConfirm(false); }} />
        {error && <p role="alert" className="m-0 text-sm text-red-400">{error}</p>}
        {!confirm ? (
          <button className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50" disabled={!text.trim() || info.audience === 0} onClick={() => setConfirm(true)}>پیش‌نمایش و ارسال</button>
        ) : (
          <div className="flex flex-col gap-2 rounded-xl border border-saffron p-3">
            <span className="text-sm">این پیام برای {fa(info.audience)} نفر ارسال می‌شود و پس‌گرفتنی نیست:</span>
            <p className="m-0 whitespace-pre-line rounded-xl bg-raised p-3 text-sm leading-7">{text}</p>
            <div className="flex gap-2">
              <button className="min-h-11 flex-1 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50" disabled={busy} onClick={send}>بله، ارسال شود</button>
              <button className="min-h-11 rounded-xl border border-line-2 px-5" onClick={() => setConfirm(false)}>ویرایش</button>
            </div>
          </div>
        )}
      </section>
      <Scheduled botId={botId} enabled={info.published} />
      {info.items.map((i) => (
        <section key={i.id} className={`${card} flex flex-col gap-1`}>
          <p className="m-0 whitespace-pre-line text-sm leading-7">{i.text}</p>
          <span className="text-xs text-mute">{i.done ? `ارسال شد به ${fa(i.sent)} نفر${i.failed ? ` · ${fa(i.failed)} ناموفق` : ""}` : `در حال ارسال… ${fa(i.sent)} از ${fa(i.audience)}`} · {fa(new Date(i.created_at).toLocaleString("fa-IR"))}</span>
        </section>
      ))}
    </div>
  );
}
