"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { PENDING_KEY, api, getToken, isPlanLimit } from "@/lib/api";
import { ErrorNote, Icon, Logo, PlanLimitNote, fa } from "@/components/ui";
import { BuilderTab } from "@/components/workspace/BuilderTab";
import { RecordsTab, StructureTab, TestsTab, VersionsTab } from "@/components/workspace/InspectorTabs";
import { PublishTab } from "@/components/workspace/PublishTab";
import { AnnounceTab } from "@/components/workspace/AnnounceTab";
import { CustomersTab } from "@/components/workspace/CustomersTab";
import { ChannelsTab } from "@/components/workspace/ChannelsTab";
import { DeliveryBanner } from "@/components/workspace/DeliveryBanner";
import { MediaTab } from "@/components/workspace/MediaTab";
import { InboxTab } from "@/components/workspace/InboxTab";
import { CatalogTab } from "@/components/workspace/CatalogTab";
import { PhoneSim } from "@/components/workspace/PhoneSim";
import { progressOf, type Bot, type ChatMsg, type Rec, type RunResult, type RunStatus, type TestRes, type Ver } from "@/components/workspace/model";

type Tab = "build" | "spec" | "tests" | "versions" | "publish" | "catalog" | "inbox" | "announce" | "customers" | "media" | "channels" | "records" | "try";
const TAB_LABEL: Record<Tab, string> = { build: "ساخت با ایجنت", spec: "ساختار", tests: "تست‌ها", versions: "نسخه‌ها", publish: "انتشار", catalog: "محصولات", inbox: "پیام‌ها", announce: "اطلاعیه", customers: "مشتریان", media: "فایل‌ها", channels: "کانال و گروه", records: "ثبت‌ها", try: "امتحانش کن" };

// The workspace in three jobs: make the bot, put it in front of customers, run it day to day.
type Group = "make" | "share" | "manage";
const GROUPS: { key: Group; label: string; icon: React.ComponentProps<typeof Icon>["name"]; tabs: Tab[] }[] = [
  { key: "make", label: "ساخت", icon: "tree", tabs: ["build", "spec", "tests", "versions", "catalog", "media"] },
  { key: "share", label: "انتشار", icon: "live", tabs: ["publish", "channels"] },
  { key: "manage", label: "مدیریت", icon: "list", tabs: ["records", "customers", "inbox", "announce"] },
];
const groupOf = (t: Tab): Group | null => GROUPS.find((g) => g.tabs.includes(t))?.key ?? null;

// Tabs that only fill up once real customers can reach the bot, and what each will show then.
const AFTER_PUBLISH: Partial<Record<Tab, { icon: React.ComponentProps<typeof Icon>["name"]; title: string; text: string }>> = {
  customers: { icon: "star", title: "مشتری‌ها بعد از انتشار اینجا می‌آیند",
    text: "هر کسی که در بله یا تلگرام با ربات‌ت گفت‌وگو کند اینجا دیده می‌شود: نام، آخرین پیام و تعداد دوستانی که دعوت کرده. می‌توانی جست‌وجو کنی، خروجی اکسل بگیری یا کسی را مسدود کنی." },
  announce: { icon: "bell", title: "اطلاعیه برای مشتری‌های ربات منتشرشده",
    text: "بعد از انتشار، برای همه‌ی کسانی که با ربات گفت‌وگو کرده‌اند پیام بفرست یا آن را برای بعد زمان‌بندی کن. روزی حداکثر ۳ اطلاعیه، و هر کس با /stop می‌تواند دیگر دریافت نکند." },
  channels: { icon: "chat", title: "کانال و گروه، بعد از انتشار",
    text: "ربات منتشرشده را به کانال یا گروهت اضافه کن تا عضویت اجباری در کانال، شمارش دعوت‌ها، بازنشر خودکار پست‌ها و مدیریت گروه (حذف لینک و فحش، اخطار و اخراج) کار کند." },
};

function AfterPublish({ tab, onPublish, testsOk }: { tab: Tab; onPublish: () => void; testsOk: boolean }) {
  const c = AFTER_PUBLISH[tab]!;
  return (
    <div className="flex flex-col items-start gap-4 rounded-[20px] border border-line bg-panel p-6 sm:p-8">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-raised text-saffron"><Icon name={c.icon} size={24} /></span>
      <h2 className="m-0 text-xl font-extrabold">{c.title}</h2>
      <p className="m-0 max-w-[640px] text-[15px] leading-8 text-fg-2">{c.text}</p>
      <ol className="m-0 flex list-none flex-wrap gap-2 p-0 text-sm text-mute">
        {testsOk
          ? <li className="rounded-full border border-mint-line bg-mint-bg px-3 py-1 text-mint-fg">۱. ساخته و تست شد ✓</li>
          : <li className="rounded-full border border-bad-line bg-bad-bg px-3 py-1 text-bad-fg">۱. اول تست‌ها باید قبول شوند</li>}
        <li className="rounded-full border border-amber-line bg-saffron/10 px-3 py-1 text-saffron">۲. انتشار روی بله یا تلگرام</li>
        <li className="rounded-full border border-line-2 px-3 py-1">۳. اینجا پر می‌شود</li>
      </ol>
      <button onClick={onPublish} className="flex min-h-12 items-center gap-2 rounded-xl bg-saffron px-5 font-extrabold text-ink hover:bg-saffron-hi">
        <Icon name="live" size={18} /> رفتن به انتشار
      </button>
    </div>
  );
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function Workspace() {
  const router = useRouter();
  const id = useSearchParams().get("id");
  const [bot, setBot] = useState<Bot | null>(null);
  const [tab, setTab] = useState<Tab>("build");
  const lastInGroup = useRef<Partial<Record<Group, Tab>>>({});  // each section reopens where the owner left it
  const beforeTry = useRef<Tab>("build");                          // phones: closing "try it" returns here
  const [error, setError] = useState("");
  const [limit, setLimit] = useState("");  // the monthly agent-request limit was reached

  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [lastCost, setLastCost] = useState<number | null>(null);
  const [stamped, setStamped] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const alive = useRef(true);
  const pendingSent = useRef(false);

  type PubInfo = { published: boolean; up_to_date?: boolean; tests_ok?: boolean; latest_version?: number };
  const [pub, setPub] = useState<{ bale: PubInfo | null; tg: PubInfo | null } | null>(null);
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

  /** Shows the live progress of a run and finishes it (also used to resume after a refresh). */
  const follow = useCallback(async (run_id: number) => {
    let misses = 0;
    try {
      for (let i = 0; i < 200 && alive.current; i++) {
        await sleep(1500);
        let r: { status: RunStatus; events: string[]; result: RunResult };
        try {
          r = await api<{ status: RunStatus; events: string[]; result: RunResult }>(`/bots/${id}/builder/runs/${run_id}`);
          misses = 0;
        } catch (e: any) {
          // the agent keeps working on the server; tolerate a few failed status checks
          if (++misses >= 5) {
            setError("ارتباط قطع شد، اما ایجنت روی سرور به کار ادامه می‌دهد. چند لحظه بعد صفحه را تازه کنید.");
            break;
          }
          continue;
        }
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
  }, [id, loadAll]);

  const sendBuild = useCallback(async (raw: string) => {
    const t = raw.trim();
    if (t.length < 2 || running) return;
    setInput("");
    setError("");
    setLimit("");
    setRunning(true);
    setStamped(false);
    setEvents([]);
    setTab("build");
    setChat((c) => [...c, { role: "user", content: t }]);
    let run_id: number;
    try {
      ({ run_id } = await api<{ run_id: number }>(`/bots/${id}/builder`, { body: { text: t } }));
    } catch (e: any) {
      // the request never reached the agent: undo the optimistic message and give the text back
      setChat((c) => c.slice(0, -1));
      setInput(t);
      if (isPlanLimit(e)) setLimit(e.message);
      else setError(e.message);
      setRunning(false);
      return;
    }
    await follow(run_id);
  }, [id, running, follow]);

  useEffect(() => {
    alive.current = true;
    if (!getToken()) return void router.replace("/login/");
    if (!id) return void router.replace("/bots/");
    loadAll()
      .then(async ({ msgs }) => {
        // the agent may still be working (the page was refreshed or reopened mid-build): pick the live view back up
        const active = await api<{ run_id: number | null; events: string[] }>(`/bots/${id}/builder/active`).catch(() => null);
        if (active?.run_id) {
          pendingSent.current = true;
          setRunning(true);
          setEvents(active.events);
          setTab("build");
          follow(active.run_id);
          return;
        }
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

  // where the bot is live; refreshed on every tab change so the header follows what the owner just did in «انتشار»
  const hasSpec = !!bot?.spec;
  useEffect(() => {
    if (!id || !hasSpec) return;
    Promise.all([
      api<PubInfo>(`/bots/${id}/publication`).catch(() => null),
      api<PubInfo & { enabled?: boolean }>(`/bots/${id}/telegram`).catch(() => null),
    ]).then(([bale, tg]) => setPub({ bale, tg }));
  }, [id, hasSpec, tab, bot?.version]);

  function editPart(where: string) {
    setTab("build");
    setInput(`در بخش «${where}»: `);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  if (!bot) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-10 text-center">
        <p className={error ? "text-lg font-bold" : "text-mute"}>{error || "در حال بارگذاری…"}</p>
        {error && <Link href="/bots/" className="min-h-11 rounded-xl bg-saffron px-5 py-2.5 font-bold text-ink">بازگشت به ربات‌های من</Link>}
      </main>
    );
  }
  const spec = bot.spec;
  const passed = tests.filter((t) => t.passed).length;
  const hasCatalog = !!spec?.blocks?.some((b: any) => b.type === "catalog_order" && b.source === "table");
  const hasMedia = !!spec?.blocks?.some((b: any) => b.type === "message" && b.media && b.media !== "none");
  const hasContact = !!spec?.blocks?.some((b: any) => b.type === "contact");
  const tabs: Tab[] = spec ? (["build", "spec", "tests", "versions", ...(hasCatalog ? ["catalog"] : []), "publish", ...(hasContact ? ["inbox"] : []), ...(hasMedia ? ["media"] : []), "announce", "customers", "channels", "records", "try"] as Tab[]) : ["build"];
  const phoneTabs = tab === "build" || tab === "spec";
  const group = groupOf(tab);
  if (group) lastInGroup.current[group] = tab;
  const liveOn = [pub?.bale?.published && "بله", pub?.tg?.published && "تلگرام"].filter(Boolean) as string[];
  const stale = !!((pub?.bale?.published && !pub.bale.up_to_date) || (pub?.tg?.published && !pub.tg.up_to_date));
  const live: "live" | "stale" | "off" | null = !pub ? null : liveOn.length ? (stale ? "stale" : "live") : "off";
  const goPublish = () => setTab("publish");
  const fieldLabels: Record<string, string> = { slot_label: "زمان" };
  for (const b of spec?.blocks ?? []) if ("fields" in b) for (const f of b.fields) fieldLabels[f.key] = f.label;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3.5 sm:gap-4 sm:px-6">
        <Logo href="/bots/" size="sm" />
        <span className="hidden h-6 w-px bg-line sm:block" />
        <div className="flex min-w-0 flex-1 basis-0 flex-col">
          <span className="truncate text-[17px] font-extrabold">{bot.name}</span>
          <span className="text-xs text-mute">
            {running ? (spec ? `نسخه ${fa(bot.version)} · در حال ساخت نسخه‌ی بعد` : "در حال ساخت اولین نسخه") : spec ? `نسخه ${fa(bot.version)}${tests.length ? ` · ${fa(passed)}/${fa(tests.length)} تست موفق` : ""}` : "پیش‌نویس"}
          </span>
        </div>
        {cost !== null && cost > 0 && <span className="hidden rounded-lg border border-line px-2.5 py-1.5 text-xs text-mute xl:inline" dir="ltr" title="هزینه‌ی هوش مصنوعی این ربات تا الان">هزینه‌ی AI: <span dir="ltr">${cost.toFixed(4)}</span></span>}
        {/* where the bot stands with customers, and the one-click way forward */}
        {spec && live === "live" && (
          <button onClick={goPublish} className="hidden min-h-11 items-center gap-2 rounded-xl bg-mint-bg px-3.5 text-sm text-mint-fg hover:bg-mint-bg/70 sm:flex">
            <span className="anim-live h-2 w-2 rounded-full bg-mint" /> زنده روی {liveOn.join(" و ")}
          </button>
        )}
        {spec && live === "stale" && (
          <button onClick={goPublish} disabled={running} className="hidden min-h-11 items-center gap-2 rounded-xl border border-amber-line bg-saffron/10 px-3.5 text-sm font-bold text-saffron hover:bg-saffron/20 disabled:opacity-50 sm:flex">
            <Icon name="live" size={16} /> انتشار نسخه‌ی {fa(bot.version)}
          </button>
        )}
        {spec && live === "off" && (
          <>
            <span className="hidden text-sm text-mute md:inline">هنوز منتشر نشده</span>
            <button onClick={goPublish} disabled={running} className="hidden min-h-11 items-center gap-2 rounded-xl bg-saffron px-4 text-sm font-extrabold text-ink hover:bg-saffron-hi disabled:opacity-50 sm:flex">
              <Icon name="live" size={16} /> انتشار برای مشتری‌ها
            </button>
          </>
        )}
        {/* on phones the simulator is not beside the page, so "try it" lives in the header where it is always visible */}
        {spec && (
          <button aria-pressed={tab === "try"} onClick={() => setTab(tab === "try" ? beforeTry.current : (beforeTry.current = tab, "try"))}
            className={`flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3.5 text-sm font-bold lg:hidden ${tab === "try" ? "bg-mint text-ink" : "border border-mint-line bg-mint-bg text-mint-fg"}`}>
            <Icon name="phone" size={16} /> {tab === "try" ? "بستن" : TAB_LABEL.try}
          </button>
        )}
      </header>
      <div className="h-[3px] bg-panel">
        {running && <div className="h-[3px] bg-saffron transition-all duration-700" style={{ width: `${Math.round(progressOf(events) * 100)}%` }} />}
      </div>

      {tabs.length > 1 && (
        <div className="border-b border-line">
          <div role="tablist" aria-label="بخش‌های ربات" className="flex items-center gap-2 overflow-x-auto px-4 pt-3 sm:px-6">
            {GROUPS.map((g) => {
              const inGroup = g.tabs.filter((t) => tabs.includes(t));
              if (!inGroup.length) return null;
              const on = group === g.key;
              return (
                <button key={g.key} role="tab" aria-selected={on}
                  onClick={() => setTab(lastInGroup.current[g.key] && inGroup.includes(lastInGroup.current[g.key]!) ? lastInGroup.current[g.key]! : inGroup[0])}
                  className={`flex min-h-11 shrink-0 items-center gap-2 rounded-xl border px-4 text-sm ${on ? "border-saffron bg-saffron/10 font-bold text-fg" : "border-line-2 text-fg-2 hover:border-line-3 hover:text-fg"}`}>
                  <Icon name={g.icon} size={16} className={on ? "text-saffron" : "text-mute"} />
                  {g.label}
                  {g.key === "make" && tests.length > 0 && <span className={`text-xs ${passed === tests.length ? "text-mint" : "text-bad-soft"}`}>{fa(passed)}/{fa(tests.length)}</span>}
                  {g.key === "share" && live === "live" && <span className="h-2 w-2 rounded-full bg-mint" title={`زنده روی ${liveOn.join(" و ")}`} />}
                  {g.key === "share" && live === "stale" && <span className="h-2 w-2 rounded-full bg-saffron" title="نسخه‌ی جدید منتشر نشده" />}
                  {g.key === "manage" && records.length > 0 && <span className="rounded-full bg-raised px-1.5 text-xs text-fg-2">{fa(records.length)}</span>}
                </button>
              );
            })}
          </div>
          {group && (
            <nav role="tablist" aria-label="صفحه‌های این بخش" className="flex gap-1 overflow-x-auto px-4 pt-1 text-sm sm:px-6">
              {GROUPS.find((g) => g.key === group)!.tabs.filter((t) => tabs.includes(t)).map((t) => (
                <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                  className={`min-h-11 shrink-0 border-b-2 px-3.5 ${tab === t ? "border-saffron font-bold text-fg" : "border-transparent text-mute hover:text-fg"}`}>
                  {TAB_LABEL[t]}
                  {t === "tests" && tests.length > 0 && <span className={`mr-1.5 text-xs ${passed === tests.length ? "text-mint" : "text-bad-soft"}`}>{fa(passed)}/{fa(tests.length)}</span>}
                  {t === "records" && records.length > 0 && <span className="mr-1.5 text-xs text-mute">{fa(records.length)}</span>}
                </button>
              ))}
            </nav>
          )}
        </div>
      )}

      <main className="flex flex-1 flex-wrap items-start gap-5 p-4 sm:p-6">
        <div className={`min-w-0 flex-[1_1_640px] flex-col gap-4 ${tab === "try" ? "hidden" : "flex"}`}>
          {error && <ErrorNote>{error}</ErrorNote>}
          {limit && tab === "build" && <PlanLimitNote text={limit} />}
          {spec && tab !== "build" && <DeliveryBanner botId={id!} />}
          {tab === "build" && (
            <BuilderTab spec={spec} tests={tests} chat={chat} events={events} running={running} lastCost={lastCost} stamped={stamped}
              input={input} setInput={setInput} inputRef={inputRef} onSend={sendBuild} />
          )}
          {tab === "spec" && spec && <StructureTab spec={spec} records={records} onEdit={editPart} />}
          {tab === "tests" && <TestsTab tests={tests} spec={spec} version={bot.version} />}
          {tab === "versions" && <VersionsTab versions={versions} spec={spec} />}
          {tab === "catalog" && spec && <CatalogTab botId={id!} />}
          {live === "off" && AFTER_PUBLISH[tab] && <AfterPublish tab={tab} onPublish={goPublish} testsOk={pub?.bale?.tests_ok !== false} />}
          {tab === "channels" && spec && live !== "off" && <ChannelsTab botId={id!} />}
          {tab === "media" && spec && <MediaTab botId={id!} />}
          {tab === "customers" && spec && live !== "off" && <CustomersTab botId={id!} />}
          {tab === "announce" && spec && live !== "off" && <AnnounceTab botId={id!} />}
          {tab === "inbox" && spec && <InboxTab botId={id!} />}
          {tab === "publish" && spec && <PublishTab botId={id!} />}
          {tab === "records" && spec && <RecordsTab records={records} spec={spec} botId={id!} onChanged={loadRecords} />}
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
