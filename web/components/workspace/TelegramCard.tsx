"use client";
import { useCallback, useEffect, useState } from "react";
import { api, isPlanLimit } from "@/lib/api";
import { PlanLimitNote, fa } from "@/components/ui";
import { ShareLink } from "@/components/workspace/ShareLink";
import { BrandButton, ModeTile, PlatformCard, StatusPill } from "@/components/workspace/Messengers";

type Tg = {
  enabled: boolean; published: boolean; latest_version: number; tests_ok: boolean; shared_bot_username: string; listed: boolean; sample_products: boolean;
  mode?: "shared" | "own"; version?: number; code?: string; admin_code?: string; bot_username?: string; admin_linked?: boolean; up_to_date?: boolean;
};


/** Publishing the same bot to Telegram (through the relay outside Iran). Independent of the Bale publication. */
/** `allowSamples`: the owner ticked «publish with the demo products» in the publish tab (one choice for both messengers). */
export function TelegramCard({ botId, allowSamples }: { botId: string; allowSamples: boolean }) {
  const [tg, setTg] = useState<Tg | null>(null);
  const [mode, setMode] = useState<"shared" | "own">("shared");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setErrorText] = useState("");
  const [limitHit, setLimitHit] = useState(false);  // the last error was a plan limit (402)
  const setError = (m: string, e?: unknown) => { setErrorText(m); setLimitHit(!!m && isPlanLimit(e)); };

  const load = useCallback(async () => {
    try {
      const s = await api<Tg>(`/bots/${botId}/telegram`);
      setTg(s);
      if (!s.shared_bot_username) setMode("own");
    } catch (e: any) {
      setError(e.message, e);
    }
  }, [botId]);

  useEffect(() => {
    load();
  }, [load]);

  async function publish(m: "shared" | "own") {
    setBusy(true);
    setError("");
    try {
      setTg(await api<Tg>(`/bots/${botId}/telegram/publish`, { body: { mode: m, token: m === "own" ? token : undefined, allow_samples: allowSamples } }));
      setToken("");
    } catch (e: any) {
      setError(e.message, e);
    } finally {
      setBusy(false);
    }
  }

  async function setListed(listed: boolean) {
    setBusy(true);
    setError("");
    try {
      await api(`/bots/${botId}/listing`, { method: "PUT", body: { listed } });
      await load();
    } catch (e: any) {
      setError(e.message, e);
    } finally {
      setBusy(false);
    }
  }

  async function unpublish() {
    if (!confirm("انتشار در تلگرام متوقف شود؟ کاربران تلگرام دیگر پاسخی دریافت نمی‌کنند.")) return;
    setBusy(true);
    try {
      setTg(await api<Tg>(`/bots/${botId}/telegram/unpublish`, { method: "POST", body: {} }));
    } catch (e: any) {
      setError(e.message, e);
    } finally {
      setBusy(false);
    }
  }

  if (!tg) return null;
  if (!tg.enabled) {
    return (
      <PlatformCard p="telegram" title="تلگرام" status={<StatusPill on={false}>غیرفعال</StatusPill>}>
        <p className="text-sm leading-7 text-mute">اتصال به تلگرام روی این سرور فعال نیست.</p>
      </PlatformCard>
    );
  }
  const handle = tg.mode === "own" ? tg.bot_username : tg.shared_bot_username;
  const err = error && (limitHit ? <PlanLimitNote text={error} className="mb-3" /> : <p className="mb-3 rounded-xl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{error}</p>);

  if (!tg.published) {
    return (
      <PlatformCard p="telegram" title="انتشار در تلگرام" lead="ربات شما همین‌جا آزمایش شده است. پس از انتشار، مشتریان در تلگرام با آن گفت‌وگو می‌کنند و ثبت‌ها به‌صورت واقعی ذخیره می‌شوند." status={<StatusPill on={false}>منتشر نشده</StatusPill>}>
        {err}
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          {tg.shared_bot_username && (
            <ModeTile selected={mode === "shared"} onClick={() => setMode("shared")} title="ربات بات‌یار"
              text={<>سریع‌ترین راه، بدون ساخت ربات جداگانه. یک لینک و کد QR می‌گیرید که مشتری را مستقیم به ربات شما در <span dir="ltr">@{tg.shared_bot_username}</span> می‌برد.</>} />
          )}
          <ModeTile selected={mode === "own"} onClick={() => setMode("own")} title="ربات اختصاصی شما" badge="پیشنهادی"
            text={<>با نام و تصویر خودتان. توکن را از <span dir="ltr">@BotFather</span> در تلگرام دریافت می‌کنید.</>} />
        </div>
        <p className="mb-4 text-sm leading-7 text-mute">ثبت‌ها و اعلان‌های تلگرام کنار ثبت‌های بله نمایش داده می‌شوند. پرداخت آنلاین فقط در بله فعال است.</p>
        {mode === "own" && (
          <label className="mb-4 block text-sm">
            <span className="mb-1 block text-mute">توکن ربات (محرمانه است و به‌صورت رمزنگاری‌شده ذخیره می‌شود)</span>
            <input dir="ltr" value={token} onChange={(e) => setToken(e.target.value)} placeholder="123456789:AA…" autoComplete="off"
              className="min-h-11 w-full rounded-xl border border-line-2 bg-ink px-3 text-left outline-none focus:border-[var(--brand)]" />
          </label>
        )}
        <BrandButton disabled={busy || (tg.sample_products && !allowSamples) || !tg.tests_ok || (mode === "own" && token.trim().length < 20)} onClick={() => publish(mode)}>
          {busy ? "در حال انتشار…" : "انتشار در تلگرام"}
        </BrandButton>
      </PlatformCard>
    );
  }

  return (
    <PlatformCard p="telegram" title="تلگرام" lead={tg.mode === "own" ? "ربات اختصاصی شما" : "ربات بات‌یار"} status={<StatusPill on>منتشرشده · نسخه‌ی {fa(tg.version ?? 0)}</StatusPill>}
      action={<button onClick={unpublish} disabled={busy} className="text-sm text-mute hover:text-bad">توقف انتشار</button>}>
      {err}
      {!tg.up_to_date && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--brand)]/50 bg-[var(--brand)]/10 p-3 text-sm">
          <span>نسخه‌ی {fa(tg.latest_version)} آماده است، اما هنوز در تلگرام منتشر نشده است.</span>
          <BrandButton className="!min-h-9 !px-4 text-sm" disabled={busy || (tg.sample_products && !allowSamples) || !tg.tests_ok} onClick={() => publish(tg.mode!)}>انتشار نسخه‌ی {fa(tg.latest_version)}</BrandButton>
        </div>
      )}
      {tg.mode === "shared" ? (
        <div className="flex flex-col gap-4">
          <ShareLink brand url={`https://t.me/${handle}?start=${tg.code}`} fileName={`telegram-${tg.code}`}
            hint="این لینک را در اینستاگرام، واتس‌اپ یا کنار صندوق قرار دهید؛ مشتری با باز کردن آن مستقیم وارد ربات شما می‌شود." />
          <label className="flex items-start gap-3 rounded-xl border border-line-2 p-3 text-sm leading-7">
            <input type="checkbox" checked={tg.listed} onChange={(e) => setListed(e.target.checked)} disabled={busy} className="mt-1.5 h-5 w-5 accent-[var(--brand)]" />
            <span>نمایش در فهرست <span dir="ltr">@{handle}</span><span className="block text-mute">این تنظیم برای فهرست ربات بات‌یار در بله هم اعمال می‌شود.</span></span>
          </label>
        </div>
      ) : (
        <ShareLink brand url={`https://t.me/${handle}`} fileName={`telegram-${handle}`} hint="ربات اختصاصی شما فعال است. این لینک را در اختیار مشتریان قرار دهید." />
      )}
      <div className="mt-3 border-t border-line pt-3 text-sm leading-7">
        {tg.admin_linked ? (
          <span className="text-mint">✓ اعلان ثبت‌های تازه در تلگرام برای شما فعال است.</span>
        ) : (
          <span className="text-mute">برای دریافت اعلان در تلگرام، این پیام را از حساب خودتان به <span dir="ltr">@{handle}</span> بفرستید:
            <span dir="ltr" className="mr-2 inline-block rounded-lg bg-ink px-3 py-1 font-mono text-fg">/admin {tg.admin_code}</span>
            <button onClick={load} className="mr-2 text-[var(--brand)] underline">بررسی دوباره</button></span>
        )}
      </div>
    </PlatformCard>
  );
}
