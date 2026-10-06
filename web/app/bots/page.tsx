"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PENDING_KEY, api, getToken, isPlanLimit } from "@/lib/api";
import { ErrorNote, Icon, PlanLimitNote, TestBar, fa } from "@/components/ui";
import { ago } from "@/components/workspace/model";
import { AppHeader } from "@/components/AppHeader";
import { PageTransition } from "@/components/PageTransition";

type BotRow = {
  id: number; name: string; version: number;
  tests?: { passed: number; total: number } | null;
  live?: { messenger: "bale" | "tg"; version: number }[];
  last_change?: { note: string; at: string } | null;
};
const MESSENGER = { bale: "بله", tg: "تلگرام" } as const;

/** Where the bot stands, in one pill: draft / not published / live on … / a newer version waits. */
function Status({ b }: { b: BotRow }) {
  const live = b.live ?? [];
  if (!b.version) return <span className="shrink-0 rounded-full border border-amber-line px-2.5 py-0.5 text-xs text-saffron">پیش‌نویس</span>;
  if (!live.length) return <span className="shrink-0 rounded-full border border-line-3 px-2.5 py-0.5 text-xs text-fg-2">منتشر نشده</span>;
  if (live.some((l) => l.version < b.version)) return <span className="shrink-0 rounded-full border border-amber-line bg-saffron/10 px-2.5 py-0.5 text-xs text-saffron">نسخه‌ی تازه منتشر نشده</span>;
  return (
    <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-mint-bg px-2.5 py-0.5 text-xs text-mint-fg">
      <span className="h-1.5 w-1.5 rounded-full bg-mint" /> فعال در {live.map((l) => MESSENGER[l.messenger]).join(" و ")}
    </span>
  );
}
type Tpl = { key: string; name: string };

const TPL_INFO: Record<string, { desc: string; tags: string[] }> = {
  workshop: { desc: "سانس با ظرفیت · دریافت نام و موبایل · اطلاع به مدیر", tags: ["نوبت", "فرم", "اطلاع‌رسانی"] },
  cafe: { desc: "منو با قیمت · سبد سفارش · اطلاع به مدیر", tags: ["سفارش", "منو", "اطلاع‌رسانی"] },
};
const EXAMPLES: [string, string][] = [
  ["کلینیک دندانپزشکی", "برای کلینیک دندانپزشکی‌ام یک ربات نوبت‌دهی می‌خواهم. "],
  ["کلاس‌های باشگاه", "برای ثبت‌نام کلاس‌های باشگاهم یک ربات می‌خواهم. "],
  ["شیرینی‌فروشی", "برای شیرینی‌فروشی‌ام یک ربات سفارش آنلاین می‌خواهم. "],
];

export default function Bots() {
  const router = useRouter();
  const [bots, setBots] = useState<BotRow[] | null>(null);
  const [tpls, setTpls] = useState<Tpl[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [limit, setLimit] = useState("");  // plan limit: shown beside the button the owner pressed
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login/");
      return;
    }
    api<BotRow[]>("/bots").then(setBots).catch((e) => setError(e.message));
    api<Tpl[]>("/templates").then(setTpls).catch(() => {});
    // «ساخت همین ربات» on the landing page arrives with its sample description: prefill the new-bot box
    const described = new URLSearchParams(window.location.search).get("describe");
    if (described) {
      setText(described.slice(0, 2000));
      setCreating(true);
      window.history.replaceState(null, "", "/bots/");
    }
  }, [router]);

  async function startDescribed(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setLimit("");
    try {
      const b = await api<BotRow>("/bots/draft", { method: "POST", body: {} });
      // the workspace picks this up and sends it to the agent straight away
      if (text.trim().length >= 2) sessionStorage.setItem(PENDING_KEY(b.id), text.trim());
      router.push(`/bot/?id=${b.id}`);
    } catch (e: any) {
      if (isPlanLimit(e)) setLimit(e.message);
      else setError(e.message);
      setBusy(false);
    }
  }

  async function fromTemplate(key: string) {
    setLimit("");
    try {
      const b = await api<BotRow>("/bots", { body: { template: key } });
      router.push(`/bot/?id=${b.id}`);
    } catch (e: any) {
      if (isPlanLimit(e)) setLimit(e.message);
      else setError(e.message);
    }
  }

  const first = bots !== null && bots.length === 0;
  const hasBots = bots !== null && bots.length > 0;

  // the new-bot box: the whole page for a first-time owner; for everyone else it opens under «ربات‌های من»
  // from the «+ ربات جدید» button, so the list (what returning owners come for) stays on top
  const creator = (
    <div id="new-bot" className={`flex flex-wrap gap-5 ${first ? "" : "anim-tab"}`}
      onKeyDown={(e) => { if (e.key === "Escape" && !first) setCreating(false); }}>
      <form onSubmit={startDescribed} className="bp flex min-w-0 flex-[2_1_560px] flex-col gap-4 rounded-[22px] border border-saffron bg-panel p-5 sm:p-6">
        {first ? (
          <h1 className="m-0 text-2xl font-black sm:text-[32px]">اولین ربات خود را توضیح دهید</h1>
        ) : (
          <h2 className="m-0 text-xl font-black sm:text-2xl">ساخت ربات جدید</h2>
        )}
        <label htmlFor="nb" className="text-sm text-fg-2">ربات جدید شما قرار است چه کاری انجام دهد؟</label>
        <textarea id="nb" autoFocus={!first} rows={3} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="مثلاً: برای کافه‌ام یک ربات سفارش می‌خواهم، با منوی نوشیدنی و کیک؛ هر سفارش که ثبت شد به من خبر بدهد."
          className="resize-none rounded-2xl border border-line-2 bg-ink p-3.5 text-base leading-8 text-fg outline-none placeholder:text-dim focus:border-saffron" />
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map(([x, starter]) => (
            <button key={x} type="button" onClick={() => setText(starter)} className="min-h-11 rounded-full border border-line-2 bg-raised px-3.5 text-[13px] text-fg-2 hover:text-fg">{x}</button>
          ))}
        </div>
        {limit && <PlanLimitNote text={limit} />}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-[13px] text-dim">اگر بخشی از توضیح مبهم باشد، بات‌یار پیش از ساخت سؤال کوتاهی می‌پرسد.</span>
          <button disabled={busy} className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-saffron px-5 font-extrabold text-ink hover:bg-saffron-hi disabled:opacity-60">
            {busy ? "در حال آماده‌سازی…" : "ساخت ربات"} <Icon name="send" strokeWidth={2.4} />
          </button>
        </div>
      </form>

      <div className="flex flex-[1_1_300px] flex-col gap-3">
        <span className="text-sm text-mute">یا از یک نمونه‌ی آماده شروع کنید</span>
        {tpls.map((t) => {
          const info = TPL_INFO[t.key];
          return (
            <button key={t.key} onClick={() => fromTemplate(t.key)} className="lift flex flex-1 flex-col gap-2.5 rounded-[18px] border border-line-2 bg-panel p-[18px] text-right hover:border-saffron">
              <span className="text-[17px] font-extrabold">{t.name}</span>
              {info && <span className="text-[13px] leading-7 text-mute">{info.desc}</span>}
              {info && (
                <span className="flex flex-wrap gap-1.5 text-xs">
                  {info.tags.map((tag, i) => (
                    <span key={tag} className={`rounded-md border px-2 py-0.5 ${i === info.tags.length - 1 ? "border-amber-line text-amber-fg/80" : "border-line-3"}`}>{tag}</span>
                  ))}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );

  const list = hasBots && (
    <section className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="m-0 text-[26px] font-black">ربات‌های من</h1>
        <button type="button" aria-expanded={creating} aria-controls="new-bot" onClick={() => setCreating(!creating)}
          className={`inline-flex min-h-11 items-center gap-2 rounded-xl px-4 text-sm font-bold ${creating ? "border border-line-2 text-fg-2 hover:text-fg" : "bg-saffron text-ink hover:bg-saffron-hi"}`}>
          {creating ? "بستن" : <><Icon name="plus" size={16} strokeWidth={2.4} /> ربات جدید</>}
        </button>
      </div>
      {creating && creator}
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(300px,1fr))]">
        {bots!.map((b) => {
          const isLive = !!b.live?.length;
          return (
            <Link key={b.id} href={`/bot/?id=${b.id}`}
              className={`lift flex flex-col gap-3 rounded-[18px] border bg-panel p-5 hover:border-saffron ${!b.version ? "border-dashed border-amber-line" : isLive ? "border-mint-line" : "border-line"}`}>
              <div className="flex items-start justify-between gap-2.5">
                <span className="text-[17px] font-extrabold leading-relaxed">{b.name}</span>
                <Status b={b} />
              </div>
              {!b.version ? (
                <span className="text-[13px] text-mute">هنوز ساخته نشده؛ برای ادامه‌ی گفت‌وگو باز کنید</span>
              ) : (
                <>
                  {b.tests && b.tests.total > 0 && (
                    <div className="flex items-center gap-2.5">
                      <div className="w-28"><TestBar passed={b.tests.passed} total={b.tests.total} h={5} /></div>
                      <span className={`text-xs ${b.tests.passed === b.tests.total ? "text-mint" : "text-bad-soft"}`}>{fa(b.tests.passed)} از {fa(b.tests.total)} تست موفق</span>
                    </div>
                  )}
                  {b.last_change && (
                    <span className="line-clamp-2 text-[13px] leading-7 text-mute">
                      نسخه‌ی {fa(b.version)} · {ago(b.last_change.at)}{b.last_change.note && <> · «{b.last_change.note}»</>}
                    </span>
                  )}
                </>
              )}
            </Link>
          );
        })}
      </div>
    </section>
  );

  return (
    <PageTransition>
      <div className="min-h-screen">
        <AppHeader />

        <main className="mx-auto flex max-w-[1320px] flex-col gap-9 px-4 py-8 sm:px-6">
          {error && <ErrorNote>{error}</ErrorNote>}
          {bots === null && !error && <p className="text-mute">در حال بارگذاری…</p>}
          {list}
          {first && creator}

          {first && (
            <p className="flex items-center gap-2.5 text-[13px] text-mute"><Icon name="shield" className="text-mint" /> هر نسخه پیش از تحویل با تست خودکار بررسی می‌شود.</p>
          )}
        </main>
      </div>
    </PageTransition>
  );
}
