import Link from "next/link";

const steps = [
  ["۱", "توضیح بدهید", "نیازتان را به فارسی ساده بنویسید؛ ایجنت ابهام‌ها را می‌پرسد."],
  ["۲", "ایجنت می‌سازد", "رفتار ربات به‌صورت یک مشخصات ساخت‌یافته طراحی و اعتبارسنجی می‌شود."],
  ["۳", "خودش تست می‌کند", "سناریوهای آزمایشی اجرا می‌شود و خطاها پیش از انتشار اصلاح می‌شوند."],
  ["۴", "منتشر و نگهداری", "ربات روی بله فعال می‌شود و هر تغییر با گفتگو اعمال و دوباره تست می‌شود."],
];

export default function Home() {
  return (
    <main>
      <header className="mx-auto flex max-w-5xl items-center justify-between px-5 py-5">
        <span className="text-xl font-extrabold text-indigo-700">بات‌ساز</span>
        <Link href="/login/" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">
          ورود / ثبت‌نام
        </Link>
      </header>
      <section className="mx-auto max-w-3xl px-5 pb-16 pt-14 text-center">
        <h1 className="text-4xl font-extrabold leading-snug sm:text-5xl">
          ربات بله‌ات را <span className="text-indigo-600">توضیح بده</span>،
          <br />
          بقیه‌اش با ایجنت.
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-lg leading-8 text-slate-600">
          کارگاه، کافه یا کلینیک دارید؟ در چند دقیقه یک ربات رزرو یا سفارش بگیرید؛ ساخته‌شده، تست‌شده و آماده انتشار.
        </p>
        <Link href="/login/" className="mt-8 inline-block rounded-xl bg-indigo-600 px-8 py-3 text-lg font-bold text-white shadow-lg shadow-indigo-200 hover:bg-indigo-700">
          شروع رایگان
        </Link>
      </section>
      <section className="mx-auto grid max-w-5xl gap-4 px-5 pb-20 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map(([n, t, d]) => (
          <div key={n} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 font-bold text-indigo-700">{n}</div>
            <h3 className="mb-1 font-bold">{t}</h3>
            <p className="text-sm leading-6 text-slate-600">{d}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
