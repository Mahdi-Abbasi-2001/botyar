"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fa } from "@/components/ui";
import { ExportButtons } from "@/components/workspace/ExportButtons";

type Row = { id: number; banned?: boolean; name: string; channel: string; messages: number; first_seen: string; last_seen: string };
type Data = { total: number; active_30d: number; cap: number; plan: string; page: number; page_size: number; items: Row[] };

const card = "rounded-2xl border border-line-2 bg-panel p-4";
const day = (iso: string) => fa(new Date(iso).toLocaleDateString("fa-IR"));

export function CustomersTab({ botId }: { botId: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [refs, setRefs] = useState<{ total: number; top: { name: string; invited: number }[] } | null>(null);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await api<Data>(`/bots/${botId}/customers?q=${encodeURIComponent(q)}&page=${page}`));
    } catch (e: any) {
      setError(e.message);
    }
  }, [botId, q, page]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    api<{ total: number; top: { name: string; invited: number }[] }>(`/bots/${botId}/referrals`).then(setRefs).catch(() => {});
  }, [botId]);
  async function toggleBan(r: Row) {
    try {
      await api(`/bots/${botId}/customers/${r.id}/${r.banned ? "unban" : "ban"}`, { method: "POST", body: {} });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="m-0 text-base">مشتریان</h3>
        {data && data.total > 0 && <ExportButtons path={`/bots/${botId}/export/customers`} name="customers" onError={setError} />}
      </div>
      {data && (
        <p className={`${card} m-0 text-sm leading-7 text-fg-2`}>
          تا این لحظه {fa(data.total)} نفر به ربات پیام داده‌اند و {fa(data.active_30d)} نفر در ۳۰ روز گذشته فعال بوده‌اند (سقف پلن «{data.plan}»: {fa(data.cap.toLocaleString("en-US"))} نفر).
        </p>
      )}
      {refs && refs.total > 0 && (
        <section className={`${card} flex flex-col gap-1 text-sm`}>
          <strong>برترین معرف‌ها ({fa(refs.total)} دعوت موفق)</strong>
          {refs.top.map((t, i) => <span key={i}>{fa(i + 1)}. {t.name} · {fa(t.invited)} نفر</span>)}
        </section>
      )}
      {error && <p role="alert" className="m-0 text-sm text-red-400">{error}</p>}
      <input aria-label="جست‌وجوی نام" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="جست‌وجوی نام…" className="min-h-11 rounded-xl border border-line-2 bg-raised px-3" />
      {data && data.items.length === 0 && <p className={`${card} m-0 text-sm text-mute`}>هنوز هیچ مشتری‌ای با ربات منتشرشده‌ی شما گفت‌وگو نکرده است.</p>}
      {data && data.items.length > 0 && (
        <div className={`${card} overflow-x-auto p-0`}>
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line-2 text-mute"><th className="p-3 text-right">نام</th><th className="p-3 text-right">پیام‌رسان</th><th className="p-3 text-right">اولین پیام</th><th className="p-3 text-right">آخرین فعالیت</th><th className="p-3 text-right">تعداد پیام</th><th className="p-3 text-right"></th></tr></thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id} className="border-b border-line-2 last:border-0"><td className="p-3">{r.name}</td><td className="p-3">{r.channel}</td><td className="p-3">{day(r.first_seen)}</td><td className="p-3">{day(r.last_seen)}</td><td className="p-3">{fa(r.messages)}</td><td className="p-3"><button onClick={() => toggleBan(r)} className={`text-xs underline ${r.banned ? "text-mint" : "text-mute hover:text-bad"}`}>{r.banned ? "رفع مسدودیت" : "مسدود کردن"}</button></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button disabled={page === 0} onClick={() => setPage(page - 1)} className="min-h-11 rounded-xl border border-line-2 px-4 disabled:opacity-40">قبلی</button>
          <span>{fa(page + 1)} از {fa(pages)}</span>
          <button disabled={page + 1 >= pages} onClick={() => setPage(page + 1)} className="min-h-11 rounded-xl border border-line-2 px-4 disabled:opacity-40">بعدی</button>
        </div>
      )}
    </div>
  );
}
