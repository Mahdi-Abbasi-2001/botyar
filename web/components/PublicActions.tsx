"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getToken, whoAmI } from "@/lib/api";

/** End of the public header (landing, pricing): «ورود» + «شروع رایگان» for visitors, one «ورود به داشبورد»
 *  for someone already signed in. The public pages are for deciding; the only thing a signed-in owner
 *  needs there is the way back into the app (their account lives in the app header's menu). */
export function PublicActions() {
  // undefined until mounted: the page is a static export, so the session is only known in the browser
  const [signedIn, setSignedIn] = useState<boolean | undefined>(undefined);
  useEffect(() => {
    setSignedIn(!!getToken());
    // an expired session reads as signed out instead of sending the visitor to the login page
    whoAmI().then((u) => { if (u !== undefined) setSignedIn(u !== null); });
  }, []);

  const cta = "inline-flex min-h-11 shrink-0 items-center rounded-xl bg-fg px-4 text-sm font-bold text-ink hover:bg-white sm:px-5 sm:text-[15px]";
  if (signedIn === undefined) return <span className="min-h-11 w-28" aria-hidden />;
  if (signedIn) return <Link href="/bots/" className={cta}>ورود به داشبورد</Link>;
  return (
    <>
      <Link href="/login/?mode=login" className="min-h-11 content-center text-sm text-fg-2 hover:text-fg sm:text-[15px]">ورود</Link>
      <Link href="/login/" className={cta}>شروع رایگان</Link>
    </>
  );
}
