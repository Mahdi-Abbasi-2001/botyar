"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { ErrorNote, Logo, fa } from "@/components/ui";

type Plan = { key: string; name: string; price: number; bots: number; live_bots: number; customers: number; ai_requests: number; tagline: string };
type Plans = { plans: Plan[]; included: string[]; window_days: number; prices_proposed: boolean; demo?: boolean };

export default function Pricing() {
  const [data, setData] = useState<Plans | null>(null);
  const [error, setError] = useState("");
  const [loggedIn, setLoggedIn] = useState(false);
  useEffect(() => {
    setLoggedIn(!!getToken());
    api<Plans>("/plans").then(setData).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-4 py-3.5 sm:px-6">
        <Logo size="sm" />
        <Link href={loggedIn ? "/bots/" : "/login/"} className="min-h-11 content-center text-sm text-fg-2 hover:text-fg">{loggedIn ? "ربات‌های من" : "ورود / ثبت‌نام"}</Link>
      </header>
      <main className="mx-auto flex max-w-[1180px] flex-col gap-8 px-4 py-10 sm:px-6">
        <div className="flex flex-col gap-3">
          <h1 className="m-0 text-3xl font-black sm:text-4xl">تعرفه‌ها: یک قیمت ثابت ماهانه، بدون محاسبه‌ی الماس و پیام</h1>
          <p className="m-0 max-w-[760px] text-base leading-8 text-fg-2">
            همه‌ی امکانات در همه‌ی پلن‌ها هست؛ پلن‌ها فقط در سقف ربات، مشتری و درخواست به ایجنت فرق دارند. صورت‌حساب هر ماه ثابت است و شگفتی ندارد.
          </p>
          {data?.prices_proposed && (
            <p className="m-0 w-fit rounded-xl border border-amber-line bg-saffron/10 px-3 py-2 text-sm text-amber-fg">
              قیمت‌ها <b>پیشنهادی</b> است و هنوز با صاحبان کسب‌وکار سنجیده نشده؛ ممکن است تغییر کند.
            </p>
          )}
        </div>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
          {data?.plans.map((p) => (
            <section key={p.key} className={`flex flex-col gap-3 rounded-[22px] border bg-panel p-5 ${p.key === "pro" ? "border-saffron" : "border-line-2"}`}>
              <h2 className="m-0 text-xl font-extrabold">{p.name}{p.key === "pro" && <span className="mr-2 rounded-full bg-saffron px-2 py-0.5 text-xs font-bold text-ink">محبوب</span>}</h2>
              <span className="text-sm text-mute">{p.tagline}</span>
              <div className="text-3xl font-black text-saffron">{p.price === 0 ? "رایگان" : <>{fa(p.price.toLocaleString("en-US"))} <span className="text-sm font-bold text-fg-2">تومان / ماه</span></>}</div>
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm leading-7">
                <li>✓ تا {fa(p.bots)} ربات، {fa(p.live_bots)} ربات هم‌زمان منتشرشده</li>
                <li>✓ تا {fa(p.customers.toLocaleString("en-US"))} مشتری فعال در ماه برای هر ربات</li>
                <li>✓ {fa(p.ai_requests.toLocaleString("en-US"))} درخواست به ایجنت در ماه (ساخت و تغییر ربات)</li>
              </ul>
              <Link href={loggedIn ? "/account/" : "/login/"} className={`mt-auto inline-flex min-h-11 items-center justify-center rounded-xl px-4 font-bold ${p.key === "free" ? "border border-line-2 hover:border-saffron" : "bg-saffron text-ink hover:bg-saffron-hi"}`}>
                {p.key === "free" ? "شروع رایگان" : data?.demo ? "ارتقا (پرداخت آزمایشی)" : "درخواست این پلن"}
              </Link>
            </section>
          ))}
        </div>
        <section className="flex flex-col gap-2 rounded-[22px] border border-line-2 bg-panel p-5">
          <h2 className="m-0 text-lg font-extrabold">در همه‌ی پلن‌ها</h2>
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm leading-7 text-fg-2">
            {data?.included.map((t) => <li key={t}>✓ {t}</li>)}
          </ul>
          <p className="m-0 mt-2 text-xs leading-6 text-dim">
            «در ماه» یعنی در ۳۰ روز گذشته. مشتری فعال یعنی کسی که در این مدت به ربات پیام داده؛ مشتری‌های قبلی هیچ‌وقت قطع نمی‌شوند و فقط پذیرش مشتری <i>جدید</i> بعد از پر شدن سقف متوقف می‌شود.
            {data?.demo ? "این نسخه‌ی نمایشی است: ارتقای پلن «پرداخت آزمایشی» است و هیچ پولی کسر نمی‌شود." : "ارتقا فعلاً با ثبت درخواست و تأیید تیم بات‌یار انجام می‌شود (پرداخت آنلاین اشتراک هنوز راه‌اندازی نشده)."}
          </p>
        </section>
      </main>
    </div>
  );
}
