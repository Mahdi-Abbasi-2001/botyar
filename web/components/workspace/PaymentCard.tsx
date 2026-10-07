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

  const own = mode === "own";
  return (
    <div className={card}>
      <h3 className="mb-1 font-bold">پرداخت آنلاین سفارش‌ها <span className="text-sm font-normal text-mute">(اختیاری)</span></h3>
      <p className="mb-3 text-sm leading-7 text-mute">
        فقط وقتی لازم است که مشتری‌ها داخل بله پول سفارش را پرداخت کنند. پول مستقیم به کیف پول خودتان در بله می‌رود، نه به بات‌یار. اگر ربات شما سفارش با پرداخت در محل یا کارت‌به‌کارت می‌گیرد، این بخش را رها کنید.
      </p>
      {st?.configured ? (
        <div className="text-sm leading-7">
          <p className={`m-0 ${st.active ? "text-mint" : "text-amber-fg"}`}>
            {st.active
              ? st.test ? "✓ فعال، در حالت آزمایشی: هیچ پولی واقعاً جابه‌جا نمی‌شود." : "✓ فعال: پرداخت‌ها به کیف پول شما می‌روند."
              : "توکن ذخیره شد، اما هنوز فعال نیست: پرداخت واقعی فقط با ربات اختصاصی شما در بله کار می‌کند."}
          </p>
          <button className="mt-1 text-mute underline" onClick={remove} disabled={busy}>حذف توکن</button>
        </div>
      ) : (
        <>
          <ol className="mb-3 flex flex-col gap-2 text-sm leading-7">
            <li className="flex gap-3"><span className="grid size-6 shrink-0 place-items-center rounded-full bg-raised text-xs font-black">۱</span>
              <span>ربات خودتان را در بله منتشر کنید{own ? " (این کار را کرده‌اید ✓)" : " (کارت «بله» در همین صفحه، گزینه‌ی «ربات اختصاصی»)"}.</span></li>
            <li className="flex gap-3"><span className="grid size-6 shrink-0 place-items-center rounded-full bg-raised text-xs font-black">۲</span>
              <span>در بله به <b dir="ltr">@botfather</b> پیام بدهید و توکن کیف پول (پرداخت) همان ربات را بگیرید.</span></li>
            <li className="flex gap-3"><span className="grid size-6 shrink-0 place-items-center rounded-full bg-raised text-xs font-black">۳</span>
              <span>توکن را همین‌جا بگذارید.</span></li>
          </ol>
          <p className="mb-3 text-xs leading-6 text-dim">فقط برای امتحان: با ربات مشترک بات‌یار می‌توانید توکن آزمایشی <span dir="ltr">WALLET-TEST-1111111111111111</span> را بگذارید؛ در این حالت پولی جابه‌جا نمی‌شود.</p>
          <div className="flex gap-2">
            <input dir="ltr" aria-label="توکن کیف پول" className="min-h-11 flex-1 rounded-xl border border-line-2 bg-raised px-3" value={token} onChange={(e) => setToken(e.target.value)} placeholder="WALLET-…" />
            <button className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50" disabled={busy || token.trim().length < 8} onClick={save}>ذخیره</button>
          </div>
        </>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-red-400">{error}</p>}
    </div>
  );
}
