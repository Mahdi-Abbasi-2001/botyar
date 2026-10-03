import Link from "next/link";
import { Logo } from "@/components/ui";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-6 text-center">
      <Logo />
      <div className="text-6xl font-black text-saffron" aria-hidden>۴۰۴</div>
      <h1 className="text-2xl font-extrabold">این صفحه پیدا نشد</h1>
      <p className="max-w-sm leading-8 text-mute">شاید نشانی را اشتباه وارد کرده‌اید یا صفحه جابه‌جا شده است.</p>
      <div className="flex flex-wrap justify-center gap-3">
        <Link href="/bots/" className="min-h-11 rounded-xl bg-saffron px-6 py-2.5 font-bold text-ink">ربات‌های من</Link>
        <Link href="/" className="min-h-11 rounded-xl border border-line-2 px-6 py-2.5">صفحه‌ی اصلی</Link>
      </div>
    </main>
  );
}
