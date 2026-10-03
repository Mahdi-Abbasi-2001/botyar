"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setToken } from "@/lib/api";

type BotRow = { id: number; name: string; version: number };
type Tpl = { key: string; name: string };

export default function Bots() {
  const router = useRouter();
  const [bots, setBots] = useState<BotRow[] | null>(null);
  const [tpls, setTpls] = useState<Tpl[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login/");
      return;
    }
    api<BotRow[]>("/bots").then(setBots).catch((e) => setError(e.message));
    api<Tpl[]>("/templates").then(setTpls).catch(() => {});
  }, [router]);

  async function create(key: string) {
    try {
      const b = await api<BotRow>("/bots", { body: { template: key } });
      router.push(`/bot/?id=${b.id}`);
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-5 py-6">
      <header className="mb-8 flex items-center justify-between">
        <Link href="/" className="text-xl font-extrabold text-indigo-700">بات‌یار</Link>
        <button onClick={() => { setToken(null); router.push("/"); }} className="text-sm text-slate-500 hover:text-slate-800">خروج</button>
      </header>
      {error && <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <button onClick={async () => { try { const b = await api<BotRow>("/bots/draft", { method: "POST", body: {} }); router.push(`/bot/?id=${b.id}`); } catch (e: any) { setError(e.message); } }}
        className="mb-8 w-full rounded-2xl bg-indigo-600 p-5 text-lg font-bold text-white shadow-lg shadow-indigo-200 hover:bg-indigo-700">
        ✨ ساخت ربات جدید با توضیح دادن
      </button>
      <h2 className="mb-3 text-lg font-bold">یا شروع از روی قالب</h2>
      <div className="mb-10 grid gap-3 sm:grid-cols-2">
        {tpls.map((t) => (
          <button key={t.key} onClick={() => create(t.key)} className="rounded-2xl border border-dashed border-indigo-300 bg-white p-5 text-right hover:border-indigo-500 hover:bg-indigo-50">
            <div className="font-bold">{t.name}</div>
            <div className="mt-1 text-sm text-slate-500">ساخت و باز کردن</div>
          </button>
        ))}
      </div>
      <h2 className="mb-3 text-lg font-bold">ربات‌های من</h2>
      {bots === null ? <p className="text-slate-500">در حال بارگذاری...</p> : bots.length === 0 ? (
        <p className="rounded-2xl border border-slate-200 bg-white p-6 text-center text-slate-500">هنوز رباتی نساخته‌اید. یکی از قالب‌های بالا را انتخاب کنید.</p>
      ) : (
        <ul className="space-y-2">
          {bots.map((b) => (
            <li key={b.id}>
              <Link href={`/bot/?id=${b.id}`} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 hover:border-indigo-400">
                <span className="font-semibold">{b.name}</span>
                <span className="text-xs text-slate-500">نسخه {b.version}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
