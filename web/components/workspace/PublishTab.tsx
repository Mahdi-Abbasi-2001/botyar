"use client";
import { useCallback, useEffect, useState } from "react";
import { api, isPlanLimit } from "@/lib/api";
import { PlanLimitNote, fa } from "@/components/ui";
import { ExportButtons } from "@/components/workspace/ExportButtons";
import { RecordActions } from "@/components/workspace/RecordActions";
import { PaymentCard } from "@/components/workspace/PaymentCard";
import { TelegramCard } from "@/components/workspace/TelegramCard";
import { ContentLinks, ShareLink } from "@/components/workspace/ShareLink";
import { BrandButton, ModeTile, OwnBotSetup, PlatformCard, StatusPill, SwitchToOwn } from "@/components/workspace/Messengers";

type Pub = {
  published: boolean; latest_version: number; tests_ok: boolean; shared_bot_username: string; webhooks_enabled: boolean; listed: boolean;
  sample_products: boolean;  // the product table still holds only the demo products made at build time
  daily_summary: boolean;    // the owner's 8:00 summary in their linked chat
  contents?: { id: string; title: string; channels: string[] }[];  // content behind a channel join: one link each
  mode?: "shared" | "own"; version?: number; code?: string; admin_code?: string; bot_username?: string; admin_linked?: boolean; up_to_date?: boolean;
};
type Live = { id: number; collection: string; data: Record<string, any>; created_at: string };

const card = "rounded-2xl border border-line-2 bg-panel p-4";
const btn = "min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50";

export function PublishTab({ botId, onImport }: { botId: string; onImport: () => void }) {
  const [pub, setPub] = useState<Pub | null>(null);
  // publishing the invented demo products is refused (server too) unless the owner says it's only a trial
  const [allowSamples, setAllowSamples] = useState(false);
  const samplesBlock = !!pub?.sample_products && !allowSamples;
  const [mode, setMode] = useState<"shared" | "own">("shared");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setErrorText] = useState("");
  const [limitHit, setLimitHit] = useState(false);  // the last error was a plan limit (402)
  const setError = (m: string, e?: unknown) => { setErrorText(m); setLimitHit(!!m && isPlanLimit(e)); };
  const [live, setLive] = useState<Live[]>([]);

  const load = useCallback(async () => {
    try {
      setPub(await api<Pub>(`/bots/${botId}/publication`));
      setLive(await api<Live[]>(`/bots/${botId}/records?sandbox=false`));
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
      setPub(await api<Pub>(`/bots/${botId}/publish`, { body: { mode: m, token: m === "own" ? token : undefined, allow_samples: allowSamples } }));
      setToken("");
    } catch (e: any) {
      setError(e.message, e);
    } finally {
      setBusy(false);
    }
  }

  async function setDigest(enabled: boolean) {
    try {
      const r = await api<{ daily_summary: boolean }>(`/bots/${botId}/digest`, { method: "PUT", body: { enabled } });
      setPub((p) => (p ? { ...p, daily_summary: r.daily_summary } : p));
    } catch (e: any) {
      setError(e.message, e);
    }
  }

  async function setListed(listed: boolean) {
    setBusy(true);
    setError("");
    try {
      setPub(await api<Pub>(`/bots/${botId}/listing`, { method: "PUT", body: { listed } }));
    } catch (e: any) {
      setError(e.message, e);
    } finally {
      setBusy(false);
    }
  }

  async function unpublish() {
    if (!confirm("انتشار ربات متوقف شود؟ کاربران دیگر پاسخی دریافت نمی‌کنند.")) return;
    setBusy(true);
    try {
      setPub(await api<Pub>(`/bots/${botId}/unpublish`, { method: "POST", body: {} }));
    } catch (e: any) {
      setError(e.message, e);
    } finally {
      setBusy(false);
    }
  }

  if (!pub) return <p className="text-mute">{error || "در حال بارگذاری…"}</p>;
  const handle = pub.mode === "own" ? pub.bot_username : pub.shared_bot_username;

  return (
    <div className="flex flex-col gap-4">
      {error && (limitHit ? <PlanLimitNote text={error} /> : <p className="rounded-xl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{error}</p>)}
      {pub.sample_products && <SampleProductsNote allow={allowSamples} setAllow={setAllowSamples} onImport={onImport} />}

      {!pub.published ? (
        <>
        <PlatformCard p="bale" title="انتشار در بله" lead="ربات شما همین‌جا آزمایش شده است. پس از انتشار، مشتریان در بله با آن گفت‌وگو می‌کنند و ثبت‌ها به‌صورت واقعی ذخیره می‌شوند." status={<StatusPill on={false}>منتشر نشده</StatusPill>}>
          {!pub.tests_ok && <p className="mb-3 rounded-xl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">همه‌ی تست‌های نسخه‌ی فعلی هنوز موفق نشده‌اند. ابتدا در «گفت‌وگوی ساخت» ربات را اصلاح کنید.</p>}
          <div className="mb-4 grid gap-3 sm:grid-cols-2">
            <ModeTile selected={mode === "shared"} onClick={() => setMode("shared")} title="شروع سریع" badge="آزمایشی"
              text={<>بدون ساخت ربات جداگانه. یک لینک و کد QR می‌گیرید که مشتری را به ربات شما در <span dir="ltr">@{pub.shared_bot_username || "botyar"}</span> می‌برد. فقط برای آزمایش ربات است.</>} />
            <ModeTile selected={mode === "own"} onClick={() => setMode("own")} title="ربات اختصاصی شما" badge="برای کسب‌وکار واقعی"
              text="با نام و تصویر خودتان. ساختنش حدود یک دقیقه طول می‌کشد و راهنمای قدم‌به‌قدم همین‌جاست."  />
          </div>
          {mode === "own" && <OwnBotSetup p="bale" token={token} setToken={setToken} />}
          {!pub.webhooks_enabled && <p className="mb-3 text-sm text-mute">انتشار فقط در نسخه‌ی آنلاین بات‌یار کار می‌کند.</p>}
          <BrandButton disabled={busy || samplesBlock || !pub.tests_ok || !pub.webhooks_enabled || (mode === "own" && token.trim().length < 10)} onClick={() => publish(mode)}>
            {busy ? "در حال انتشار…" : "انتشار در بله"}
          </BrandButton>
        </PlatformCard>
        <TelegramCard botId={botId} allowSamples={allowSamples} />
        </>
      ) : (
        <>
          <PlatformCard p="bale" title="بله" lead={pub.mode === "own" ? "ربات اختصاصی شما" : "ربات بات‌یار"} status={<StatusPill on>منتشرشده · نسخه‌ی {fa(pub.version ?? 0)}</StatusPill>}
            action={<button onClick={unpublish} disabled={busy} className="text-sm text-mute hover:text-bad">توقف انتشار</button>}>
            {!pub.up_to_date && (
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--brand)]/50 bg-[var(--brand)]/10 p-3 text-sm">
                <span>نسخه‌ی {fa(pub.latest_version)} آماده است، اما هنوز منتشر نشده است.</span>
                <BrandButton className="!min-h-9 !px-4 text-sm" disabled={busy || samplesBlock || !pub.tests_ok} onClick={() => publish(pub.mode!)}>انتشار نسخه‌ی {fa(pub.latest_version)}</BrandButton>
              </div>
            )}
            {pub.mode === "shared" ? (
              <div className="flex flex-col gap-4">
                <ShareLink brand url={`https://ble.ir/${handle}?start=${pub.code}`} fileName={`bale-${pub.code}`}
                  hint="این لینک را در اینستاگرام، واتس‌اپ یا کنار صندوق قرار دهید؛ مشتری با باز کردن آن مستقیم وارد ربات شما می‌شود." />
                <label className="flex items-start gap-3 rounded-xl border border-line-2 p-3 text-sm leading-7">
                  <input type="checkbox" checked={pub.listed} onChange={(e) => setListed(e.target.checked)} disabled={busy} className="mt-1.5 h-5 w-5 accent-[var(--brand)]" />
                  <span>نمایش در فهرست <span dir="ltr">@{handle}</span><span className="block text-mute">مشتریانی که بدون لینک وارد ربات بات‌یار شوند، ربات شما را در فهرست کسب‌وکارها می‌بینند. لینک اختصاصی شما در هر صورت کار می‌کند.</span></span>
                </label>
              </div>
            ) : (
              <ShareLink brand url={`https://ble.ir/${handle}`} fileName={`bale-${handle}`} hint="ربات اختصاصی شما فعال است. این لینک را در اختیار مشتریان قرار دهید." />
            )}
            <ContentLinks items={pub.contents ?? []} link={(id) => `https://ble.ir/${handle}?start=${pub.mode === "shared" ? `${pub.code}-${id}` : `go-${id}`}`} />
            {pub.mode === "shared" && <SwitchToOwn p="bale" busy={busy} token={token} setToken={setToken} minToken={10} onSwitch={() => publish("own")} />}
          </PlatformCard>
          <TelegramCard botId={botId} allowSamples={allowSamples} />

          <div className={card}>
            <h3 className="mb-1 font-bold">اعلان ثبت‌های تازه</h3>
            {pub.admin_linked ? (
              <>
                <p className="text-sm text-mint">✓ فعال است؛ ثبت‌های تازه در بله برای شما ارسال می‌شوند.</p>
                <label className="mt-2 flex min-h-11 items-center gap-2 text-sm">
                  <input type="checkbox" checked={pub.daily_summary} onChange={(e) => setDigest(e.target.checked)} />
                  <span>خلاصه‌ی روزانه، هر روز ساعت ۸ صبح<span className="block text-xs text-mute">نوبت‌های امروز به ترتیب ساعت، سفارش‌های باز، و پیام‌ها و سؤال‌های بی‌پاسخ؛ اگر چیزی نباشد، پیامی ارسال نمی‌شود.</span></span>
                </label>
              </>
            ) : (
              <p className="text-sm leading-7 text-mute">برای دریافت اعلان، همین پیام را از حساب خودتان به {pub.mode === "own" ? "ربات" : `@${handle}`} بفرستید:
                <span dir="ltr" className="mr-2 inline-block rounded-lg bg-ink px-3 py-1 font-mono text-fg">/admin {pub.admin_code}</span>
                <button onClick={load} className="mr-2 text-saffron underline">بررسی دوباره</button></p>
            )}
          </div>

          <StaffCard botId={botId} handle={pub.mode === "own" ? "ربات" : `@${handle}`} />

          <PaymentCard botId={botId} mode={pub.mode} />

          <div className={card}>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold">ثبت‌های واقعی ({fa(live.length)})</h3>
              <span className="flex items-center gap-3"><button onClick={load} className="text-sm text-saffron">به‌روزرسانی</button>
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

/** The product table still holds the demo products the agent invented: say so before anything goes live. */
function SampleProductsNote({ allow, setAllow, onImport }: { allow: boolean; setAllow: (v: boolean) => void; onImport: () => void }) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-amber-line bg-amber-bg p-4 text-sm leading-7">
      <strong className="text-base text-amber-fg">محصولات این ربات هنوز نمونه‌اند</strong>
      <span className="text-fg-2">بات‌یار این محصولات را ساخته تا بتوانید ربات را امتحان کنید. اگر ربات با همین‌ها منتشر شود، مشتریان واقعی محصولاتی را می‌بینند و سفارش می‌دهند که وجود ندارند.</span>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <button type="button" onClick={onImport} className="min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink hover:bg-saffron-hi">وارد کردن محصولات واقعی</button>
        <label className="flex min-h-11 items-center gap-2 text-mute">
          <input type="checkbox" checked={allow} onChange={(e) => setAllow(e.target.checked)} />
          فقط برای آزمایش، با همین محصولات نمونه منتشر شود
        </label>
      </div>
    </div>
  );
}

type Staff = { name: string; code: string; linked: boolean; messenger: string };

/** Staff of the appointment calendars link their own chat («/staff CODE») to hear about their own bookings. */
function StaffCard({ botId, handle }: { botId: string; handle: string }) {
  const [staff, setStaff] = useState<Staff[]>([]);
  const load = useCallback(() => { api<Staff[]>(`/bots/${botId}/staff`).then(setStaff).catch(() => {}); }, [botId]);
  useEffect(load, [load]);
  if (!staff.length) return null;
  async function reset(name: string) {
    if (!confirm(`اتصال «${name}» قطع و کد تازه ساخته شود؟`)) return;
    setStaff(await api<Staff[]>(`/bots/${botId}/staff/reset`, { body: { name } }));
  }
  return (
    <div className={card}>
      <h3 className="mb-1 font-bold">اعلان برای همکاران</h3>
      <p className="mb-3 text-sm leading-7 text-mute">هر همکار با فرستادن کد خودش به {handle} (در بله یا تلگرام)، نوبت‌های تازه و لغوشده‌ی خودش را همان‌جا دریافت می‌کند. شما همچنان همه‌ی اعلان‌ها را دریافت می‌کنید.</p>
      <div className="flex flex-col gap-2 text-sm">
        {staff.map((s) => (
          <div key={s.name} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-raised px-3 py-2">
            <span className="font-bold">{s.name}</span>
            {s.linked ? (
              <span className="flex items-center gap-3 text-mint">✓ متصل در {s.messenger === "tg" ? "تلگرام" : "بله"}
                <button onClick={() => reset(s.name)} className="text-xs text-mute underline hover:text-bad">قطع اتصال</button></span>
            ) : (
              <span dir="ltr" className="rounded-lg bg-ink px-3 py-1 font-mono text-fg">/staff {s.code}</span>
            )}
          </div>
        ))}
      </div>
      <button onClick={load} className="mt-2 text-sm text-saffron underline">بررسی دوباره</button>
    </div>
  );
}
