"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getToken, getUsername, whoAmI } from "@/lib/api";

/** Header link: the signed-in username (to the account page), or «ورود / ثبت‌نام» before signing in. */
/** `onSignedIn` tells the page what the server said, so other signed-in-only bits can follow (e.g. the landing CTA). */
export function AccountLink({ className = "", onSignedIn }: { className?: string; onSignedIn?: (yes: boolean) => void }) {
  // undefined until mounted: the page is a static export, so localStorage is only read in the browser
  const [name, setName] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    if (!getToken()) return setName(null);
    setName(getUsername() ?? "");
    // confirm with the server: covers sessions from before the username was stored, and expired ones
    whoAmI().then((u) => { if (u !== undefined) { setName(u); onSignedIn?.(u !== null); } });
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  if (name === undefined) return <span className={`min-h-11 ${className}`} aria-hidden />;
  if (name === null) return <Link href="/login/?mode=login" className={`min-h-11 content-center text-fg-2 hover:text-fg ${className}`}>ورود / ثبت‌نام</Link>;
  return (
    <Link href="/account/" title="حساب، پلن و مصرف" className={`inline-flex min-h-11 max-w-[130px] sm:max-w-[220px] items-center gap-2 text-fg-2 hover:text-fg ${className}`}>
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden className="shrink-0">
        <circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0116 0" />
      </svg>
      <span dir="ltr" className="truncate font-bold">{name || "حساب من"}</span>
    </Link>
  );
}
