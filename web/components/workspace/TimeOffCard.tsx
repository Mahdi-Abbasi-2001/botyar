"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fa } from "@/components/ui";

type Off = { id: number; block_id: string; date_fa: string; start: string; end: string; staff: string; note: string };
type Booking = { id: string; title: string; staff: string[] };

const input = "min-h-10 rounded-lg border border-line-2 bg-raised px-2.5 text-sm outline-none focus:border-saffron";

/** The owner closes hours on one date (afternoon off, a staff member's leave): those times are no longer offered.
 *  Bookings already there are only counted, so the owner cancels them deliberately, with a reason. */
export function TimeOffCard({ botId, bookings }: { botId: string; bookings: Booking[] }) {
  const [rows, setRows] = useState<Off[]>([]);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ block_id: bookings[0]?.id ?? "", date: "", start: "13:00", end: "18:00", staff: "", note: "" });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => { api<Off[]>(`/bots/${botId}/time-off`).then(setRows).catch(() => {}); }, [botId]);
  useEffect(load, [load]);
  const staff = bookings.find((b) => b.id === f.block_id)?.staff ?? [];

  async function add() {
    setError("");
    setMsg("");
    try {
      const r = await api<{ clashes: number }>(`/bots/${botId}/time-off`, { body: f });
      setMsg(r.clashes ? `ثبت شد. ${fa(r.clashes)} نوبت از قبل در این بازه هست؛ اگر لازم است، آن‌ها را از فهرست زیر با ذکر دلیل لغو کنید.` : "ثبت شد؛ این ساعت‌ها دیگر به مشتری پیشنهاد نمی‌شوند.");
      setF({ ...f, date: "", note: "" });
      load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-line-2 bg-panel p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong>بستن بازه‌ی زمانی</strong>
        <button onClick={() => setOpen(!open)} className="text-saffron underline">{open ? "بستن فرم" : "بستن چند ساعت از یک روز"}</button>
      </div>
      <span className="text-xs leading-6 text-mute">مثلاً تعطیلی بعدازظهر سه‌شنبه یا مرخصی یکی از همکاران؛ برای کل روزهای تعطیل، از «گفت‌وگوی ساخت» بخواهید.</span>
      {open && (
        <div className="flex flex-wrap items-end gap-2">
          {bookings.length > 1 && (
            <select aria-label="بخش" className={input} value={f.block_id} onChange={(e) => setF({ ...f, block_id: e.target.value, staff: "" })}>
              {bookings.map((b) => <option key={b.id} value={b.id}>{b.title}</option>)}
            </select>
          )}
          <input aria-label="تاریخ" className={input + " w-32"} placeholder="۱۴۰۵/۰۷/۲۰" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
          <input aria-label="از ساعت" type="time" className={input} value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} />
          <input aria-label="تا ساعت" type="time" className={input} value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} />
          {staff.length > 0 && (
            <select aria-label="همکار" className={input} value={f.staff} onChange={(e) => setF({ ...f, staff: e.target.value })}>
              <option value="">همه‌ی همکاران</option>
              {staff.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          )}
          <input aria-label="توضیح" className={input + " w-36"} maxLength={100} placeholder="توضیح (اختیاری)" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
          <button disabled={!f.date.trim()} onClick={add} className="min-h-10 rounded-lg bg-saffron px-4 font-bold text-ink disabled:opacity-50">ثبت</button>
        </div>
      )}
      {msg && <span className="text-xs leading-6 text-mint-fg">{msg}</span>}
      {error && <span className="text-xs text-bad-soft">{error}</span>}
      {rows.map((r) => (
        <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-raised px-3 py-1.5 text-xs">
          <span>{fa(r.date_fa)} · {fa(r.start)} تا {fa(r.end)}{r.staff ? ` · ${r.staff}` : ""}{r.note ? ` · ${r.note}` : ""}</span>
          <button onClick={async () => { await api(`/bots/${botId}/time-off/${r.id}`, { method: "DELETE" }); load(); }} className="text-mute underline hover:text-fg">باز کردن دوباره</button>
        </div>
      ))}
    </section>
  );
}
