import Link from "next/link";

export const fa = (n: number | string) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[+d]);

export function Logo({ href = "/", size = "md" }: { href?: string; size?: "sm" | "md" }) {
  const box = size === "sm" ? "h-8 w-8 rounded-[9px] text-base" : "h-9 w-9 rounded-[10px] text-xl";
  return (
    <Link href={href} className="flex items-center gap-2.5 text-fg" aria-label="بات‌یار">
      <span className={`flex items-center justify-center bg-saffron font-black text-ink ${box}`}>ب</span>
      <span className={`font-extrabold ${size === "sm" ? "text-lg" : "text-[22px]"}`}>بات‌یار</span>
    </Link>
  );
}

/** The rubber stamp shown whenever a version passes all its tests. */
export function Stamp({ label = "تست‌شده", sub, size = 150, settle = false, className = "" }: { label?: string; sub?: string; size?: number; settle?: boolean; className?: string }) {
  return (
    <div
      aria-hidden
      className={`${settle ? "anim-stamp-settle" : "anim-stamp"} pointer-events-none flex flex-col items-center justify-center rounded-full border-[5px] border-double border-mint bg-ink/85 text-center text-mint ${className}`}
      style={{ width: size, height: size }}
    >
      <span className="font-black leading-tight" style={{ fontSize: size * 0.19 }}>{label}</span>
      {sub && <span className="font-extrabold" style={{ fontSize: Math.max(12, size * 0.09) }}>{sub}</span>}
    </div>
  );
}

/** Five-ish segments, one per test; green = passed. */
export function TestBar({ passed, total, h = 6 }: { passed: number; total: number; h?: number }) {
  if (!total) return null;
  return (
    <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${total}, minmax(0, 1fr))` }}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={i < passed ? "bg-mint" : "bg-bad"} style={{ height: h, borderRadius: h / 2 }} />
      ))}
    </div>
  );
}

export function CapacityBar({ used, capacity }: { used: number; capacity: number }) {
  const pct = Math.min(100, Math.round((used / capacity) * 100));
  return (
    <div className="h-1.5 rounded-full bg-line">
      <div className={`h-1.5 rounded-full ${pct >= 100 ? "bg-bad-soft" : "bg-saffron"}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

type IconName = "send" | "bell" | "shield" | "back" | "alert" | "plus" | "phone" | "chat" | "tree" | "clock" | "list" | "refresh";
const PATHS: Record<IconName, React.ReactNode> = {
  send: <path d="M19 12H5M11 6l-6 6 6 6" />,
  bell: <><path d="M6 8a6 6 0 0112 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 003.4 0" /></>,
  shield: <><path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z" /><path d="M8.5 12l2.5 2.5 4.5-5" /></>,
  back: <path d="M9 6l6 6-6 6" />,
  alert: <><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  phone: <><rect x="5" y="3" width="14" height="18" rx="3" /><path d="M10 18h4" /></>,
  chat: <path d="M4 5h16v11H8l-4 4z" />,
  tree: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /><path d="M10 6.5h4v7.5" /></>,
  clock: <><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2" /></>,
  list: <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />,
  refresh: <><path d="M20 11a8 8 0 10-2.3 5.7" /><path d="M20 4v7h-7" /></>,
};

export function Icon({ name, size = 18, className = "", strokeWidth = 2 }: { name: IconName; size?: number; className?: string; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      {PATHS[name]}
    </svg>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-bad-line bg-bad-bg px-3.5 py-3 text-sm leading-7 text-bad-fg">
      <Icon name="alert" className="mt-1 shrink-0" />
      <span>{children}</span>
    </div>
  );
}
