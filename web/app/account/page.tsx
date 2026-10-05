"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { ErrorNote, Logo, fa } from "@/components/ui";

type Plan = { key: string; name: string; price: number; bots: number; live_bots: number; customers: number; ai_requests: number };
type Pay = { id: number; plan: string; name: string; amount: number; simulated: boolean; at: string };
type Me = { demo?: boolean; payments?: Pay[]; plan: Plan; usage: { bots: number; live_bots: number; ai_requests: number; per_bot: { id: number; name: string; live: boolean; customers: number }[] }; pending_request: string | null; admin: boolean };
type Plans = { plans: (Plan & { tagline: string })[] };
type Req = { id: number; email: string; plan: string; current: string; note: string; status: string };

const card = "rounded-2xl border border-line-2 bg-panel p-4";

function Meter({ label, used, max }: { label: string; used: number; max: number }) {
  const pct = Math.min(100, Math.round((used / Math.max(max, 1)) * 100));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-sm"><span>{label}</span><span className={pct >= 100 ? "text-bad-soft" : "text-fg-2"}>{fa(used)} از {fa(max.toLocaleString("en-US"))}</span></div>
      <div className="h-2 overflow-hidden rounded-full bg-raised"><div className={`h-full ${pct >= 90 ? "bg-bad-soft" : "bg-saffron"}`} style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

export default function Account() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [plans, setPlans] = useState<Plans | null>(null);
  const [reqs, setReqs] = useState<Req[]>([]);
  const [pick, setPick] = useState("");
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

  async function upgrade(plan: string, name: string) {
    setError("");
    setMsg("");
    if (me?.demo && !confirm(`پلن «${name}» فعال شود؟ این پرداخت آزمایشی است و هیچ پولی کسر نمی‌شود.`)) return;
    try {
      const r = await api<{ simulated?: boolean }>("/me/upgrade", { body: { plan, note } });
      setMsg(r.simulated ? "✅ پرداخت آزمایشی با موفقیت انجام شد و پلن شما فعال شد (پولی کسر نشد)." : "درخواست شما ثبت شد؛ پس از بررسی پلن فعال می‌شود.");
      setNote("");
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function cancelPlan() {
    setError("");
    setMsg("");
    try {
      await api("/me/plan/cancel", { method: "POST", body: {} });
      setMsg("به پلن رایگان برگشتید. رباتی که منتشر شده بود همچنان فعال می‌ماند، ولی ساخت یا انتشار رباتِ تازه از سقف رایگان پیروی می‌کند.");
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
            <section className={`${card} flex flex-col gap-4`}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="m-0 text-lg font-extrabold">تغییر پلن</h2>
                <Link href="/pricing/" className="text-sm text-saffron underline">مقایسه‌ی کامل پلن‌ها</Link>
              </div>
              {me.demo && <p className="m-0 rounded-xl border border-amber-line bg-saffron/10 px-3 py-2 text-sm leading-7 text-amber-fg">نسخه‌ی نمایشی: هنوز درگاه پرداخت وصل نیست؛ «پرداخت» شبیه‌سازی می‌شود، پلن بلافاصله فعال می‌شود و هیچ پولی کسر نمی‌شود.</p>}
              {me.pending_request && <p className="m-0 text-sm text-mute">درخواست تغییر به پلن «{plans?.plans.find((p) => p.key === me.pending_request)?.name ?? me.pending_request}» در حال بررسی است.</p>}
              <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(200px,1fr))]">
                {plans?.plans.filter((p) => p.key !== "free").map((p) => {
                  const current = p.key === me.plan.key;
                  const picked = !me.demo && pick === p.key && !current;
                  return (
                    <div key={p.key} className={`flex flex-col gap-2 rounded-2xl border p-4 ${current ? "border-mint-line bg-mint-bg/40" : picked ? "border-saffron bg-saffron/5" : "border-line-2"}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-base font-extrabold">{p.name}</span>
                        {current && <span className="rounded-full bg-mint px-2 py-0.5 text-xs font-bold text-ink">پلن فعلی</span>}
                      </div>
                      <span className="text-xs leading-6 text-mute">{p.tagline}</span>
                      <span className="text-xl font-black text-saffron">{fa(p.price.toLocaleString("en-US"))} <span className="text-xs font-bold text-fg-2">تومان / ماه</span></span>
                      <span className="text-xs leading-6 text-fg-2">{fa(p.bots)} ربات · {fa(p.live_bots)} منتشرشده · {fa(p.ai_requests.toLocaleString("en-US"))} درخواست ایجنت</span>
                      {!current && !me.pending_request && (
                        me.demo ? (
                          <button onClick={() => upgrade(p.key, p.name)} className="mt-auto min-h-11 rounded-xl bg-saffron px-3 text-sm font-bold text-ink hover:bg-saffron-hi">
                            {p.price > me.plan.price ? "ارتقا" : "تغییر"} · پرداخت آزمایشی
                          </button>
                        ) : (
                          <button onClick={() => setPick(p.key)} aria-pressed={picked} className={`mt-auto min-h-11 rounded-xl px-3 text-sm font-bold ${picked ? "bg-saffron text-ink" : "border border-line-2 hover:border-saffron"}`}>
                            {picked ? "انتخاب شد" : "انتخاب این پلن"}
                          </button>
                        )
                      )}
                    </div>
                  );
                })}
              </div>
              {!me.demo && !me.pending_request && pick && pick !== me.plan.key && (
                <div className="flex flex-col gap-3">
                  <textarea aria-label="توضیح" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="کسب‌وکارت چیست و چرا به این پلن نیاز داری؟ (اختیاری)" className="min-h-20 rounded-xl border border-line-2 bg-raised p-3" />
                  <button onClick={() => upgrade(pick, plans?.plans.find((x) => x.key === pick)?.name ?? pick)} className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink">ثبت درخواست پلن «{plans?.plans.find((x) => x.key === pick)?.name}»</button>
                  <p className="m-0 text-xs leading-6 text-dim">پرداخت آنلاین اشتراک هنوز راه‌اندازی نشده؛ تیم بات‌یار با شما هماهنگ می‌کند و پلن را فعال می‌کند.</p>
                </div>
              )}
            </section>
            {me.plan.key !== "free" && <button onClick={cancelPlan} className="w-fit text-sm text-mute underline hover:text-bad">لغو اشتراک و برگشت به پلن رایگان</button>}
            {(me.payments?.length ?? 0) > 0 && (
              <section className={`${card} flex flex-col gap-1 text-sm`}>
                <h2 className="m-0 text-lg font-extrabold">پرداخت‌ها</h2>
                {me.payments!.map((p) => (
                  <span key={p.id} className="text-fg-2">{fa(new Date(p.at).toLocaleDateString("fa-IR"))} · پلن {p.name} · {fa(p.amount.toLocaleString("en-US"))} تومان{p.simulated ? " · (پرداخت آزمایشی، پولی کسر نشد)" : ""}</span>
                ))}
              </section>
            )}
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
