"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PENDING_KEY, api, getToken } from "@/lib/api";
import { ErrorNote, Icon, Logo, fa } from "@/components/ui";
import { BuilderTab } from "@/components/workspace/BuilderTab";
import { RecordsTab, StructureTab, TestsTab, VersionsTab } from "@/components/workspace/InspectorTabs";
import { PhoneSim } from "@/components/workspace/PhoneSim";
import { progressOf, type Bot, type ChatMsg, type Rec, type RunResult, type RunStatus, type TestRes, type Ver } from "@/components/workspace/model";

type Tab = "build" | "spec" | "tests" | "versions" | "records" | "try";
const TAB_LABEL: Record<Tab, string> = { build: "ساخت با ایجنت", spec: "ساختار", tests: "تست‌ها", versions: "نسخه‌ها", records: "ثبت‌ها", try: "امتحانش کن" };
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function Workspace() {
  const router = useRouter();
  const id = useSearchParams().get("id");
  const [bot, setBot] = useState<Bot | null>(null);
  const [tab, setTab] = useState<Tab>("build");
  const [error, setError] = useState("");

  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [lastCost, setLastCost] = useState<number | null>(null);
  const [stamped, setStamped] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const alive = useRef(true);
  const pendingSent = useRef(false);

  const [records, setRecords] = useState<Rec[]>([]);
  const [tests, setTests] = useState<TestRes[]>([]);
  const [versions, setVersions] = useState<Ver[]>([]);
  const [cost, setCost] = useState<number | null>(null);

  const loadRecords = useCallback(() => {
    api<Rec[]>(`/bots/${id}/records?sandbox=true`).then(setRecords).catch(() => {});
  }, [id]);

  const loadAll = useCallback(async () => {
    const b = await api<Bot>(`/bots/${id}`);
    setBot(b);
    const [msgs] = await Promise.all([
      api<ChatMsg[]>(`/bots/${id}/builder/messages`).then((m) => { setChat(m); return m; }).catch(() => [] as ChatMsg[]),
      api<{ results: TestRes[] }>(`/bots/${id}/tests`).then((t) => setTests(t.results)).catch(() => {}),
      api<Ver[]>(`/bots/${id}/versions`).then(setVersions).catch(() => {}),
      api<{ total_usd: number }>(`/bots/${id}/cost`).then((c) => setCost(c.total_usd)).catch(() => {}),
    ]);
    loadRecords();
    return { b, msgs };
  }, [id, loadRecords]);

  const sendBuild = useCallback(async (raw: string) => {
    const t = raw.trim();
    if (t.length < 2 || running) return;
    setInput("");
    setError("");
    setRunning(true);
    setStamped(false);
    setEvents([]);
    setTab("build");
    setChat((c) => [...c, { role: "user", content: t }]);
    try {
      const { run_id } = await api<{ run_id: number }>(`/bots/${id}/builder`, { body: { text: t } });
      for (let i = 0; i < 150 && alive.current; i++) {
        await sleep(1500);
        const r = await api<{ status: RunStatus; events: string[]; result: RunResult }>(`/bots/${id}/builder/runs/${run_id}`);
        setEvents(r.events);
        if (r.status !== "running") {
          setChat((c) => [...c, { role: "assistant", content: r.result.message }]);
          setLastCost(r.result.cost_usd ?? null);
          await loadAll();
          const res = r.result.tests ?? [];
          if (r.status === "done" && res.length && res.every((x) => x.passed)) setStamped(true);
          break;
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }, [id, running, loadAll]);

  useEffect(() => {
    alive.current = true;
    if (!getToken()) return void router.replace("/login/");
    if (!id) return void router.replace("/bots/");
    loadAll()
      .then(({ msgs }) => {
        // a description typed on /bots: send it once, as soon as the workspace opens
        const pending = sessionStorage.getItem(PENDING_KEY(id));
        if (pending && !msgs.length && !pendingSent.current) {
          pendingSent.current = true;
          sessionStorage.removeItem(PENDING_KEY(id));
          sendBuild(pending);
        }
      })
      .catch((e) => setError(e.message));
    return () => { alive.current = false; };
  }, [id, router, loadAll]); // eslint-disable-line react-hooks/exhaustive-deps

  function editPart(where: string) {
    setTab("build");
    setInput(`در بخش «${where}»: `);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  if (!bot) return <main className="p-10 text-center text-mute">{error || "در حال بارگذاری…"}</main>;
  const spec = bot.spec;
  const passed = tests.filter((t) => t.passed).length;
  const tabs: Tab[] = spec ? ["build", "spec", "tests", "versions", "records", "try"] : ["build"];
  const phoneTabs = tab === "build" || tab === "spec";
  const fieldLabels: Record<string, string> = { slot_label: "زمان" };
  for (const b of spec?.blocks ?? []) if ("fields" in b) for (const f of b.fields) fieldLabels[f.key] = f.label;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3.5 sm:gap-4 sm:px-6">
        <Logo href="/bots/" size="sm" />
        <span className="hidden h-6 w-px bg-line sm:block" />
        <div className="flex min-w-0 flex-[1_1_220px] flex-col">
          <span className="truncate text-[17px] font-extrabold">{bot.name}</span>
          <span className="text-xs text-mute">
            {running ? (spec ? `نسخه ${fa(bot.version)} · در حال ساخت نسخه‌ی بعد` : "در حال ساخت اولین نسخه") : spec ? `نسخه ${fa(bot.version)}${tests.length ? ` · ${fa(passed)}/${fa(tests.length)} تست موفق` : ""}` : "پیش‌نویس"}
          </span>
        </div>
        {cost !== null && cost > 0 && <span className="rounded-lg border border-line px-2.5 py-1.5 text-xs text-mute" dir="ltr" title="هزینه‌ی هوش مصنوعی این ربات تا الان">هزینه‌ی AI: <span dir="ltr">${cost.toFixed(4)}</span></span>}
      </header>
      <div className="h-[3px] bg-panel">
        {running && <div className="h-[3px] bg-saffron transition-all duration-700" style={{ width: `${Math.round(progressOf(events) * 100)}%` }} />}
      </div>

      {tabs.length > 1 && (
        <nav className="flex gap-1 overflow-x-auto border-b border-line px-4 pt-2.5 text-sm sm:px-6" role="tablist">
          {tabs.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
              className={`min-h-11 shrink-0 border-b-2 px-3.5 ${t === "try" ? "lg:hidden" : ""} ${tab === t ? "border-saffron font-bold text-fg" : "border-transparent text-mute hover:text-fg"}`}>
              {TAB_LABEL[t]}
              {t === "tests" && tests.length > 0 && <span className={`mr-1.5 text-xs ${passed === tests.length ? "text-mint" : "text-bad-soft"}`}>{fa(passed)}/{fa(tests.length)}</span>}
              {t === "records" && records.length > 0 && <span className="mr-1.5 text-xs text-mute">{fa(records.length)}</span>}
            </button>
          ))}
        </nav>
      )}

      <main className="flex flex-1 flex-wrap items-start gap-5 p-4 sm:p-6">
        <div className={`min-w-0 flex-[1_1_640px] flex-col gap-4 ${tab === "try" ? "hidden" : "flex"}`}>
          {error && <ErrorNote>{error}</ErrorNote>}
          {tab === "build" && (
            <BuilderTab spec={spec} tests={tests} chat={chat} events={events} running={running} lastCost={lastCost} stamped={stamped}
              input={input} setInput={setInput} inputRef={inputRef} onSend={sendBuild} />
          )}
          {tab === "spec" && spec && <StructureTab spec={spec} records={records} onEdit={editPart} />}
          {tab === "tests" && <TestsTab tests={tests} spec={spec} version={bot.version} />}
          {tab === "versions" && <VersionsTab versions={versions} spec={spec} />}
          {tab === "records" && spec && <RecordsTab records={records} spec={spec} />}
        </div>

        {spec ? (
          // kept mounted so the conversation survives tab switches
          <aside className={`w-full justify-center lg:w-auto lg:flex-[0_0_320px] ${tab === "try" ? "flex" : phoneTabs ? "hidden lg:flex" : "hidden"}`}>
            <PhoneSim botId={id!} version={bot.version} labels={fieldLabels} onActivity={loadRecords} />
          </aside>
        ) : (
          <aside className="hidden flex-[0_0_320px] lg:flex">
            <div className="flex h-[640px] w-[320px] flex-col items-center justify-center gap-3 rounded-[40px] border-8 border-line bg-panel p-8 text-center text-[13px] leading-7 text-dim">
              <Icon name="phone" size={40} strokeWidth={1.6} className="text-line-3" />
              ربات بعد از قبولی تست‌ها اینجا روشن می‌شود و می‌توانی امتحانش کنی.
            </div>
          </aside>
        )}
      </main>
    </div>
  );
}

export default function BotPage() {
  return (
    <Suspense fallback={<main className="p-10 text-center text-mute">در حال بارگذاری…</main>}>
      <Workspace />
    </Suspense>
  );
}
