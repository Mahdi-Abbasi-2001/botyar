"use client";
import { useState } from "react";
import { downloadFile } from "@/lib/api";

/** Two small buttons: CSV (re-importable backup) and Excel. */
export function ExportButtons({ path, name, onError }: { path: string; name: string; onError: (m: string) => void }) {
  const [busy, setBusy] = useState<"csv" | "xlsx" | null>(null);
  async function go(fmt: "csv" | "xlsx") {
    setBusy(fmt);
    try {
      await downloadFile(`${path}${path.includes("?") ? "&" : "?"}format=${fmt}`, `${name}.${fmt}`);
    } catch (e: any) {
      onError(e.message);
    } finally {
      setBusy(null);
    }
  }
  const cls = "min-h-9 rounded-lg border border-line-2 px-3 text-sm hover:border-saffron disabled:opacity-50";
  return (
    <span className="flex items-center gap-2">
      <button className={cls} disabled={busy !== null} onClick={() => go("xlsx")}>{busy === "xlsx" ? "…" : "⬇ Excel"}</button>
      <button className={cls} disabled={busy !== null} onClick={() => go("csv")} title="برای پشتیبان‌گیری و وارد کردن دوباره">{busy === "csv" ? "…" : "⬇ CSV"}</button>
    </span>
  );
}
