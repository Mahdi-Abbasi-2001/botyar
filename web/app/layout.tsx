import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const vazir = localFont({ src: "./fonts/Vazirmatn.woff2", variable: "--font-vazir", weight: "100 900", display: "swap" });

export const metadata: Metadata = {
  title: "بات‌یار | ساخت ربات بله و تلگرام بدون کدنویسی",
  description: "کار ربات را به فارسی توضیح دهید؛ بات‌یار آن را می‌سازد، تست می‌کند و در بله و تلگرام منتشر می‌کند.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className={vazir.variable}>
      <body className="min-h-screen bg-ink text-fg antialiased">{children}</body>
    </html>
  );
}
