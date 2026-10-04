"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fa } from "@/components/ui";
import { ExportButtons } from "@/components/workspace/ExportButtons";
import { RecordActions } from "@/components/workspace/RecordActions";

type Pub = {
  published: boolean; latest_version: number; tests_ok: boolean; shared_bot_username: string; webhooks_enabled: boolean;
  mode?: "shared" | "own"; version?: number; code?: string; admin_code?: string; bot_username?: string; admin_linked?: boolean; up_to_date?: boolean;
};
type Live = { id: number; collection: string; data: Record<string, any>; created_at: string };

const card = "rounded-2xl border border-line-2 bg-panel p-4";
const btn = "min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50";

export function PublishTab({ botId }: { botId: string }) {
  const [pub, setPub] = useState<Pub | null>(null);
  const [mode, setMode] = useState<"shared" | "own">("shared");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [live, setLive] = useState<Live[]>([]);

  const load = useCallback(async () => {
    try {
      setPub(await api<Pub>(`/bots/${botId}/publication`));
      setLive(await api<Live[]>(`/bots/${botId}/records?sandbox=false`));
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
      setPub(await api<Pub>(`/bots/${botId}/publish`, { body: { mode: m, token: m === "own" ? token : undefined } }));
      setToken("");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function unpublish() {
    if (!confirm("انتشار ربات لغو شود؟ کاربران دیگر پاسخی نمی‌گیرند.")) return;
    setBusy(true);
    try {
      setPub(await api<Pub>(`/bots/${botId}/unpublish`, { method: "POST", body: {} }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!pub) return <p className="text-mute">{error || "در حال بارگذاری…"}</p>;
  const handle = pub.mode === "own" ? pub.bot_username : pub.shared_bot_username;

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="rounded-xl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{error}</p>}

      {!pub.published ? (
        <div className={card}>
          <h3 className="mb-1 text-lg font-extrabold">انتشار روی پیام‌رسان بله</h3>
          <p className="mb-4 text-sm leading-7 text-mute">ربات شما همین‌جا آزمایش شده است. با انتشار، مشتری‌هایتان می‌توانند در بله با آن گفتگو کنند و ثبت‌ها به‌صورت واقعی ذخیره می‌شود.</p>
          {!pub.tests_ok && <p className="mb-3 rounded-xl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">نسخه‌ی فعلی هنوز همه‌ی تست‌ها را نگذرانده؛ ابتدا با ایجنت اصلاحش کنید.</p>}
          <div className="mb-4 grid gap-3 sm:grid-cols-2">
            {([["shared", "ربات بات‌یار", "سریع‌ترین راه. مشتری کد ربات شما را برای @" + (pub.shared_bot_username || "botyar") + " می‌فرستد."], ["own", "ربات اختصاصی شما", "با نام و عکس خودتان. توکن را از @botfather بله می‌گیرید."]] as const).map(([m, t, d]) => (
              <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
                className={`rounded-xl border p-4 text-right ${mode === m ? "border-saffron bg-saffron/10" : "border-line-2 hover:border-mute"}`}>
                <div className="font-bold">{t}</div>
                <div className="mt-1 text-sm leading-6 text-mute">{d}</div>
              </button>
            ))}
          </div>
          {mode === "own" && (
            <label className="mb-4 block text-sm">
              <span className="mb-1 block text-mute">توکن ربات (محرمانه است و رمزنگاری ذخیره می‌شود)</span>
              <input dir="ltr" value={token} onChange={(e) => setToken(e.target.value)} placeholder="123456789:ABC…" autoComplete="off"
                className="min-h-11 w-full rounded-xl border border-line-2 bg-ink px-3 text-left outline-none focus:border-saffron" />
            </label>
          )}
          {!pub.webhooks_enabled && <p className="mb-3 text-sm text-mute">انتشار فقط روی نسخه‌ی آنلاین کار می‌کند.</p>}
          <button className={btn} disabled={busy || !pub.tests_ok || !pub.webhooks_enabled || (mode === "own" && token.trim().length < 10)} onClick={() => publish(mode)}>
            {busy ? "در حال انتشار…" : "انتشار روی بله"}
          </button>
        </div>
      ) : (
        <>
          <div className={card}>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-lg font-extrabold"><span className="ml-2 inline-block h-2.5 w-2.5 rounded-full bg-mint" />منتشر شده روی بله · نسخه {fa(pub.version ?? 0)}</h3>
              <button onClick={unpublish} disabled={busy} className="text-sm text-mute hover:text-bad">لغو انتشار</button>
            </div>
            {!pub.up_to_date && (
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-saffron/50 bg-saffron/10 p-3 text-sm">
                <span>نسخه‌ی {fa(pub.latest_version)} آماده است ولی هنوز منتشر نشده.</span>
                <button className={btn + " !min-h-9 !px-4 text-sm"} disabled={busy || !pub.tests_ok} onClick={() => publish(pub.mode!)}>انتشار نسخه‌ی {fa(pub.latest_version)}</button>
              </div>
            )}
            {pub.mode === "shared" ? (
              <ol className="list-decimal space-y-2 pr-5 text-sm leading-7">
                <li>در بله ربات <a className="font-bold text-saffron underline" dir="ltr" href={`https://ble.ir/${handle}`} target="_blank" rel="noreferrer">@{handle}</a> را باز کنید.</li>
                <li>این کد را برایش بفرستید (همین کد را به مشتری‌ها بدهید):
                  <div dir="ltr" className="my-2 inline-block rounded-xl border border-saffron bg-ink px-5 py-2 text-2xl font-black tracking-[0.3em] text-saffron">{pub.code}</div>
                </li>
              </ol>
            ) : (
              <p className="text-sm leading-7">ربات شما فعال است: <a className="font-bold text-saffron underline" dir="ltr" href={`https://ble.ir/${handle}`} target="_blank" rel="noreferrer">@{handle}</a></p>
            )}
          </div>

          <div className={card}>
            <h3 className="mb-1 font-bold">اعلان ثبت‌های جدید</h3>
            {pub.admin_linked ? (
              <p className="text-sm text-mint">✓ فعال است؛ ثبت‌های جدید در بله برای شما ارسال می‌شود.</p>
            ) : (
              <p className="text-sm leading-7 text-mute">برای دریافت اعلان، همین پیام را از حساب خودتان به {pub.mode === "own" ? "ربات" : `@${handle}`} بفرستید:
                <span dir="ltr" className="mr-2 inline-block rounded-lg bg-ink px-3 py-1 font-mono text-fg">/admin {pub.admin_code}</span>
                <button onClick={load} className="mr-2 text-saffron underline">بررسی دوباره</button></p>
            )}
          </div>

          <div className={card}>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold">ثبت‌های واقعی ({fa(live.length)})</h3>
              <span className="flex items-center gap-3"><button onClick={load} className="text-sm text-saffron">تازه‌سازی</button>
                {live.length > 0 && <ExportButtons path={`/bots/${botId}/export/records`} name="records" onError={setError} />}</span></div>
            {live.length === 0 ? <p className="text-sm text-mute">هنوز مشتری واقعی ثبتی انجام نداده است.</p> : (
              <ul className="space-y-2">
                {live.slice(0, 20).map((r) => (
                  <li key={r.id} className="flex flex-col gap-2 rounded-xl border border-line-2 p-3 text-sm">
                    <div>{Object.entries(r.data).filter(([k]) => !k.startsWith("_") && k !== "slot").map(([k, v]) => <span key={k} className="ml-3 inline-block"><span className="text-mute">{k}: </span>{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>)}</div>
                    <RecordActions botId={botId} rec={r} onChanged={load} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
