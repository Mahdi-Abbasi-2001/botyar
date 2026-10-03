"use client";
import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, getToken, type Action, type Button } from "@/lib/api";

type Msg = { from: "bot" | "me" | "admin"; text: string; buttons?: Button[] };
type Rec = { id: number; collection: string; data: Record<string, any>; created_at: string };
type TestRes = { name: string; passed: boolean; failures: string[]; transcript: { user: string; bot: string }[] };
type Ver = { version: number; note: string; created_at: string; diff: { path: string; before: any; after: any }[]; tests_passed: number; tests_total: number };
type ChatMsg = { role: "user" | "assistant"; content: string };
type Tab = "build" | "spec" | "tests" | "versions" | "records";

const TAB_LABEL: Record<Tab, string> = { build: "ساخت با ایجنت", spec: "ساختار", tests: "تست‌ها", versions: "نسخه‌ها", records: "ثبت‌ها" };
const BLOCK_LABEL: Record<string, string> = { message: "پیام", form: "فرم", booking: "رزرو", catalog_order: "سفارش", admin_notify: "اطلاع به مدیر" };
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const rid = () => Math.random().toString(36).slice(2, 10);
const show = (v: any) => (v === null || v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));

function Workspace() {
  const router = useRouter();
  const id = useSearchParams().get("id");
  const [bot, setBot] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("build");
  const [error, setError] = useState("");

  // simulator
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState(rid);
  const endRef = useRef<HTMLDivElement>(null);
  const started = useRef("");

  // builder
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [lastCost, setLastCost] = useState<number | null>(null);
  const alive = useRef(true);
  const chatEnd = useRef<HTMLDivElement>(null);

  // inspector data
  const [records, setRecords] = useState<Rec[]>([]);
  const [tests, setTests] = useState<TestRes[]>([]);
  const [versions, setVersions] = useState<Ver[]>([]);
  const [cost, setCost] = useState<number | null>(null);

  const loadRecords = useCallback(() => {
    api<Rec[]>(`/bots/${id}/records?sandbox=true`).then(setRecords).catch(() => {});
  }, [id]);

  const loadAll = useCallback(async () => {
    const b = await api(`/bots/${id}`);
    setBot(b);
    api<ChatMsg[]>(`/bots/${id}/builder/messages`).then(setChat).catch(() => {});
    api<{ results: TestRes[] }>(`/bots/${id}/tests`).then((t) => setTests(t.results)).catch(() => {});
    api<Ver[]>(`/bots/${id}/versions`).then(setVersions).catch(() => {});
    api<{ total_usd: number }>(`/bots/${id}/cost`).then((c) => setCost(c.total_usd)).catch(() => {});
    loadRecords();
    return b;
  }, [id, loadRecords]);

  useEffect(() => {
    alive.current = true;
    if (!getToken()) {
      router.replace("/login/");
      return;
    }
    if (!id) {
      router.replace("/bots/");
      return;
    }
    loadAll().then((b) => { if (!b.spec) setTab("build"); else setTab("spec"); }).catch((e) => setError(e.message));
    return () => { alive.current = false; };
  }, [id, router, loadAll]);

  // ---- simulator ----
  const send = useCallback(async (t: string, shown?: string | null) => {
    setBusy(true);
    setError("");
    if (shown !== null) setMsgs((m) => [...m.map((x) => ({ ...x, buttons: undefined })), { from: "me", text: shown ?? t }]);
    try {
      const r = await api<{ actions: Action[] }>(`/bots/${id}/simulate`, { body: { session_id: session, text: t } });
      setMsgs((m) => [...m, ...r.actions.map((a): Msg => (a.type === "send" ? { from: "bot", text: a.text, buttons: a.buttons } : { from: "admin", text: a.text }))]);
      loadRecords();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [id, session, loadRecords]);

  useEffect(() => {
    if (bot?.spec && started.current !== session + bot.version) {
      started.current = session + bot.version;
      setMsgs([]);
      send("/start", null);
    }
  }, [bot, session]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  async function resetSandbox() {
    await api(`/bots/${id}/simulate/reset`, { method: "POST", body: {} });
    setRecords([]);
    setSession(rid());
  }

  // ---- builder ----
  async function sendBuild(e: React.FormEvent) {
    e.preventDefault();
    const t = input.trim();
    if (t.length < 2 || running) return;
    setInput("");
    setError("");
    setRunning(true);
    setEvents([]);
    setChat((c) => [...c, { role: "user", content: t }]);
    try {
      const { run_id } = await api<{ run_id: number }>(`/bots/${id}/builder`, { body: { text: t } });
      for (let i = 0; i < 150 && alive.current; i++) {
        await sleep(2000);
        const r = await api<{ status: string; events: string[]; result: any }>(`/bots/${id}/builder/runs/${run_id}`);
        setEvents(r.events);
        if (r.status !== "running") {
          setChat((c) => [...c, { role: "assistant", content: r.result.message }]);
          setLastCost(r.result.cost_usd ?? null);
          await loadAll();
          if (r.status === "done") setTab("tests");
          break;
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [chat, events, running]);

  if (!bot) return <main className="p-10 text-center text-slate-500">{error || "در حال بارگذاری..."}</main>;
  const spec = bot.spec;
  const tabs: Tab[] = spec ? ["build", "spec", "tests", "versions", "records"] : ["build"];
  const failed = tests.filter((t) => !t.passed).length;

  return (
    <main className="mx-auto max-w-6xl px-5 py-6">
      <header className="mb-6 flex items-center justify-between">
        <Link href="/bots/" className="text-sm text-indigo-700 hover:underline">← ربات‌های من</Link>
        <h1 className="text-lg font-extrabold">
          {bot.name} {spec && <span className="text-xs font-normal text-slate-500">نسخه {bot.version}</span>}
          {cost !== null && <span className="mr-2 text-xs font-normal text-slate-400">هزینه هوش مصنوعی: ${cost.toFixed(4)}</span>}
        </h1>
      </header>
      {error && <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <div className={"grid gap-6 " + (spec ? "lg:grid-cols-[380px_1fr]" : "")}>
        {spec && (
          <section className="flex h-[640px] flex-col overflow-hidden rounded-3xl border border-slate-300 bg-white shadow-lg">
            <div className="flex items-center justify-between bg-indigo-600 px-4 py-3 text-white">
              <span className="font-bold">شبیه‌ساز گفتگو</span>
              <button onClick={resetSandbox} className="rounded-md bg-white/20 px-2 py-1 text-xs hover:bg-white/30">شروع مجدد</button>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto bg-slate-100 p-3">
              {msgs.map((m, i) => (
                <div key={i} className={m.from === "me" ? "flex justify-start" : "flex justify-end"}>
                  <div className="max-w-[85%]">
                    <div className={"whitespace-pre-line rounded-2xl px-3 py-2 text-sm leading-6 " + (m.from === "me" ? "bg-indigo-600 text-white" : m.from === "admin" ? "border border-amber-300 bg-amber-50 text-amber-900" : "bg-white shadow-sm")}>
                      {m.from === "admin" && <div className="mb-1 text-xs font-bold">🔔 اعلان به مدیر</div>}
                      {m.text}
                    </div>
                    {m.buttons && m.buttons.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {m.buttons.map((b) => (
                          <button key={b.data} disabled={busy} onClick={() => send(b.data, b.text)} className="rounded-full border border-indigo-300 bg-white px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-50 disabled:opacity-50">{b.text}</button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={endRef} />
            </div>
            <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) { send(text); setText(""); } }} className="flex gap-2 border-t border-slate-200 p-2">
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="پیام بنویسید..." className="flex-1 rounded-full border border-slate-300 px-4 py-2 text-sm outline-none focus:border-indigo-500" />
              <button disabled={busy} className="rounded-full bg-indigo-600 px-4 text-sm font-bold text-white disabled:opacity-50">ارسال</button>
            </form>
          </section>
        )}

        <section>
          <div className="mb-4 flex flex-wrap gap-2">
            {tabs.map((t) => (
              <button key={t} onClick={() => setTab(t)} className={"rounded-lg px-4 py-2 text-sm font-semibold " + (tab === t ? "bg-indigo-600 text-white" : "bg-white text-slate-700 hover:bg-slate-100")}>
                {TAB_LABEL[t]}
                {t === "tests" && tests.length > 0 && <span className={"mr-1 text-xs " + (failed ? "text-red-300" : "text-emerald-300")}>({tests.length - failed}/{tests.length})</span>}
                {t === "records" && ` (${records.length})`}
              </button>
            ))}
          </div>

          {tab === "build" && (
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="mb-3 max-h-[380px] space-y-2 overflow-y-auto">
                {chat.length === 0 && (
                  <p className="rounded-xl bg-indigo-50 p-4 text-sm leading-7 text-indigo-900">
                    رباتی که می‌خواهید را به فارسی ساده توضیح دهید؛ مثلاً: «برای کارگاه سفالگری‌ام ربات ثبت‌نام می‌خواهم. پنجشنبه‌ها دو سانس، ظرفیت هر سانس ۱۲ نفر.»
                    {spec ? " برای تغییر ربات فعلی هم همین‌جا بنویسید." : ""}
                  </p>
                )}
                {chat.map((m, i) => (
                  <div key={i} className={"whitespace-pre-line rounded-2xl px-4 py-2 text-sm leading-7 " + (m.role === "user" ? "mr-0 ml-10 bg-indigo-600 text-white" : "ml-0 mr-10 bg-slate-100")}>{m.content}</div>
                ))}
                {running && (
                  <div className="ml-0 mr-10 rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm">
                    <div className="mb-1 font-bold text-indigo-700">ایجنت در حال کار…</div>
                    <ul className="space-y-0.5 text-slate-700">{events.map((e, i) => <li key={i} className={e.startsWith("✗") ? "text-red-600" : ""}>• {e}</li>)}</ul>
                  </div>
                )}
                <div ref={chatEnd} />
              </div>
              {lastCost !== null && !running && <p className="mb-2 text-xs text-slate-400">هزینه این درخواست: ${lastCost.toFixed(4)}</p>}
              <form onSubmit={sendBuild} className="flex gap-2">
                <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={2} placeholder={spec ? "تغییر مورد نظر را بنویسید…" : "ربات خود را توضیح دهید…"} disabled={running}
                  className="flex-1 rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 disabled:bg-slate-50" />
                <button disabled={running || input.trim().length < 2} className="rounded-xl bg-indigo-600 px-5 font-bold text-white disabled:opacity-50">{running ? "…" : "ارسال"}</button>
              </form>
            </div>
          )}

          {tab === "spec" && spec && (
            <div className="space-y-3">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="mb-1 text-xs text-slate-500">پیام خوش‌آمد</div>
                <div>{spec.welcome}</div>
                <div className="mb-1 mt-3 text-xs text-slate-500">منو</div>
                <div className="flex flex-wrap gap-2">{spec.menu.map((m: any) => <span key={m.label} className="rounded-full bg-indigo-50 px-3 py-1 text-sm text-indigo-700">{m.label}</span>)}</div>
              </div>
              {spec.blocks.map((b: any) => (
                <div key={b.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="mb-1 flex items-center gap-2"><span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold">{BLOCK_LABEL[b.type]}</span><span className="font-bold">{b.title ?? b.id}</span></div>
                  {b.type === "message" && <p className="text-sm text-slate-600">{b.text}</p>}
                  {b.type === "booking" && <p className="text-sm text-slate-600">{b.slots.map((s: any) => `${s.label} (ظرفیت ${s.capacity})`).join(" • ")} {b.waitlist ? "• لیست انتظار فعال" : "• بدون لیست انتظار"}</p>}
                  {b.type === "catalog_order" && <p className="text-sm text-slate-600">{b.items.map((i: any) => `${i.name} ${i.price.toLocaleString("fa-IR")}`).join(" • ")}{b.min_total ? ` • حداقل سفارش ${b.min_total.toLocaleString("fa-IR")}` : ""}</p>}
                  {b.type === "form" && <p className="text-sm text-slate-600">{b.fields.map((f: any) => f.label).join(" • ")}</p>}
                  {b.type === "admin_notify" && <p className="text-sm text-slate-600">پس از تکمیل «{b.on}» به مدیر اطلاع داده می‌شود.</p>}
                </div>
              ))}
            </div>
          )}

          {tab === "tests" && (
            <div className="space-y-3">
              {tests.length === 0 && <p className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500">هنوز تستی اجرا نشده. ربات را با ایجنت بسازید.</p>}
              {tests.map((t, i) => (
                <details key={i} className="rounded-2xl border border-slate-200 bg-white p-4" open={!t.passed}>
                  <summary className="flex cursor-pointer items-center gap-2 font-semibold">
                    <span className={t.passed ? "text-emerald-600" : "text-red-600"}>{t.passed ? "✓" : "✗"}</span>{t.name}
                  </summary>
                  {t.failures.map((f, j) => <p key={j} className="mt-2 text-sm text-red-600">{f}</p>)}
                  <div className="mt-3 space-y-1 rounded-xl bg-slate-50 p-3 text-xs leading-6">
                    {t.transcript.map((s, j) => (
                      <div key={j}><span className="font-bold text-indigo-700">کاربر: </span><span dir="ltr" className="inline-block">{s.user}</span><br /><span className="font-bold text-slate-600">ربات: </span><span className="whitespace-pre-line">{s.bot}</span></div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          )}

          {tab === "versions" && (
            <div className="space-y-3">
              {versions.map((v) => (
                <div key={v.version} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="mb-1 flex items-center justify-between"><span className="font-bold">نسخه {v.version}</span><span className={"text-xs " + (v.tests_passed === v.tests_total ? "text-emerald-600" : "text-red-600")}>{v.tests_passed}/{v.tests_total} تست موفق</span></div>
                  {v.note && <p className="mb-2 text-sm text-slate-600">{v.note}</p>}
                  <ul className="space-y-1 text-xs">
                    {v.diff.slice(0, 12).map((d, i) => (
                      <li key={i} className="rounded bg-slate-50 px-2 py-1" dir="ltr"><span className="text-slate-500">{d.path}: </span><span className="text-red-600 line-through">{show(d.before).slice(0, 60)}</span> → <span className="text-emerald-700">{show(d.after).slice(0, 60)}</span></li>
                    ))}
                    {v.diff.length > 12 && <li className="text-slate-400">… و {v.diff.length - 12} تغییر دیگر</li>}
                  </ul>
                </div>
              ))}
            </div>
          )}

          {tab === "records" && (records.length === 0 ? (
            <p className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500">هنوز ثبتی انجام نشده. در شبیه‌ساز یک رزرو یا سفارش انجام دهید.</p>
          ) : (
            <div className="space-y-2">
              {records.map((r) => (
                <div key={r.id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
                  <div className="mb-1 text-xs text-slate-500">{r.collection} #{r.id}</div>
                  {Object.entries(r.data).filter(([k]) => !k.startsWith("_")).map(([k, v]) => <div key={k}><span className="text-slate-500">{k}: </span>{show(v)}</div>)}
                </div>
              ))}
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}

export default function BotPage() {
  return <Suspense fallback={<main className="p-10 text-center text-slate-500">در حال بارگذاری...</main>}><Workspace /></Suspense>;
}
