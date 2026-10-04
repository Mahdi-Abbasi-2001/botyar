"use client";
import Link from "next/link";
import { BlueprintPreview, TypedRequest, useTyping } from "@/components/TypingHero";
import { Icon, Logo } from "@/components/ui";

const PROOF = [
  { name: "ثبت موفق نوبت شنبه", lines: [["بیمار", "شنبه ساعت ۹ صبح"], ["ربات", "نام و نام خانوادگی؟"], ["ربات", "نوبت شما ثبت شد."]] },
  { name: "رد موبایل نامعتبر", lines: [["بیمار", "۱۲۳۴"], ["ربات", "شماره معتبر نیست. مثل ۰۹۱۲۱۲۳۴۵۶۷ وارد کنید."]] },
];

const FEATURES: { icon: React.ComponentProps<typeof Icon>["name"]; title: string; text: string }[] = [
  { icon: "calendar", title: "نوبت‌دهی و کلاس هفتگی", text: "سانس با ظرفیت، تکرار هر هفته با تاریخ شمسی، و لیست انتظار وقتی جا پر شد." },
  { icon: "clock", title: "تقویم وقت‌دهی", text: "از ساعت کاری، مدت هر نوبت و وقت ناهار، زمان‌ها خودش ساخته می‌شود؛ برای هر همکار جدا." },
  { icon: "cart", title: "فروشگاه و منو", text: "دسته‌بندی، سایز و رنگ، موجودی، سبد خرید، هزینه‌ی ارسال و کد تخفیف." },
  { icon: "file", title: "ورود محصولات", text: "فایل اکسل، CSV، متن کپی‌شده یا حتی عکس لیست قیمت؛ اول پیش‌نمایش، بعد ذخیره." },
  { icon: "card", title: "پرداخت آنلاین در بله", text: "فاکتور پرداخت داخل خود بله؛ سفارش پرداخت‌نشده بعد از چند دقیقه خودش لغو می‌شود." },
  { icon: "help", title: "پرسش‌های متداول", text: "مشتری به زبان خودش می‌پرسد؛ جواب، همان جمله‌ای است که خودت نوشتی. چیزی از خودش نمی‌سازد." },
  { icon: "repeat", title: "لغو و تغییر زمان", text: "«ثبت‌های من» برای هر مشتری؛ جای آزادشده خودکار به نفر اول لیست انتظار می‌رسد." },
  { icon: "bell", title: "یادآوری و اطلاعیه", text: "یادآوری پیش از نوبت، و اطلاعیه برای همه‌ی مشتری‌ها با امکان لغو دریافت." },
  { icon: "star", title: "پیام به مدیر و نظر مشتری", text: "پیام‌های مشتری در صندوق پنل، جوابت مستقیم در چت او؛ امتیاز ستاره‌ای و نظر." },
  { icon: "chart", title: "مدیریت و خروجی", text: "لغو با دلیل، وضعیت سفارش (آماده‌سازی، آماده، تحویل) و خروجی اکسل از همه‌ی ثبت‌ها." },
];

const PROOF_NUMBERS: [string, string][] = [
  ["۸ از ۸", "درخواست متنوع به ربات کامل و تست‌شده رسید"],
  ["۱۲ تا ۴۳ ثانیه", "از پیام صاحب کسب‌وکار تا ربات آماده"],
  ["حدود ۰٫۰۰۲ دلار", "میانگین هزینه‌ی هوش مصنوعی برای ساخت یک ربات"],
  ["بدون مدل زبانی", "جواب پیام‌های مشتری؛ پرسش متداول فقط بین جمله‌های خودت جست‌وجو می‌شود"],
];

function Kicker({ children, mint }: { children: React.ReactNode; mint?: boolean }) {
  return <span className={`text-sm font-bold ${mint ? "text-mint" : "text-saffron"}`}>{children}</span>;
}

export default function Home() {
  const n = useTyping();
  return (
    <div className="bp min-h-screen px-4 sm:px-6">
      <div className="mx-auto flex max-w-[1320px] flex-col gap-24 pb-16 sm:gap-32">
        <div className="flex flex-col gap-10">
          <header className="flex flex-wrap items-center justify-between gap-4 py-6">
            <Logo />
            <nav className="flex flex-wrap items-center gap-6 text-[15px]">
              <a href="#features" className="hidden text-fg-2 hover:text-fg sm:inline">چه کارهایی بلد است؟</a>
              <a href="#proof" className="hidden text-fg-2 hover:text-fg sm:inline">چطور مطمئن شوم؟</a>
              <Link href="/login/?mode=login" className="text-fg-2 hover:text-fg">ورود</Link>
              <Link href="/login/" className="inline-flex min-h-11 items-center rounded-xl bg-fg px-5 font-bold text-ink hover:bg-white">ساخت اولین ربات</Link>
            </nav>
          </header>

          <section className="flex flex-wrap items-start gap-12">
            <div className="flex min-w-0 flex-[1_1_540px] flex-col gap-5">
              <span className="self-start rounded-full border border-line-2 px-3.5 py-1.5 text-[13px] text-fg-2">ایجنت ربات‌ساز برای پیام‌رسان بله</span>
              <h1 className="m-0 text-5xl font-black leading-[1.2] sm:text-[68px]">
                بگو چی می‌خوای،<br />ربات رو <span className="text-saffron">می‌سازم.</span>
              </h1>
              <p className="m-0 max-w-[540px] text-lg leading-9 text-fg-2">
                به فارسی بنویس. هر جمله‌ات یک تکه از ربات می‌شود، ایجنت خودش تستش می‌کند و فقط وقتی همه‌ی تست‌ها قبول شد تحویلش می‌دهد.
              </p>
              <div className="flex flex-col gap-3.5 rounded-[20px] border border-line-2 bg-panel px-5 py-5">
                <span className="text-[13px] text-mute">ربات‌ت چه کاری انجام بدهد؟</span>
                <TypedRequest n={n} />
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="text-[13px] text-dim">نمونه · بعد از ورود، خودت می‌نویسی</span>
                  <Link href="/login/" className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-saffron px-5 font-extrabold text-ink hover:bg-saffron-hi">
                    همین را بساز <Icon name="send" strokeWidth={2.4} />
                  </Link>
                </div>
              </div>
            </div>
            <div className="min-w-0 flex-[1_1_480px] pt-2">
              <BlueprintPreview n={n} />
            </div>
          </section>
        </div>

        <section id="proof" className="flex flex-col gap-7">
          <div className="flex max-w-[760px] flex-col gap-2.5">
            <Kicker mint>۱ · مدرک، نه قول</Kicker>
            <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">ربات قبل از این‌که به دستت برسد، امتحان پس می‌دهد.</h2>
            <p className="m-0 text-[17px] leading-8 text-fg-2">ایجنت مثل یک مشتری واقعی با ربات حرف می‌زند. هر تست، همان گفت‌وگویی است که اتفاق افتاد؛ می‌توانی بخوانی‌اش.</p>
          </div>
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(280px,1fr))]">
            {PROOF.map((p) => (
              <div key={p.name} className="flex flex-col gap-2.5 rounded-[18px] border border-line bg-panel p-[18px]">
                <div className="flex items-center justify-between"><span className="font-extrabold">{p.name}</span><PassTag /></div>
                <div className="flex flex-col text-[13px] leading-8">
                  {p.lines.map(([who, line], i) => (
                    <span key={i}><span className={who === "بیمار" ? "text-saffron" : "text-mute"}>{who}:</span> {line}</span>
                  ))}
                </div>
              </div>
            ))}
            <div className="flex flex-col gap-2.5 rounded-[18px] border border-mint bg-panel p-[18px]">
              <div className="flex items-center justify-between"><span className="font-extrabold">ظرفیت تکمیل‌شده</span><PassTag /></div>
              <p className="m-0 text-[13px] leading-8 text-mint-fg">اجرای اول رد شد. ایجنت پیش از تو خطا را پیدا کرد، اصلاحش کرد و دوباره اجرا کرد.</p>
            </div>
          </div>
        </section>

        <section className="flex flex-wrap items-center gap-12">
          <div className="flex flex-[1_1_420px] flex-col gap-2.5">
            <Kicker>۲ · تغییر بده، چیزی نشکند</Kicker>
            <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">یک جمله برای تغییر. همه‌ی تست‌های قبلی دوباره.</h2>
            <p className="m-0 text-[17px] leading-8 text-fg-2">می‌بینی دقیقاً چه چیزی عوض شد، به زبان آدمیزاد. هر نسخه با نتیجه‌ی تست‌هایش نگه داشته می‌شود.</p>
          </div>
          <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-3 rounded-[20px] border border-line bg-panel p-5">
            <span className="rounded-xl bg-raised px-3.5 py-2.5 text-[15px] leading-8">«وقتی ظرفیت پر شد، بیمار بتونه تو لیست انتظار ثبت بشه»</span>
            <div className="flex flex-wrap items-center gap-2.5 text-[15px]">
              <span className="font-bold">لیست انتظار</span>
              <span className="mr-auto text-mute line-through">غیرفعال</span>
              <span className="text-saffron">←</span>
              <span className="rounded-md bg-mint px-2.5 py-0.5 font-extrabold text-ink">فعال</span>
            </div>
            <div className="grid grid-cols-6 gap-1">
              {[0, 1, 2, 3, 4, 5].map((i) => <span key={i} className={`h-2 rounded ${i < 5 ? "bg-mint" : "bg-fg"}`} />)}
            </div>
            <span className="text-[13px] text-mint-fg">۵ تست قدیمی سالم · ۱ تست جدید قبول · نسخه‌ی تازه ذخیره شد</span>
          </div>
        </section>

        <section className="flex flex-wrap items-center gap-12">
          <div className="flex flex-[1_1_420px] flex-col gap-2.5">
            <Kicker mint>۳ · روی بله، همین امروز</Kicker>
            <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">نسخه‌ی تست‌شده با یک دکمه به دست مشتری‌ها می‌رسد.</h2>
            <p className="m-0 text-[17px] leading-8 text-fg-2">
              ساده‌ترین راه: مشتری‌ها ربات مشترک <span dir="ltr" className="font-bold text-fg">@botyar_ai_bot</span> را در بله باز می‌کنند و کد ۶حرفی ربات تو را می‌فرستند.
              یا توکن ربات خودت را بگذار تا با اسم و عکس خودت جواب بدهد. نوبت‌ها و سفارش‌ها همان لحظه در پنل و در چت بله‌ی خودت می‌رسند.
            </p>
            <p className="m-0 flex items-center gap-2 text-sm text-mute"><Icon name="lock" size={16} className="text-mint" /> تا وقتی حتی یک تست رد شده باشد، انتشار قفل است.</p>
          </div>
          <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-2.5 rounded-[20px] border border-line bg-panel p-5 text-sm">
            <span className="flex items-center gap-2 border-b border-line pb-2.5 text-[13px] text-mute"><span className="h-2 w-2 rounded-full bg-mint" />بله · <span dir="ltr">@botyar_ai_bot</span></span>
            <span className="self-end rounded-[14px_14px_4px_14px] bg-saffron px-3 py-2 text-ink" dir="ltr">/start</span>
            <span className="self-start rounded-[14px_14px_14px_4px] bg-raised px-3 py-2">سلام! برای شروع، «کد ربات» را بفرستید.</span>
            <span className="self-end rounded-[14px_14px_4px_14px] bg-saffron px-3 py-2 font-bold tracking-widest text-ink" dir="ltr">K7M2QX</span>
            <span className="self-start rounded-[14px_14px_14px_4px] bg-raised px-3 py-2">سلام! به کلینیک دندانپزشکی خوش آمدید.</span>
            <span className="self-start rounded-[10px] border border-line-3 px-3 py-2">دریافت نوبت</span>
            <span className="flex items-center gap-2 self-stretch rounded-xl border border-amber-line bg-amber-bg px-3 py-2 text-amber-fg"><Icon name="bell" size={16} /> برای تو: نوبت جدید · دوشنبه ۵ عصر</span>
          </div>
        </section>

        <section id="features" className="flex flex-col gap-7">
          <div className="flex max-w-[760px] flex-col gap-2.5">
            <Kicker>۴ · بیشتر از یک ربات جواب‌گو</Kicker>
            <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">کارهای روزمره‌ی کسب‌وکارت را بگو؛ ربات بلدش است.</h2>
            <p className="m-0 text-[17px] leading-8 text-fg-2">لازم نیست اسم این‌ها را بدانی. همان‌طور که برای یک همکار توضیح می‌دهی بنویس؛ ایجنت بخش درست را انتخاب می‌کند.</p>
          </div>
          <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fill,minmax(250px,1fr))]">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex flex-col gap-2 rounded-[18px] border border-line bg-panel p-[18px]">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-raised text-saffron"><Icon name={f.icon} size={20} /></span>
                <span className="text-base font-extrabold">{f.title}</span>
                <span className="text-sm leading-7 text-mute">{f.text}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="flex flex-wrap items-center gap-12 rounded-[24px] border border-mint-line bg-mint-bg/40 p-6 sm:p-10">
          <div className="flex flex-[1_1_440px] flex-col gap-2.5">
            <Kicker mint>۵ · مشتری با هوش مصنوعی حرف نمی‌زند</Kicker>
            <h2 className="m-0 text-3xl font-black leading-snug sm:text-[40px]">هوش مصنوعی ربات را می‌سازد؛ جواب مشتری را نه.</h2>
            <p className="m-0 text-[17px] leading-8 text-fg-2">
              ایجنت فقط یک نقشه‌ی دقیق از ربات می‌نویسد. پیام‌های مشتری را یک موتور ثابت جواب می‌دهد: هر بار همان رفتار، بدون حرف ساختگی،
              بدون امکان فریب‌دادن ربات، و تقریباً بدون هزینه برای هر پیام.
            </p>
          </div>
          <div className="grid flex-[1_1_440px] grid-cols-2 gap-3">
            {PROOF_NUMBERS.map(([big, label]) => (
              <div key={label} className="flex flex-col gap-1 rounded-2xl border border-line bg-panel p-4">
                <span className="text-[28px] font-black text-mint">{big}</span>
                <span className="text-[13px] leading-6 text-fg-2">{label}</span>
              </div>
            ))}
            <span className="col-span-2 text-xs text-dim">اعداد از ارزیابی خودمان روی ۸ درخواست متنوع؛ هر بار اجرا کمی فرق می‌کند.</span>
          </div>
        </section>

        <section className="flex flex-col items-center gap-5 border-t border-line pt-16 text-center">
          <h2 className="m-0 text-4xl font-black leading-snug sm:text-[52px]">ربات اولت را همین الان بساز.</h2>
          <div className="flex flex-wrap justify-center gap-3">
            <Link href="/login/" className="inline-flex min-h-13 items-center rounded-xl bg-saffron px-6 text-[17px] font-extrabold text-ink hover:bg-saffron-hi">با توضیح دادن شروع کن</Link>
            <Link href="/login/" className="inline-flex min-h-13 items-center rounded-xl border border-line-2 bg-panel px-5 hover:border-line-3">از یک نمونه شروع کن</Link>
          </div>
          <span className="text-sm text-mute">هزینه‌ی هوش مصنوعی هر ساخت را شفاف می‌بینی.</span>
        </section>
      </div>
    </div>
  );
}

function PassTag() {
  return <span className="-rotate-[4deg] rounded-md border-2 border-mint px-2 text-[13px] font-black text-mint">قبول</span>;
}
