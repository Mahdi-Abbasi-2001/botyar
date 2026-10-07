"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { BlueprintPreview, TypedRequest, useTyping } from "@/components/TypingHero";
import { Icon, Logo, fa } from "@/components/ui";
import { PublicActions } from "@/components/PublicActions";
import { useSignedIn } from "@/components/useSignedIn";
import { SAMPLE_REQUEST } from "@/components/TypingHero";
import { useReveal } from "@/components/useReveal";
import { PageTransition } from "@/components/PageTransition";

type Plan = { key: string; name: string; price: number; bots: number; live_bots: number; ai_requests: number; tagline: string };

const PROOF = [
  { name: "ثبت نوبت شنبه", lines: [["بیمار", "شنبه ساعت ۹ صبح"], ["ربات", "لطفاً نام و نام خانوادگی خود را بنویسید."], ["ربات", "نوبت شما ثبت شد."]] },
  { name: "شماره‌ی موبایل نامعتبر", lines: [["بیمار", "۱۲۳۴"], ["ربات", "شماره‌ی موبایل معتبر نیست. لطفاً آن را به شکل ۰۹۱۲۱۲۳۴۵۶۷ وارد کنید."]] },
];

type Feature = { icon: React.ComponentProps<typeof Icon>["name"]; title: string; text: string };
const FEATURE_GROUPS: { title: string; items: Feature[] }[] = [
  { title: "نوبت و سفارش", items: [
    { icon: "calendar", title: "نوبت‌دهی و کلاس هفتگی", text: "سانس با ظرفیت مشخص، تکرار هفتگی با تاریخ شمسی، و لیست انتظار برای وقتی که ظرفیت پر می‌شود." },
    { icon: "clock", title: "تقویم وقت‌دهی", text: "با تعیین ساعت کاری، مدت هر نوبت و زمان استراحت، وقت‌های خالی خودکار ساخته می‌شوند؛ برای هر همکار جداگانه." },
    { icon: "repeat", title: "لغو و تغییر زمان", text: "هر مشتری نوبت‌ها و سفارش‌های خودش را می‌بیند. اگر کسی لغو کند، جایش خودکار به نفر اول لیست انتظار می‌رسد." },
    { icon: "cart", title: "فروشگاه و منو", text: "دسته‌بندی، سایز و رنگ، موجودی انبار، سبد خرید، هزینه‌ی ارسال و کد تخفیف." },
    { icon: "file", title: "وارد کردن محصولات", text: "از فایل اکسل یا CSV، متن کپی‌شده یا حتی عکس فهرست قیمت. پیش از ذخیره، پیش‌نمایش را می‌بینید." },
    { icon: "card", title: "پرداخت آنلاین در بله", text: "صورت‌حساب داخل خود بله صادر می‌شود و مبلغ مستقیم به کیف پول شما می‌رود. سفارش‌های پرداخت‌نشده خودکار لغو می‌شوند." },
    { icon: "list", title: "مدیریت سفارش‌ها و خروجی", text: "تغییر وضعیت سفارش (در حال آماده‌سازی، آماده، تحویل‌شده)، لغو با ذکر دلیل، فهرست مشتریان و خروجی اکسل از همه‌ی ثبت‌ها." },
  ] },
  { title: "گفت‌وگو با مشتری", items: [
    { icon: "help", title: "پرسش‌های متداول", text: "مشتری سؤالش را با کلمات خودش می‌پرسد و همان پاسخی را می‌گیرد که شما نوشته‌اید. ربات از خودش جوابی نمی‌سازد." },
    { icon: "tree", title: "زیرمنو و آزمون", text: "منوهای چندسطحی برای کسب‌وکارهایی با خدمات متنوع، و آزمون چندگزینه‌ای با امتیاز و نتیجه." },
    { icon: "file", title: "عکس، فایل و موقعیت مکانی", text: "عکس منو، فایل PDF یا نشانی روی نقشه را همراه پیام‌های ربات بفرستید." },
    { icon: "star", title: "پیام به مدیر و نظرسنجی", text: "پیام مشتری به صندوق پیام پنل می‌رسد و پاسخ شما مستقیم در گفت‌وگوی او ارسال می‌شود. امتیازدهی ستاره‌ای و ثبت نظر هم دارد." },
    { icon: "bell", title: "یادآوری و اطلاع‌رسانی", text: "یادآوری خودکار پیش از نوبت، و اطلاعیه‌ی فوری یا زمان‌بندی‌شده برای همه‌ی مشتریان. هر مشتری می‌تواند دریافت اطلاعیه را لغو کند." },
  ] },
  { title: "کانال و گروه", items: [
    { icon: "lock", title: "عضویت اجباری در کانال", text: "ربات فقط به اعضای کانال شما پاسخ می‌دهد و از دیگران می‌خواهد ابتدا عضو شوند." },
    { icon: "chart", title: "لینک دعوت و رتبه‌بندی معرف‌ها", text: "هر کاربر لینک دعوت اختصاصی دارد. دعوت‌ها شمرده می‌شوند و معرف‌های برتر در جدول رتبه‌بندی می‌آیند." },
    { icon: "chat", title: "چت ناشناس", text: "گفت‌وگوی ناشناس میان کاربران ربات، همراه با گزارش تخلف و امکان مسدود کردن." },
    { icon: "shield", title: "مدیریت گروه و بازنشر خودکار", text: "حذف خودکار لینک‌ها و کلمه‌های ممنوع، اخطار و اخراج، و بازنشر پست‌ها میان کانال‌ها." },
  ] },
];

// a decorative 5×5 "QR" for the landing mock-up (real QR codes are generated in the publish tab)
const QR_DOTS = [1, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0, 1, 1].map(Boolean);

const PROOF_NUMBERS: [string, string][] = [
  ["۵۴", "درخواست فارسی متنوع در ارزیابی خودکار بات‌یار با مدل واقعی"],
  ["حدود ۰٫۰۰۲ دلار", "میانگین هزینه‌ی هوش مصنوعی برای ساخت یا تغییر هر ربات"],
  ["بیش از ۲۷۰", "تست خودکار برای موتور ربات‌ها و تک‌تک امکاناتش"],
  ["بدون هوش مصنوعی", "در پاسخ به پیام مشتری؛ پرسش‌های متداول فقط میان پاسخ‌هایی که خودتان نوشته‌اید جست‌وجو می‌شوند"],
];

// header links of the landing page → sections below; [id, label, breakpoint at which the link shows]
const SECTIONS: [string, string, string][] = [["features", "امکانات", "lg:inline"], ["proof", "تست خودکار", "lg:inline"], ["pricing", "تعرفه‌ها", "sm:inline"]];

/** Which of SECTIONS crosses the middle of the screen right now; null on the hero and on the sections in between. */
function useSectionInView() {
  const [here, setHere] = useState<string | null>(null);
  useEffect(() => {
    const check = () => {
      const mid = window.innerHeight / 2;
      const hit = SECTIONS.find(([id]) => {
        const r = document.getElementById(id)?.getBoundingClientRect();
        return r && r.top <= mid && r.bottom >= mid;
      });
      setHere(hit ? hit[0] : null);
    };
    // three position reads per scroll event are cheap; React skips the render when the answer is unchanged
    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => { window.removeEventListener("scroll", check); window.removeEventListener("resize", check); };
  }, []);
  return here;
}

function Kicker({ children, mint }: { children: React.ReactNode; mint?: boolean }) {
  return <span className={`text-sm font-bold ${mint ? "text-mint" : "text-saffron"}`}>{children}</span>;
}

export default function Home() {
  const n = useTyping();
  useReveal();
  const here = useSectionInView();
  const signedIn = useSignedIn();  // the header and every «start» button adapt: an owner goes to the dashboard, not the login page
  const [plans, setPlans] = useState<{ plans: Plan[]; prices_proposed: boolean } | null>(null);
  useEffect(() => {
    api<{ plans: Plan[]; prices_proposed: boolean }>("/plans").then(setPlans).catch(() => {});
  }, []);
  return (
    <PageTransition>
      <div className="bp min-h-screen px-4 sm:px-6">
        <header className="sticky top-0 z-30 -mx-4 border-b border-line/70 bg-ink/80 px-4 backdrop-blur-md sm:-mx-6 sm:px-6">
          <div className="mx-auto flex max-w-[1320px] items-center justify-between gap-3 py-3 sm:py-4">
            <Logo />
            <nav className="flex items-center gap-4 text-[15px] sm:gap-6">
              {/* all three jump to a section of this page, in page order; the one in view is marked */}
              {SECTIONS.map(([id, label, show]) => (
                <a key={id} href={`#${id}`} aria-current={here === id ? "location" : undefined}
                  className={`relative hidden py-1 ${show} after:absolute after:inset-x-0 after:-bottom-0.5 after:h-0.5 after:rounded-full after:bg-saffron after:transition-transform after:duration-300 ${here === id ? "text-fg after:scale-x-100" : "text-fg-2 after:scale-x-0 hover:text-fg"}`}>
                  {label}
                </a>
              ))}
              <span className="hidden h-5 w-px bg-line-2 sm:block" aria-hidden />
              <PublicActions signedIn={signedIn} />
            </nav>
          </div>
        </header>
        <div className="mx-auto flex max-w-[1320px] flex-col gap-24 pb-16 sm:gap-32">
          <div className="flex flex-col gap-10 pt-8 sm:pt-10">

            <section className="flex flex-wrap items-center gap-12">
              <div className="flex min-w-0 flex-[1_1_540px] flex-col gap-5">
                <span className="self-start rounded-full border border-line-2 px-3.5 py-1.5 text-[13px] text-fg-2">ساخت ربات بله و تلگرام با هوش مصنوعی</span>
                <h1 className="m-0 text-5xl font-black leading-[1.2] sm:text-[68px]">
                  ربات بله و تلگرام،<br /><span className="text-saffron">بدون یک خط کد.</span>
                </h1>
                <p className="m-0 max-w-[540px] text-lg leading-9 text-fg-2">
                  کافی است کار ربات را به فارسی توضیح دهید. بات‌یار آن را می‌سازد، مثل یک مشتری واقعی امتحانش می‌کند و فقط وقتی همه‌ی تست‌ها موفق باشند، آماده‌ی انتشار تحویلش می‌دهد.
                </p>
                <div className="flex flex-col gap-3.5 rounded-[20px] border border-line-2 bg-panel px-5 py-5">
                  <span className="text-[13px] text-mute">ربات شما قرار است چه کاری انجام دهد؟</span>
                  <TypedRequest n={n} />
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="text-[13px] text-dim">یک نمونه؛ بعد از ورود، توضیح خودتان را می‌نویسید</span>
                    <Link href={signedIn ? `/bots/?describe=${encodeURIComponent(SAMPLE_REQUEST)}` : "/login/"} className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-saffron px-5 font-extrabold text-ink hover:bg-saffron-hi">
                      ساخت همین ربات <Icon name="send" strokeWidth={2.4} />
                    </Link>
                  </div>
                </div>
              </div>
              <div className="min-w-0 flex-[1_1_480px]">
                <BlueprintPreview n={n} />
              </div>
            </section>
          </div>

          <section id="features" className="flex flex-col gap-7">
            <div data-reveal className="flex max-w-[760px] flex-col gap-2.5">
              <Kicker>۱ · امکانات</Kicker>
              <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">کارهای روزمره‌ی کسب‌وکارتان را به ربات بسپارید.</h2>
              <p className="m-0 text-[17px] leading-8 text-fg-2">لازم نیست نام این امکانات را بدانید. همان‌طور بنویسید که کاری را به یک همکار توضیح می‌دهید؛ بات‌یار امکان مناسب را خودش انتخاب می‌کند.</p>
            </div>
            {FEATURE_GROUPS.map((g) => (
              <div key={g.title} data-reveal className="flex flex-col gap-3">
                <h3 className="m-0 text-base font-extrabold text-fg-2">{g.title}</h3>
                <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fill,minmax(250px,1fr))]">
                  {g.items.map((f) => (
                    <div key={f.title} className="lift group flex flex-col gap-2 rounded-[18px] border border-line bg-panel p-[18px] hover:border-line-3">
                      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-raised text-saffron transition-colors duration-300 group-hover:bg-saffron/15"><Icon name={f.icon} size={20} /></span>
                      <span className="text-base font-extrabold">{f.title}</span>
                      <span className="text-sm leading-7 text-mute">{f.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </section>

          <section data-reveal id="proof" className="flex flex-col gap-7">
            <div className="flex max-w-[760px] flex-col gap-2.5">
              <Kicker mint>۲ · تست خودکار</Kicker>
              <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">هر ربات پیش از تحویل، تست می‌شود.</h2>
              <p className="m-0 text-[17px] leading-8 text-fg-2">بات‌یار برای هر ربات چند سناریو می‌نویسد و مثل یک مشتری واقعی با آن گفت‌وگو می‌کند. متن کامل هر تست را می‌توانید بخوانید.</p>
            </div>
            <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(280px,1fr))]">
              {PROOF.map((p) => (
                <div key={p.name} className="lift flex flex-col gap-2.5 rounded-[18px] border border-line bg-panel p-[18px]">
                  <div className="flex items-center justify-between"><span className="font-extrabold">{p.name}</span><PassTag /></div>
                  <div className="flex flex-col text-[13px] leading-8">
                    {p.lines.map(([who, line], i) => (
                      <span key={i}><span className={who === "بیمار" ? "text-saffron" : "text-mute"}>{who}:</span> {line}</span>
                    ))}
                  </div>
                </div>
              ))}
              <div className="lift flex flex-col gap-2.5 rounded-[18px] border border-mint bg-panel p-[18px]">
                <div className="flex items-center justify-between"><span className="font-extrabold">پر شدن ظرفیت</span><PassTag /></div>
                <p className="m-0 text-[13px] leading-8 text-mint-fg">بار اول ناموفق بود. بات‌یار پیش از رسیدن ربات به دست شما خطا را پیدا کرد، اصلاحش کرد و تست بار دوم موفق شد.</p>
              </div>
            </div>
          </section>

          <section data-reveal className="flex flex-wrap items-center gap-12">
            <div className="flex flex-[1_1_420px] flex-col gap-2.5">
              <Kicker>۳ · تغییر بدون نگرانی</Kicker>
              <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">هر تغییر با همه‌ی تست‌های قبلی سنجیده می‌شود.</h2>
              <p className="m-0 text-[17px] leading-8 text-fg-2">تغییر را در یک جمله بنویسید. بات‌یار به زبان ساده نشان می‌دهد دقیقاً چه چیزی عوض شده و هر نسخه را همراه با نتیجه‌ی تست‌هایش نگه می‌دارد.</p>
            </div>
            <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-3 rounded-[20px] border border-line bg-panel p-5">
              <span className="rounded-xl bg-raised px-3.5 py-2.5 text-[15px] leading-8">«وقتی ظرفیت پر شد، بیمار بتونه تو لیست انتظار ثبت‌نام کنه»</span>
              <div className="flex flex-wrap items-center gap-2.5 text-[15px]">
                <span className="font-bold">لیست انتظار</span>
                <span className="mr-auto text-mute line-through">غیرفعال</span>
                <span className="text-saffron">←</span>
                <span className="rounded-md bg-mint px-2.5 py-0.5 font-extrabold text-ink">فعال</span>
              </div>
              <div className="grid grid-cols-6 gap-1">
                {[0, 1, 2, 3, 4, 5].map((i) => <span key={i} className={`h-2 rounded ${i < 5 ? "bg-mint" : "bg-fg"}`} />)}
              </div>
              <span className="text-[13px] text-mint-fg">۵ تست قبلی موفق · ۱ تست جدید موفق · نسخه‌ی ۲ ذخیره شد</span>
            </div>
          </section>

          <section data-reveal className="flex flex-wrap items-center gap-12">
            <div className="flex flex-[1_1_420px] flex-col gap-2.5">
              <Kicker mint>۴ · انتشار در بله و تلگرام</Kicker>
              <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">نسخه‌ی تست‌شده را با یک دکمه منتشر کنید.</h2>
              <p className="m-0 text-[17px] leading-8 text-fg-2">
                یک لینک و یک کد QR دریافت می‌کنید تا در اینستاگرام، روی ویترین یا کنار صندوق بگذارید؛ مشتری با باز کردن آن مستقیم وارد ربات شما می‌شود.
                ربات می‌تواند نام و تصویر اختصاصی خودتان را داشته باشد، یا بدون هیچ تنظیمی روی <span dir="ltr" className="font-bold text-fg">@botyar_ai_bot</span> اجرا شود. انتشار در تلگرام هم ممکن است.
                نوبت‌ها و سفارش‌های تازه همان لحظه در پنل و در بله به دستتان می‌رسد.
              </p>
              <p className="m-0 flex items-center gap-2 text-sm text-mute"><Icon name="lock" size={16} className="text-mint" /> تا وقتی حتی یک تست ناموفق باشد، دکمه‌ی انتشار غیرفعال است.</p>
            </div>
            <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-2.5 rounded-[20px] border border-line bg-panel p-5 text-sm">
              <div className="flex items-center gap-3 border-b border-line pb-3">
                <span aria-hidden className="grid h-14 w-14 shrink-0 grid-cols-5 gap-0.5 rounded-lg bg-white p-1.5">
                  {QR_DOTS.map((on, i) => <span key={i} className={on ? "bg-ink" : ""} />)}
                </span>
                <span className="flex flex-col gap-0.5">
                  <span className="font-bold">لینک ربات کلینیک</span>
                  <span className="text-[13px] text-mute" dir="ltr">ble.ir/…?start=…</span>
                </span>
                <span className="mr-auto rounded-full bg-mint-bg px-2.5 py-1 text-xs text-mint-fg">ورود مستقیم</span>
              </div>
              <span className="self-start rounded-[14px_14px_14px_4px] bg-raised px-3 py-2">سلام! به کلینیک دندانپزشکی خوش آمدید.</span>
              <span className="self-start rounded-[10px] border border-line-3 px-3 py-2">دریافت نوبت</span>
              <span className="flex items-center gap-2 self-stretch rounded-xl border border-amber-line bg-amber-bg px-3 py-2 text-amber-fg"><Icon name="bell" size={16} /> پیام به شما: نوبت جدید، دوشنبه ساعت ۵ عصر</span>
            </div>
          </section>

          <section data-reveal className="flex flex-wrap items-center gap-12 rounded-[24px] border border-mint-line bg-mint-bg/40 p-6 sm:p-10">
            <div className="flex flex-[1_1_440px] flex-col gap-2.5">
              <Kicker mint>۵ · پاسخ‌های قابل پیش‌بینی</Kicker>
              <h2 className="m-0 text-3xl font-black leading-snug sm:text-[40px]">هوش مصنوعی ربات را می‌سازد، اما به مشتری پاسخ نمی‌دهد.</h2>
              <p className="m-0 text-[17px] leading-8 text-fg-2">
                بات‌یار فقط طرح دقیق ربات را می‌نویسد و پیام‌های مشتری را یک موتور ثابت پاسخ می‌دهد. به همین دلیل ربات همیشه یک‌جور رفتار می‌کند،
                حرفی خارج از نوشته‌های شما نمی‌زند، با ترفندهای کلامی فریب نمی‌خورد و هزینه‌ی هر پیام تقریباً صفر است.
              </p>
            </div>
            <div className="grid flex-[1_1_440px] grid-cols-2 gap-3">
              {PROOF_NUMBERS.map(([big, label]) => (
                <div key={label} className="flex flex-col gap-1 rounded-2xl border border-line bg-panel p-4">
                  <span className="text-[28px] font-black text-mint">{big}</span>
                  <span className="text-[13px] leading-6 text-fg-2">{label}</span>
                </div>
              ))}
              <span className="col-span-2 text-xs text-dim">این اعداد از ارزیابی‌ها و تست‌های خود ما به دست آمده‌اند؛ رفتار هوش مصنوعی ممکن است در هر اجرا کمی متفاوت باشد.</span>
            </div>
          </section>

          <section data-reveal id="pricing" className="flex flex-col gap-6">
            <div className="flex max-w-[760px] flex-col gap-2.5">
              <Kicker>۶ · تعرفه</Kicker>
              <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">مبلغ ثابت ماهانه، با همه‌ی امکانات در همه‌ی پلن‌ها.</h2>
              <p className="m-0 text-[17px] leading-8 text-fg-2">تفاوت پلن‌ها فقط در تعداد ربات، تعداد مشتری و تعداد درخواست ساخت و تغییر است. مبلغ صورت‌حساب هر ماه از پیش مشخص است.</p>
            </div>
            {plans && (
              <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(190px,1fr))]">
                {plans.plans.map((pl) => (
                  <div key={pl.key} className={`lift flex flex-col gap-1.5 rounded-[18px] border bg-panel p-4 ${pl.key === "pro" ? "border-saffron" : "border-line"}`}>
                    <span className="font-extrabold">{pl.name}</span>
                    <span className="text-2xl font-black text-saffron">{fa(pl.price.toLocaleString("en-US"))} <span className="text-xs font-bold text-fg-2">تومان / ماه</span></span>
                    <span className="text-xs leading-6 text-mute">{fa(pl.bots)} ربات · {fa(pl.live_bots)} ربات منتشرشده · {fa(pl.ai_requests.toLocaleString("en-US"))} درخواست ساخت و تغییر در ماه</span>
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-4">
              <Link href="/pricing/" className="inline-flex min-h-11 items-center rounded-xl border border-line-2 px-4 font-bold hover:border-saffron">مقایسه‌ی کامل پلن‌ها</Link>
              {plans?.prices_proposed && <span className="text-sm text-amber-fg">این قیمت‌ها پیشنهادی‌اند و هنوز با نظر صاحبان کسب‌وکار سنجیده نشده‌اند.</span>}
            </div>
          </section>

          <section data-reveal className="flex flex-col items-center gap-5 border-t border-line pt-16 text-center">
            {signedIn ? (
              <>
                <h2 className="m-0 text-4xl font-black leading-snug sm:text-[52px]">ربات بعدی خود را بسازید.</h2>
                <Link href="/bots/" className="inline-flex min-h-13 items-center rounded-xl bg-saffron px-6 text-[17px] font-extrabold text-ink hover:bg-saffron-hi">ساخت ربات جدید</Link>
              </>
            ) : (
              <>
                <h2 className="m-0 text-4xl font-black leading-snug sm:text-[52px]">اولین ربات خود را همین حالا بسازید.</h2>
                <div className="flex flex-wrap justify-center gap-3">
                  <Link href="/login/" className="inline-flex min-h-13 items-center rounded-xl bg-saffron px-6 text-[17px] font-extrabold text-ink hover:bg-saffron-hi">شروع رایگان</Link>
                  <Link href="/login/" className="inline-flex min-h-13 items-center rounded-xl border border-line-2 bg-panel px-5 hover:border-line-3">شروع از یک نمونه</Link>
                </div>
                <span className="text-sm text-mute">برای ساخت ربات به کارت بانکی نیازی نیست؛ هزینه‌ی هوش مصنوعی هر ساخت را هم شفاف می‌بینید.</span>
              </>
            )}
          </section>
        </div>
      </div>
    </PageTransition>
  );
}

function PassTag() {
  return <span className="-rotate-[4deg] rounded-md border-2 border-mint px-2 text-[13px] font-black text-mint">قبول</span>;
}
