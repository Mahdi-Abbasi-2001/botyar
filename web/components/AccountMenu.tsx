"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, getUsername, setToken, whoAmI } from "@/lib/api";

const ITEMS: [string, string][] = [["/bots/", "داشبورد"], ["/account/", "پلن و مصرف"], ["/pricing/", "تعرفه‌ها"], ["/support/", "پشتیبانی"]];

/** The one account control of every app page: the username, opening a menu with the app's pages and sign-out.
 *  On phones only the person icon shows, so crowded headers (the bot workspace) still fit. */
export function AccountMenu() {
  const router = useRouter();
  const path = usePathname();
  const [name, setName] = useState("");
  const [open, setOpen] = useState(false);
  // a reply from the team waiting in «پشتیبانی» (for admins: tickets still open) puts a dot on the menu
  const [count, setNews] = useState(0);
  const news = path.startsWith("/support") ? 0 : count;  // the page itself marks replies as read
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setName(getUsername() ?? "");
    whoAmI().then((u) => { if (u) setName(u); });
    api<{ count: number; admin_open: number | null }>("/tickets/unread").then((r) => setNews(r.count + (r.admin_open ?? 0))).catch(() => {});
  }, []);

  // close on a click elsewhere or Escape (focus goes back to the button)
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); button.current?.focus(); } };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);

  const signOut = () => { setToken(null); router.push("/"); };
  const item = "flex min-h-11 items-center justify-between gap-3 rounded-lg px-3 text-sm hover:bg-raised";

  return (
    <div ref={box} className="relative shrink-0">
      <button ref={button} type="button" aria-haspopup="menu" aria-expanded={open} aria-label={`حساب کاربری ${name}`} onClick={() => setOpen(!open)}
        className={`flex min-h-11 items-center gap-2 rounded-xl border px-2.5 text-sm sm:px-3 ${open ? "border-line-3 bg-raised text-fg" : "border-line-2 text-fg-2 hover:border-line-3 hover:text-fg"}`}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden className="shrink-0">
          <circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0116 0" />
        </svg>
        <span dir="ltr" className="hidden max-w-[160px] truncate font-bold sm:inline">{name || "حساب من"}</span>
        {news > 0 && <span className="h-2 w-2 shrink-0 rounded-full bg-saffron" aria-label="پاسخ تازه در پشتیبانی" />}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden
          className={`hidden shrink-0 text-mute transition-transform duration-200 sm:block ${open ? "rotate-180" : ""}`}><path d="M6 9l6 6 6-6" /></svg>
      </button>

      {open && (
        <div role="menu" className="anim-menu absolute left-0 top-[calc(100%+8px)] z-40 flex w-56 flex-col rounded-2xl border border-line-2 bg-panel p-1.5 shadow-2xl shadow-black/60">
          <span dir="ltr" className="truncate px-3 pb-2 pt-1.5 text-right text-xs text-mute">{name}</span>
          {ITEMS.map(([href, label]) => {
            const here = path === href || path === href.slice(0, -1);
            return (
              <Link key={href} href={href} role="menuitem" aria-current={here ? "page" : undefined} onClick={() => setOpen(false)}
                className={`${item} ${here ? "font-bold text-fg" : "text-fg-2 hover:text-fg"}`}>
                {label}
                {href === "/support/" && news > 0 && !here
                  ? <span className="rounded-full bg-saffron px-2 text-xs font-bold text-ink">{news.toLocaleString("fa-IR")}</span>
                  : here && <span className="h-1.5 w-1.5 rounded-full bg-saffron" aria-hidden />}
              </Link>
            );
          })}
          <span className="mx-2 my-1 h-px bg-line" aria-hidden />
          <button type="button" role="menuitem" onClick={signOut} className={`${item} text-fg-2 hover:text-bad-soft`}>خروج از حساب</button>
        </div>
      )}
    </div>
  );
}
