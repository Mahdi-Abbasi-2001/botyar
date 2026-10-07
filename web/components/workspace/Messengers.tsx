"use client";
import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";

/** Each messenger keeps its own look in the publish tab: logo tile, accent colour and tinted header. */
export type Platform = "bale" | "telegram";

export const BRAND: Record<Platform, { name: string; accent: string; deep: string }> = {
  bale: { name: "بله", accent: "#44D9AB", deep: "#2A8C80" },
  telegram: { name: "تلگرام", accent: "#2AABEE", deep: "#1C8ACB" },
};

/** Bale: the speech-bubble check mark, mint to indigo gradient. */
export function BaleLogo({ size = 44 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 512 512" role="img" aria-label="بله" className="shrink-0">
      <defs><linearGradient id="bale-g" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#4EEBB4" /><stop offset="1" stopColor="#2A2468" /></linearGradient></defs>
      <path d="M0 256V34Q0 -2 30 6L105 48A256 256 0 1 1 0 256Z" fill="url(#bale-g)" />
      <path d="M140 248 222 326 376 176" fill="none" stroke="#fff" strokeWidth="88" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Telegram: blue circle with the white paper plane. */
export function TelegramLogo({ size = 44 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" role="img" aria-label="تلگرام" className="shrink-0">
      <defs><linearGradient id="tg-g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#37BBFE" /><stop offset="1" stopColor="#007DBB" /></linearGradient></defs>
      <circle cx="24" cy="24" r="24" fill="url(#tg-g)" />
      <path d="M10.800 23.700c7-3.050 11.700-5.060 14-6.030 6.670-2.770 8.050-3.250 8.950-3.270.2 0 .64.050.93.290.24.200.3.470.34.660.03.190.07.620.04.960-.36 3.790-1.920 13-2.720 17.250-.34 1.800-1 2.400-1.640 2.460-1.390.13-2.440-.92-3.790-1.800-2.110-1.380-3.300-2.240-5.350-3.590-2.370-1.560-.83-2.420.52-3.820.35-.37 6.480-5.940 6.600-6.450.01-.06.030-.3-.11-.43-.14-.13-.35-.08-.5-.05-.21.050-3.590 2.280-10.140 6.700-.96.660-1.830.98-2.610.96-.86-.02-2.510-.49-3.740-.89-1.510-.49-2.710-.75-2.600-1.580.05-.43.650-.88 1.790-1.340z" fill="#fff" />
    </svg>
  );
}

export const Logo = ({ p, size }: { p: Platform; size?: number }) => (p === "bale" ? <BaleLogo size={size} /> : <TelegramLogo size={size} />);

const vars = (p: Platform) => ({ "--brand": BRAND[p].accent, "--brand-deep": BRAND[p].deep }) as CSSProperties;

/** The card of one messenger: tinted header with the logo, a status pill, then the content. */
export function PlatformCard({ p, title, lead, status, action, children }: { p: Platform; title: string; lead?: string; status?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return (
    <section style={vars(p)} className="overflow-hidden rounded-2xl border border-[color-mix(in_srgb,var(--brand)_35%,var(--color-line-2))] bg-panel">
      <header className="flex flex-wrap items-center gap-3 border-b border-[color-mix(in_srgb,var(--brand)_25%,var(--color-line-2))] bg-[linear-gradient(90deg,color-mix(in_srgb,var(--brand)_16%,transparent),transparent_75%)] px-4 py-3">
        <Logo p={p} />
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-extrabold leading-7">{title}</h3>
          {lead && <p className="text-sm leading-6 text-mute">{lead}</p>}
        </div>
        {status}
        {action}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function StatusPill({ on, children }: { on: boolean; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold ${on ? "border-[color-mix(in_srgb,var(--brand)_55%,transparent)] bg-[color-mix(in_srgb,var(--brand)_16%,transparent)] text-fg" : "border-line-2 text-mute"}`}>
      <span className={`size-2 rounded-full ${on ? "bg-[var(--brand)]" : "bg-dim"}`} />{children}
    </span>
  );
}

/** One way to publish (shared bot / own bot): a radio-style tile in the messenger's colour. */
export function ModeTile({ selected, onClick, title, text, badge }: { selected: boolean; onClick: () => void; title: string; text: ReactNode; badge?: string }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={selected}
      className={`flex gap-3 rounded-xl border p-4 text-right transition-colors ${selected ? "border-[var(--brand)] bg-[color-mix(in_srgb,var(--brand)_10%,transparent)]" : "border-line-2 hover:border-line-3"}`}>
      <span className={`mt-1 grid size-5 shrink-0 place-items-center rounded-full border-2 ${selected ? "border-[var(--brand)]" : "border-line-3"}`}>{selected && <span className="size-2.5 rounded-full bg-[var(--brand)]" />}</span>
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-2 font-bold">{title}{badge && <span className="rounded-full bg-[color-mix(in_srgb,var(--brand)_20%,transparent)] px-2 py-0.5 text-xs font-bold">{badge}</span>}</span>
        <span className="mt-1 block text-sm leading-6 text-mute">{text}</span>
      </span>
    </button>
  );
}

/** The main action in the messenger's own colour. */
export function BrandButton({ className = "", ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...rest} className={`min-h-11 rounded-xl bg-[var(--brand-deep)] px-5 font-bold text-white hover:brightness-110 disabled:opacity-50 ${className}`} />;
}

/** Three steps to a bot of one's own, with the token field: the same for both messengers. */
export function OwnBotSetup({ p, token, setToken }: { p: Platform; token: string; setToken: (v: string) => void }) {
  const father = p === "bale" ? "@botfather" : "@BotFather";
  const steps: ReactNode[] = [
    <>در {BRAND[p].name} به <b dir="ltr">{father}</b> پیام بدهید و <b dir="ltr">/newbot</b> را بفرستید.</>,
    <>یک نام برای ربات و یک نام کاربری انتخاب کنید (نام کاربری باید به <span dir="ltr">bot</span> ختم شود).</>,
    <>توکنی که <span dir="ltr">{father}</span> می‌فرستد را کپی کنید و در کادر زیر بگذارید.</>,
  ];
  return (
    <div className="mb-4 rounded-xl border border-line-2 bg-ink-2 p-4" style={vars(p)}>
      <ol className="mb-3 flex flex-col gap-2 text-sm leading-7">
        {steps.map((t, i) => (
          <li key={i} className="flex items-start gap-3">
            <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-[var(--brand-deep)] text-xs font-black text-white">{"۱۲۳"[i]}</span>
            <span>{t}</span>
          </li>
        ))}
      </ol>
      <label className="block text-sm">
        <span className="mb-1 block text-mute">توکن ربات (محرمانه است و به‌صورت رمزنگاری‌شده ذخیره می‌شود)</span>
        <input dir="ltr" value={token} onChange={(e) => setToken(e.target.value)} placeholder={p === "bale" ? "123456789:ABC…" : "123456789:AA…"} autoComplete="off"
          className="min-h-11 w-full rounded-xl border border-line-2 bg-ink px-3 text-left outline-none focus:border-[var(--brand)]" />
      </label>
    </div>
  );
}

/** Published with the shared Bot-yar bot (a trial): move to a bot of one's own, keeping every record and customer. */
export function SwitchToOwn({ p, busy, token, setToken, onSwitch, minToken }: { p: Platform; busy: boolean; token: string; setToken: (v: string) => void; onSwitch: () => void; minToken: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4 rounded-xl border border-dashed border-line-3 p-4 text-sm leading-7" style={vars(p)}>
      <p className="m-0 font-bold">این ربات هنوز با ربات مشترک بات‌یار منتشر شده است (نسخه‌ی آزمایشی)</p>
      <p className="m-0 mb-3 text-mute">برای کسب‌وکار واقعی ربات اختصاصی خودتان را بسازید تا مشتری نام و تصویر شما را ببیند. سفارش‌ها، ثبت‌ها و فهرست محصولات همین‌طور می‌مانند؛ فقط لینک ربات عوض می‌شود و لینک تازه را باید به مشتریان بدهید.</p>
      {!open ? (
        <button type="button" onClick={() => setOpen(true)} className="min-h-11 rounded-xl border border-[var(--brand)] px-4 font-bold hover:bg-[var(--brand)]/10">تبدیل به ربات اختصاصی</button>
      ) : (
        <>
          <OwnBotSetup p={p} token={token} setToken={setToken} />
          <div className="flex flex-wrap items-center gap-3">
            <BrandButton disabled={busy || token.trim().length < minToken} onClick={onSwitch}>{busy ? "در حال انتقال…" : `انتقال به ربات اختصاصی در ${BRAND[p].name}`}</BrandButton>
            <button type="button" onClick={() => setOpen(false)} className="text-mute underline">بعداً</button>
          </div>
        </>
      )}
    </div>
  );
}
