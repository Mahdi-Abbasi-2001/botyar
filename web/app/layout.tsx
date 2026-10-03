import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const vazir = localFont({ src: "./fonts/Vazirmatn.woff2", variable: "--font-vazir", weight: "100 900", display: "swap" });

export const metadata: Metadata = {
  title: "بات‌یار | ساخت ربات بله با گفتگو",
  description: "ربات خود را به زبان فارسی توضیح دهید؛ ایجنت آن را می‌سازد، تست می‌کند و منتشر می‌کند.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className={vazir.variable}>
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
