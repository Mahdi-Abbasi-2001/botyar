"use client";
import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, getToken, type Action, type Button } from "@/lib/api";

type Msg = { from: "bot" | "me" | "admin"; text: string; buttons?: Button[] };
type Rec = { id: number; collection: string; data: Record<string, any>; created_at: string };

const BLOCK_LABEL: Record<string, string> = {
  message: "پیام", form: "فرم", booking: "رزرو", catalog_order: "سفارش", admin_notify: "اطلاع به مدیر",
};

function Workspace() {
  const router = useRouter();
  const id = useSearchParams().get("id");
  const [bot, setBot] = useState<any>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [tab, setTab] = useState<"spec" | "records">("spec");
  const [records, setRecords] = useState<Rec[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [session, setSession] = useState(() => Math.random().toString(36).slice(2, 10));
  const endRef = useRef<HTMLDivElement>(null);

  const loadRecords = useCallback(() => api<Rec[]>(`/bots/${id}/records?sandbox=true`).then(setRecords).catch(() => {}), [id]);

  const send = useCallback(async (t: string, shown?: string | null) => {
    setBusy(true);
    setError("");
    if (shown !== null) setMsgs((m) => [...m.map((x) => ({ ...x, buttons: undefined })), { from: "me", text: shown ?? t }]);
    try {
      const r = await api<{ actions: Action[] }>(`/bots/${id}/simulate`, { body: { session_id: session, text: t } });
      setMsgs((m) => [
        ...m,
        ...r.actions.map((a): Msg => a.type === "send" ? { from: "bot", text: a.text, buttons: a.buttons } : { from: "admin", text: a.text }),
      ]);
      loadRecords();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [id, session, loadRecords]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login/");
      return;
    }
    if (!id) {
      router.replace("/bots/");
      return;
    }
    api(`/bots/${id}`).then(setBot).catch((e) => setError(e.message));
    loadRecords();
  }, [id, router, loadRecords]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  async function resetSandbox() {
    await api(`/bots/${id}/simulate/reset`, { method: "POST", body: {} });
    setMsgs([]);
    setRecords([]);
    setSession(Math.random().toString(36).slice(2, 10));
  }
  const started = useRef("");
  useEffect(() => {
    if (bot && started.current !== session) { started.current = session; send("/start", null); }
  }, [bot, session]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!bot) return <main className="p-10 text-center text-slate-500">{error || "در حال بارگذاری..."}</main>;
  const spec = bot.spec;

  return (
    <main className="mx-auto max-w-6xl px-5 py-6">
      <header className="mb-6 flex items-center justify-between">
        <Link href="/bots/" className="text-sm text-indigo-700 hover:underline">← ربات‌های من</Link>
        <h1 className="text-lg font-extrabold">{bot.name} <span className="text-xs font-normal text-slate-500">نسخه {bot.version}</span></h1>
      </header>
      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        {/* simulator */}
        <section className="flex h-[640px] flex-col overflow-hidden rounded-3xl border border-slate-300 bg-white shadow-lg">
          <div className="flex items-center justify-between bg-indigo-600 px-4 py-3 text-white">
            <span className="font-bold">شبیه‌ساز گفتگو</span>
            <button onClick={resetSandbox} className="rounded-md bg-white/20 px-2 py-1 text-xs hover:bg-white/30">شروع مجدد</button>
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto bg-slate-100 p-3">
            {msgs.map((m, i) => (
              <div key={i} className={m.from === "me" ? "flex justify-start" : "flex justify-end"}>
                <div className="max-w-[85%]">
                  <div className={"whitespace-pre-line rounded-2xl px-3 py-2 text-sm leading-6 " + (
                    m.from === "me" ? "bg-indigo-600 text-white" : m.from === "admin" ? "border border-amber-300 bg-amber-50 text-amber-900" : "bg-white shadow-sm")}>
                    {m.from === "admin" && <div className="mb-1 text-xs font-bold">🔔 اعلان به مدیر</div>}
                    {m.text}
                  </div>
                  {m.buttons && m.buttons.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {m.buttons.map((b) => (
                        <button key={b.data} disabled={busy} onClick={() => send(b.data, b.text)}
                          className="rounded-full border border-indigo-300 bg-white px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-50 disabled:opacity-50">{b.text}</button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
          {error && <p className="bg-red-50 px-3 py-1 text-xs text-red-700">{error}</p>}
          <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) { send(text); setText(""); } }} className="flex gap-2 border-t border-slate-200 p-2">
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="پیام بنویسید..." className="flex-1 rounded-full border border-slate-300 px-4 py-2 text-sm outline-none focus:border-indigo-500" />
            <button disabled={busy} className="rounded-full bg-indigo-600 px-4 text-sm font-bold text-white disabled:opacity-50">ارسال</button>
          </form>
        </section>

        {/* inspector */}
        <section>
          <div className="mb-4 flex gap-2">
            {(["spec", "records"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)} className={"rounded-lg px-4 py-2 text-sm font-semibold " + (tab === t ? "bg-indigo-600 text-white" : "bg-white text-slate-700 hover:bg-slate-100")}>
                {t === "spec" ? "ساختار ربات" : `ثبت‌ها (${records.length})`}
              </button>
            ))}
          </div>
          {tab === "spec" ? (
            <div className="space-y-3">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="mb-1 text-xs text-slate-500">پیام خوش‌آمد</div>
                <div>{spec.welcome}</div>
                <div className="mb-1 mt-3 text-xs text-slate-500">منو</div>
                <div className="flex flex-wrap gap-2">{spec.menu.map((m: any) => <span key={m.label} className="rounded-full bg-indigo-50 px-3 py-1 text-sm text-indigo-700">{m.label}</span>)}</div>
              </div>
              {spec.blocks.map((b: any) => (
                <div key={b.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold">{BLOCK_LABEL[b.type]}</span>
                    <span className="font-bold">{b.title ?? b.id}</span>
                  </div>
                  {b.type === "message" && <p className="text-sm text-slate-600">{b.text}</p>}
                  {b.type === "booking" && <p className="text-sm text-slate-600">{b.slots.map((s: any) => `${s.label} (ظرفیت ${s.capacity})`).join(" • ")} {b.waitlist ? "• لیست انتظار فعال" : "• بدون لیست انتظار"}</p>}
                  {b.type === "catalog_order" && <p className="text-sm text-slate-600">{b.items.map((i: any) => `${i.name} ${i.price.toLocaleString("fa-IR")}`).join(" • ")}</p>}
                  {b.type === "form" && <p className="text-sm text-slate-600">{b.fields.map((f: any) => f.label).join(" • ")}</p>}
                  {b.type === "admin_notify" && <p className="text-sm text-slate-600">پس از تکمیل «{b.on}» به مدیر اطلاع داده می‌شود.</p>}
                </div>
              ))}
            </div>
          ) : records.length === 0 ? (
            <p className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500">هنوز ثبتی انجام نشده. در شبیه‌ساز یک رزرو یا سفارش انجام دهید.</p>
          ) : (
            <div className="space-y-2">
              {records.map((r) => (
                <div key={r.id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                  <div className="mb-1 text-xs text-slate-500">{r.collection} #{r.id}</div>
                  {Object.entries(r.data).filter(([k]) => !k.startsWith("_")).map(([k, v]) => (
                    <div key={k}><span className="text-slate-500">{k}: </span>{typeof v === "object" ? JSON.stringify(v) : String(v)}</div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

export default function BotPage() {
  return <Suspense fallback={<main className="p-10 text-center text-slate-500">در حال بارگذاری...</main>}><Workspace /></Suspense>;
}
