"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fa } from "@/components/ui";
import { ShareLink } from "@/components/workspace/ShareLink";

type Tg = {
  enabled: boolean; published: boolean; latest_version: number; tests_ok: boolean; shared_bot_username: string; listed: boolean;
  mode?: "shared" | "own"; version?: number; code?: string; admin_code?: string; bot_username?: string; admin_linked?: boolean; up_to_date?: boolean;
};

const card = "rounded-2xl border border-line-2 bg-panel p-4";
const btn = "min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50";

/** Publishing the same bot to Telegram (through the relay outside Iran). Independent of the Bale publication. */
export function TelegramCard({ botId }: { botId: string }) {
  const [tg, setTg] = useState<Tg | null>(null);
  const [mode, setMode] = useState<"shared" | "own">("shared");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const s = await api<Tg>(`/bots/${botId}/telegram`);
      setTg(s);
      if (!s.shared_bot_username) setMode("own");
    } catch (e: any) {
      setError(e.message);
    }
  }, [botId]);

  useEffect(() => {
    load();
  }, [load]);

  async function publish(m: "shared" | "own") {
    setBusy(true);
    setError("");
    try {
      setTg(await api<Tg>(`/bots/${botId}/telegram/publish`, { body: { mode: m, token: m === "own" ? token : undefined } }));
      setToken("");
    } catch (e: any) {
      setError(e.message);
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
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function unpublish() {
    if (!confirm("انتشار در تلگرام لغو شود؟ کاربران تلگرام دیگر پاسخی نمی‌گیرند.")) return;
    setBusy(true);
    try {
      setTg(await api<Tg>(`/bots/${botId}/telegram/unpublish`, { method: "POST", body: {} }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!tg) return null;
  if (!tg.enabled) {
    return (
      <div className={card}>
        <h3 className="mb-1 font-bold">تلگرام</h3>
        <p className="text-sm leading-7 text-mute">اتصال به تلگرام روی این سرور فعال نیست.</p>
      </div>
    );
  }
  const handle = tg.mode === "own" ? tg.bot_username : tg.shared_bot_username;
  const err = error && <p className="mb-3 rounded-xl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{error}</p>;

  if (!tg.published) {
    return (
      <div className={card}>
        <h3 className="mb-1 text-lg font-extrabold">انتشار روی تلگرام هم</h3>
        <p className="mb-4 text-sm leading-7 text-mute">همین ربات، با همین تست‌ها، برای مشتری‌هایی که تلگرام دارند. ثبت‌ها و اعلان‌ها کنار ثبت‌های بله می‌آیند. پرداخت آنلاین فقط در بله فعال است.</p>
        {err}
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          {tg.shared_bot_username && (
            <button onClick={() => setMode("shared")} aria-pressed={mode === "shared"}
              className={`rounded-xl border p-4 text-right ${mode === "shared" ? "border-saffron bg-saffron/10" : "border-line-2 hover:border-mute"}`}>
              <div className="font-bold">ربات بات‌یار در تلگرام</div>
              <div className="mt-1 text-sm leading-6 text-mute">سریع‌ترین راه، بدون ساختن ربات؛ یک لینک و QR به ربات شما در <span dir="ltr">@{tg.shared_bot_username}</span> می‌گیرید.</div>
            </button>
          )}
          <button onClick={() => setMode("own")} aria-pressed={mode === "own"}
            className={`rounded-xl border p-4 text-right ${mode === "own" ? "border-saffron bg-saffron/10" : "border-line-2 hover:border-mute"}`}>
            <div className="font-bold">ربات تلگرام خودتان</div>
            <div className="mt-1 text-sm leading-6 text-mute">با نام و عکس خودتان. توکن را از <span dir="ltr">@BotFather</span> تلگرام می‌گیرید.</div>
          </button>
        </div>
        {mode === "own" && (
          <label className="mb-4 block text-sm">
            <span className="mb-1 block text-mute">توکن ربات تلگرام (محرمانه است و رمزنگاری ذخیره می‌شود)</span>
            <input dir="ltr" value={token} onChange={(e) => setToken(e.target.value)} placeholder="123456789:AA…" autoComplete="off"
              className="min-h-11 w-full rounded-xl border border-line-2 bg-ink px-3 text-left outline-none focus:border-saffron" />
          </label>
        )}
        <button className={btn} disabled={busy || !tg.tests_ok || (mode === "own" && token.trim().length < 20)} onClick={() => publish(mode)}>
          {busy ? "در حال انتشار…" : "انتشار روی تلگرام"}
        </button>
      </div>
    );
  }

  return (
    <div className={card}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-extrabold"><span className="ml-2 inline-block h-2.5 w-2.5 rounded-full bg-mint" />منتشر شده روی تلگرام · نسخه {fa(tg.version ?? 0)}</h3>
        <button onClick={unpublish} disabled={busy} className="text-sm text-mute hover:text-bad">لغو انتشار</button>
      </div>
      {err}
      {!tg.up_to_date && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-saffron/50 bg-saffron/10 p-3 text-sm">
          <span>نسخه‌ی {fa(tg.latest_version)} آماده است ولی در تلگرام هنوز منتشر نشده.</span>
          <button className={btn + " !min-h-9 !px-4 text-sm"} disabled={busy || !tg.tests_ok} onClick={() => publish(tg.mode!)}>انتشار نسخه‌ی {fa(tg.latest_version)}</button>
        </div>
      )}
      {tg.mode === "shared" ? (
        <div className="flex flex-col gap-4">
          <ShareLink url={`https://t.me/${handle}?start=${tg.code}`} fileName={`telegram-${tg.code}`}
            hint="مشتری‌های تلگرامی با این لینک یا QR مستقیم وارد ربات شما می‌شوند." />
          <label className="flex items-start gap-3 rounded-xl border border-line-2 p-3 text-sm leading-7">
            <input type="checkbox" checked={tg.listed} onChange={(e) => setListed(e.target.checked)} disabled={busy} className="mt-1.5 h-5 w-5 accent-[var(--color-saffron)]" />
            <span>نمایش در فهرست <span dir="ltr">@{handle}</span><span className="block text-mute">همین تنظیم برای فهرست ربات بات‌یار در بله هم اعمال می‌شود.</span></span>
          </label>
        </div>
      ) : (
        <ShareLink url={`https://t.me/${handle}`} fileName={`telegram-${handle}`} hint="ربات تلگرام شما فعال است. این لینک را به مشتری‌ها بدهید." />
      )}
      <div className="mt-3 border-t border-line pt-3 text-sm leading-7">
        {tg.admin_linked ? (
          <span className="text-mint">✓ اعلان ثبت‌های جدید در تلگرام برای شما فعال است.</span>
        ) : (
          <span className="text-mute">برای گرفتن اعلان در تلگرام، این را از حساب خودتان به <span dir="ltr">@{handle}</span> بفرستید:
            <span dir="ltr" className="mr-2 inline-block rounded-lg bg-ink px-3 py-1 font-mono text-fg">/admin {tg.admin_code}</span>
            <button onClick={load} className="mr-2 text-saffron underline">بررسی دوباره</button></span>
        )}
      </div>
    </div>
  );
}
