"use client";
import { useEffect, useState } from "react";
import { Stamp } from "./ui";

// The sample request, split so each meaningful phrase maps to a numbered block in the map.
const SEGS: [string, number][] = [
  ["برای کلینیک دندانپزشکی‌ام ", 1],
  ["ربات نوبت‌دهی", 2],
  [" می‌خوام. دو زمان دارم: ", 0],
  ["شنبه ساعت ۹ صبح", 2],
  [" و ", 0],
  ["دوشنبه ساعت ۵ عصر", 2],
  ["، ", 0],
  ["ظرفیت هر کدوم ۸ نفر", 2],
  [". ", 0],
  ["نام و شماره موبایل بیمار رو بگیر", 3],
  [" و ", 0],
  ["ثبت نوبت که شد به من اطلاع بده", 4],
  [".", 0],
];
const NUM = ["", "۱", "۲", "۳", "۴"];
/** The whole sample, for «ساخت همین ربات»: a signed-in owner gets it prefilled in the dashboard's new-bot box. */
export const SAMPLE_REQUEST = SEGS.map(([t]) => t).join("");
const ENDS = SEGS.reduce<number[]>((a, [t]) => [...a, (a.at(-1) ?? 0) + t.length], []);
const LEN = ENDS.at(-1)!;
const TICK = 45;

export function useTyping() {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setN(LEN + 40);
      return;
    }
    const t = setInterval(() => setN((v) => (v >= LEN + 90 ? 0 : v + 1)), TICK);
    return () => clearInterval(t);
  }, []);
  return n;
}

function Sentence({ n, caret }: { n: number; caret?: boolean }) {
  let start = 0;
  return (
    <>
      {SEGS.map(([text, tag], i) => {
        const s = start;
        start += text.length;
        const hl = n >= ENDS[i] && tag > 0;
        return (
          <span key={i}>
            <span className={`rounded transition-colors duration-500 ${hl ? "bg-saffron/15 text-saffron-soft shadow-[inset_0_-2px_0_var(--color-saffron)]" : ""}`}>
              {text.slice(0, Math.max(0, n - s))}
            </span>
            {hl && <sup className="mx-0.5 rounded-full bg-saffron px-1.5 text-[11px] font-black text-ink">{NUM[tag]}</sup>}
          </span>
        );
      })}
      {caret && n < LEN && <span className="anim-caret font-light text-saffron">|</span>}
    </>
  );
}

export function TypedRequest({ n }: { n: number }) {
  return (
    // the finished sentence is laid out invisibly in the same cell, so the box is exactly as tall as the full text at every width
    <p className="m-0 grid text-xl leading-[2.05]">
      <span aria-hidden className="invisible col-start-1 row-start-1"><Sentence n={LEN + 1} /></span>
      <span className="col-start-1 row-start-1"><Sentence n={n} caret /></span>
    </p>
  );
}

function Node({ on, children, className = "" }: { on: boolean; children: React.ReactNode; className?: string }) {
  return (
    <div className={`transition-all duration-500 ${on ? "opacity-100" : "translate-y-2.5 opacity-10"} ${className}`}>{children}</div>
  );
}

const Num = ({ n }: { n: string }) => (
  <span className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-saffron text-[13px] font-black text-ink">{n}</span>
);

export function BlueprintPreview({ n }: { n: number }) {
  const cap = n >= ENDS[7];
  return (
    <div className="relative mb-12 flex flex-col gap-3">
      <span className="text-[13px] text-mute">نقشه‌ی ربات، هم‌زمان با نوشتن شما</span>
      <Node on={n >= ENDS[0]} className="flex items-center gap-3 rounded-2xl border border-line-2 bg-panel px-4 py-3.5">
        <Num n="۱" />
        <div className="flex flex-col"><span className="text-xs text-mute">پیام خوش‌آمد</span><span className="text-[15px]">سلام! به کلینیک دندانپزشکی خوش آمدید.</span></div>
      </Node>
      <Node on={n >= ENDS[1]} className="flex items-start gap-3 rounded-2xl border border-saffron bg-panel px-4 py-3.5">
        <Num n="۲" />
        <div className="flex flex-1 flex-col gap-2.5">
          <span className="text-xs text-mute">نوبت‌دهی · دکمه‌ی «دریافت نوبت»</span>
          {[["شنبه ساعت ۹ صبح", ENDS[3]], ["دوشنبه ساعت ۵ عصر", ENDS[5]]].map(([label, end]) => (
            <Node key={label} on={n >= (end as number)} className="flex flex-col gap-1">
              <div className="flex justify-between text-sm"><span>{label}</span><span className={`text-saffron transition-opacity ${cap ? "" : "opacity-0"}`}>ظرفیت ۸</span></div>
              <div className="h-1.5 rounded-full bg-line"><div className="h-1.5 rounded-full bg-saffron transition-all duration-700" style={{ width: cap ? "100%" : "0%" }} /></div>
            </Node>
          ))}
        </div>
      </Node>
      <div className="grid grid-cols-2 gap-3">
        <Node on={n >= ENDS[9]} className="flex items-center gap-3 rounded-2xl border border-line-2 bg-panel px-4 py-3.5">
          <Num n="۳" />
          <div className="flex flex-col"><span className="text-xs text-mute">اطلاعات بیمار</span><span className="text-sm">نام · شماره‌ی موبایل</span></div>
        </Node>
        <Node on={n >= ENDS[11]} className="flex items-center gap-3 rounded-2xl border border-amber-line bg-amber-bg px-4 py-3.5">
          <Num n="۴" />
          <div className="flex flex-col"><span className="text-xs text-amber-fg/80">اطلاع به مدیر</span><span className="text-sm">پس از ثبت هر نوبت</span></div>
        </Node>
      </div>
      <Node on={n >= LEN + 15} className="flex items-center gap-3.5 rounded-2xl border border-mint-line bg-mint-bg px-4 py-3.5 text-mint-fg">
        <span className="flex-1 text-[15px] font-extrabold">۵ سناریوی تست نوشته و اجرا شد</span>
      </Node>
      {n >= LEN + 32 && <Stamp sub="۵ از ۵" size={146} className="absolute -bottom-14 left-1" />}
    </div>
  );
}
