"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { ErrorNote, Logo, fa } from "@/components/ui";

type Plan = { key: string; name: string; price: number; bots: number; live_bots: number; customers: number; ai_requests: number };
type Me = { plan: Plan; usage: { bots: number; live_bots: number; ai_requests: number; per_bot: { id: number; name: string; live: boolean; customers: number }[] }; pending_request: string | null; admin: boolean };
type Plans = { plans: (Plan & { tagline: string })[] };
type Req = { id: number; email: string; plan: string; current: string; note: string; status: string };

const card = "rounded-2xl border border-line-2 bg-panel p-4";

function Meter({ label, used, max }: { label: string; used: number; max: number }) {
  const pct = Math.min(100, Math.round((used / Math.max(max, 1)) * 100));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-sm"><span>{label}</span><span className={pct >= 100 ? "text-red-400" : "text-fg-2"}>{fa(used)} از {fa(max.toLocaleString("en-US"))}</span></div>
      <div className="h-2 overflow-hidden rounded-full bg-raised"><div className={`h-full ${pct >= 90 ? "bg-red-400" : "bg-saffron"}`} style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

export default function Account() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [plans, setPlans] = useState<Plans | null>(null);
  const [reqs, setReqs] = useState<Req[]>([]);
  const [pick, setPick] = useState("pro");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const m = await api<Me>("/me/plan");
      setMe(m);
      if (m.admin) setReqs(await api<Req[]>("/admin/upgrades"));
    } catch (e: any) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    if (!getToken()) {
      router.replace("/login/");
      return;
    }
    load();
    api<Plans>("/plans").then(setPlans).catch(() => {});
  }, [router, load]);

  async function upgrade() {
    setError("");
    setMsg("");
    try {
      await api("/me/upgrade", { body: { plan: pick, note } });
      setMsg("درخواست شما ثبت شد؛ پس از بررسی پلن فعال می‌شود.");
      setNote("");
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function decide(id: number, approve: boolean) {
    try {
      await api(`/admin/upgrades/${id}`, { body: { approve } });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-4 py-3.5 sm:px-6">
        <Logo size="sm" />
        <nav className="flex gap-4 text-sm"><Link href="/bots/" className="text-fg-2 hover:text-fg">ربات‌های من</Link><Link href="/pricing/" className="text-fg-2 hover:text-fg">تعرفه‌ها</Link></nav>
      </header>
      <main className="mx-auto flex max-w-[860px] flex-col gap-5 px-4 py-8 sm:px-6">
        <h1 className="m-0 text-2xl font-black">پلن و مصرف</h1>
        {error && <ErrorNote>{error}</ErrorNote>}
        {msg && <p className="m-0 text-sm text-mint">{msg}</p>}
        {me && (
          <>
            <section className={`${card} flex flex-col gap-3`}>
              <div className="flex items-center justify-between"><h2 className="m-0 text-lg font-extrabold">پلن فعلی: {me.plan.name}</h2>{me.plan.price > 0 && <span className="text-sm text-fg-2">{fa(me.plan.price.toLocaleString("en-US"))} تومان / ماه</span>}</div>
              <Meter label="ربات‌ها" used={me.usage.bots} max={me.plan.bots} />
              <Meter label="ربات‌های منتشرشده" used={me.usage.live_bots} max={me.plan.live_bots} />
              <Meter label="درخواست به ایجنت (۳۰ روز گذشته)" used={me.usage.ai_requests} max={me.plan.ai_requests} />
              {me.usage.per_bot.filter((b) => b.live).map((b) => <Meter key={b.id} label={`مشتری فعال · ${b.name}`} used={b.customers} max={me.plan.customers} />)}
            </section>
            <section className={`${card} flex flex-col gap-3`}>
              <h2 className="m-0 text-lg font-extrabold">ارتقای پلن</h2>
              {me.pending_request ? (
                <p className="m-0 text-sm text-mute">درخواست ارتقا به پلن «{plans?.plans.find((p) => p.key === me.pending_request)?.name ?? me.pending_request}» در حال بررسی است.</p>
              ) : (
                <>
                  <select aria-label="پلن" value={pick} onChange={(e) => setPick(e.target.value)} className="min-h-11 rounded-xl border border-line-2 bg-raised px-3">
                    {plans?.plans.filter((p) => p.key !== "free").map((p) => <option key={p.key} value={p.key}>{p.name} — {fa(p.price.toLocaleString("en-US"))} تومان در ماه (پیشنهادی)</option>)}
                  </select>
                  <textarea aria-label="توضیح" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="کسب‌وکارت چیست و چرا به این پلن نیاز داری؟ (اختیاری)" className="min-h-20 rounded-xl border border-line-2 bg-raised p-3" />
                  <button onClick={upgrade} className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink">ثبت درخواست ارتقا</button>
                  <p className="m-0 text-xs leading-6 text-dim">پرداخت آنلاین اشتراک هنوز راه‌اندازی نشده؛ تیم بات‌یار با شما هماهنگ می‌کند و پلن را فعال می‌کند.</p>
                </>
              )}
            </section>
            {me.admin && (
              <section className={`${card} flex flex-col gap-2`}>
                <h2 className="m-0 text-lg font-extrabold">درخواست‌های ارتقا (مدیر)</h2>
                {reqs.length === 0 && <p className="m-0 text-sm text-mute">درخواستی نیست.</p>}
                {reqs.map((r) => (
                  <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line-2 p-3 text-sm">
                    <span dir="ltr">{r.email}</span><span>{r.current} → <b>{r.plan}</b></span>{r.note && <span className="text-mute">{r.note}</span>}
                    {r.status === "pending" ? (
                      <span className="flex gap-2"><button className="rounded-lg bg-saffron px-3 py-1 font-bold text-ink" onClick={() => decide(r.id, true)}>تأیید</button><button className="rounded-lg border border-line-2 px-3 py-1" onClick={() => decide(r.id, false)}>رد</button></span>
                    ) : <span className="text-mute">{r.status === "approved" ? "تأیید شد" : "رد شد"}</span>}
                  </div>
                ))}
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
