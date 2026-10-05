"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PENDING_KEY, api, getToken, setToken } from "@/lib/api";
import { ErrorNote, Icon, Logo, fa } from "@/components/ui";

type BotRow = { id: number; name: string; version: number };
type Tpl = { key: string; name: string };

const TPL_INFO: Record<string, { desc: string; tags: string[] }> = {
  workshop: { desc: "زمان‌ها با ظرفیت · فرم نام و موبایل · اعلان به مدیر", tags: ["نوبت", "فرم", "اعلان"] },
  cafe: { desc: "منو با آیتم و قیمت · سبد سفارش · اعلان به مدیر", tags: ["سفارش", "منو", "اعلان"] },
};
const EXAMPLES = ["نوبت‌دهی کلینیک", "ثبت‌نام کلاس باشگاه", "سفارش شیرینی‌فروشی"];

export default function Bots() {
  const router = useRouter();
  const [bots, setBots] = useState<BotRow[] | null>(null);
  const [tpls, setTpls] = useState<Tpl[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login/");
      return;
    }
    api<BotRow[]>("/bots").then(setBots).catch((e) => setError(e.message));
    api<Tpl[]>("/templates").then(setTpls).catch(() => {});
  }, [router]);

  async function startDescribed(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const b = await api<BotRow>("/bots/draft", { method: "POST", body: {} });
      // the workspace picks this up and sends it to the agent straight away
      if (text.trim().length >= 2) sessionStorage.setItem(PENDING_KEY(b.id), text.trim());
      router.push(`/bot/?id=${b.id}`);
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  }

  async function fromTemplate(key: string) {
    try {
      const b = await api<BotRow>("/bots", { body: { template: key } });
      router.push(`/bot/?id=${b.id}`);
    } catch (e: any) {
      setError(e.message);
    }
  }

  const first = bots !== null && bots.length === 0;

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-4 py-3.5 sm:px-6">
        <Logo size="sm" />
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/account/" className="min-h-11 content-center text-fg-2 hover:text-fg">پلن و مصرف</Link>
          <Link href="/pricing/" className="min-h-11 content-center text-fg-2 hover:text-fg">تعرفه‌ها</Link>
          <button onClick={() => { setToken(null); router.push("/"); }} className="min-h-11 text-fg-2 hover:text-fg">خروج</button>
        </nav>
      </header>

      <main className="mx-auto flex max-w-[1320px] flex-col gap-9 px-4 py-8 sm:px-6">
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex flex-wrap gap-5">
          <form onSubmit={startDescribed} className="bp flex min-w-0 flex-[2_1_560px] flex-col gap-4 rounded-[22px] border border-saffron bg-panel p-5 sm:p-6">
            <h1 className="m-0 text-2xl font-black sm:text-[32px]">
              {first ? <>سلام! اولین ربات‌ت را <span className="text-saffron">تعریف کن.</span></> : "ساخت ربات جدید با توضیح دادن"}
            </h1>
            <label htmlFor="nb" className="text-sm text-fg-2">ربات جدیدت چه کاری انجام بدهد؟</label>
            <textarea id="nb" rows={3} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="مثلاً: برای کافه‌ام ربات سفارش می‌خوام؛ منوی نوشیدنی و کیک، و سفارش که ثبت شد به من خبر بده."
              className="resize-none rounded-2xl border border-line-2 bg-ink p-3.5 text-base leading-8 text-fg outline-none placeholder:text-dim focus:border-saffron" />
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((x) => (
                <button key={x} type="button" onClick={() => setText(`برای ${x} ربات می‌خوام. `)} className="min-h-11 rounded-full border border-line-2 bg-raised px-3.5 text-[13px] text-fg-2 hover:text-fg">{x}</button>
              ))}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-[13px] text-dim">ایجنت اگر چیزی مبهم بود، کوتاه می‌پرسد.</span>
              <button disabled={busy} className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-saffron px-5 font-extrabold text-ink hover:bg-saffron-hi disabled:opacity-60">
                {busy ? "در حال آماده‌سازی…" : "بساز"} <Icon name="send" strokeWidth={2.4} />
              </button>
            </div>
          </form>

          <div className="flex flex-[1_1_300px] flex-col gap-3">
            <span className="text-sm text-mute">یا از یک نمونه شروع کن</span>
            {tpls.map((t) => {
              const info = TPL_INFO[t.key];
              return (
                <button key={t.key} onClick={() => fromTemplate(t.key)} className="flex flex-1 flex-col gap-2.5 rounded-[18px] border border-line-2 bg-panel p-[18px] text-right hover:border-saffron">
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

        {!first && (
          <section className="flex flex-col gap-3.5">
            <h2 className="m-0 text-[22px] font-extrabold">ربات‌های من</h2>
            {bots === null ? (
              <p className="text-mute">در حال بارگذاری…</p>
            ) : (
              <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(320px,1fr))]">
                {bots.map((b) => (
                  <Link key={b.id} href={`/bot/?id=${b.id}`}
                    className={`flex flex-col gap-3.5 rounded-[18px] border bg-panel p-5 hover:border-saffron ${b.version ? "border-line" : "border-dashed border-amber-line"}`}>
                    <div className="flex items-start justify-between gap-2.5">
                      <span className="text-[17px] font-extrabold leading-relaxed">{b.name}</span>
                      {b.version ? (
                        <span className="shrink-0 rounded-full border border-line-3 px-2.5 py-0.5 text-xs text-fg-2">نسخه {fa(b.version)}</span>
                      ) : (
                        <span className="shrink-0 rounded-full border border-amber-line px-2.5 py-0.5 text-xs text-saffron">پیش‌نویس</span>
                      )}
                    </div>
                    <span className="text-[13px] text-mute">{b.version ? "باز کردن، امتحان کردن یا تغییر دادن" : "هنوز ساخته نشده · ادامه‌ی گفت‌وگو با ایجنت"}</span>
                  </Link>
                ))}
              </div>
            )}
          </section>
        )}
        {first && (
          <p className="flex items-center gap-2.5 text-[13px] text-mute"><Icon name="shield" className="text-mint" /> هر نسخه قبل از تحویل با تست خودکار بررسی می‌شود.</p>
        )}
      </main>
    </div>
  );
}
