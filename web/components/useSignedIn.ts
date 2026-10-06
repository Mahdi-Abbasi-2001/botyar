"use client";
import { useEffect, useState } from "react";
import { getToken, whoAmI } from "@/lib/api";

/** Signed in or not, for pages anyone can open. undefined until known (the pages are a static export,
 *  so the session only exists in the browser); an expired session reads as signed out. */
export function useSignedIn() {
  const [signedIn, setSignedIn] = useState<boolean | undefined>(undefined);
  useEffect(() => {
    setSignedIn(!!getToken());
    whoAmI().then((u) => { if (u !== undefined) setSignedIn(u !== null); });
  }, []);
  return signedIn;
}
