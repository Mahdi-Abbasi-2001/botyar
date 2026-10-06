"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type St = { configured: boolean; test: boolean; mode: "shared" | "own" | null; active: boolean };
const card = "rounded-2xl border border-line-2 bg-panel p-4";

export function PaymentCard({ botId, mode }: { botId: string; mode?: "shared" | "own" }) {
  const [st, setSt] = useState<St | null>(null);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setSt(await api<St>(`/bots/${botId}/payment`));
    } catch (e: any) {
      setError(e.message);
    }
  }, [botId]);
  useEffect(() => {
    load();
  }, [load, mode]);

  async function save() {
    setBusy(true);
    setError("");
    try {
      setSt(await api<St>(`/bots/${botId}/payment`, { method: "PUT", body: { wallet_token: token.trim() } }));
      setToken("");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    setBusy(true);
    try {
      await api(`/bots/${botId}/payment`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={card}>
      <h3 className="mb-1 font-bold">پرداخت آنلاین (برای سفارش‌ها)</h3>
      <p className="mb-2 text-sm leading-7 text-mute">
        اگر ربات سفارش شما «پرداخت آنلاین» دارد، مبلغ مستقیم به کیف پول خودتان در بله واریز می‌شود، نه به بات‌یار. توکن کیف پول را از @botfather در بله دریافت کنید. برای دریافت پرداخت واقعی باید ربات اختصاصی خودتان را منتشر کنید؛ در ربات مشترک بات‌یار فقط توکن آزمایشی بله کار می‌کند (<span dir="ltr">WALLET-TEST-1111111111111111</span>).
      </p>
      {st?.configured ? (
        <p className={`text-sm ${st.active ? "text-mint" : "text-amber-fg"}`}>
          {st.active ? (st.test ? "✓ فعال (حالت آزمایشی؛ هیچ مبلغ واقعی جابه‌جا نمی‌شود)" : "✓ فعال") : "ذخیره شده، اما فعال نیست. برای استفاده از توکن واقعی، ربات را با توکن اختصاصی خودتان منتشر کنید."}{" "}
          <button className="mr-2 text-mute underline" onClick={remove} disabled={busy}>حذف توکن</button>
        </p>
      ) : (
        <div className="flex gap-2">
          <input dir="ltr" aria-label="توکن کیف پول" className="min-h-11 flex-1 rounded-xl border border-line-2 bg-raised px-3" value={token} onChange={(e) => setToken(e.target.value)} placeholder="WALLET-…" />
          <button className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50" disabled={busy || token.trim().length < 8} onClick={save}>ذخیره</button>
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-red-400">{error}</p>}
    </div>
  );
}
