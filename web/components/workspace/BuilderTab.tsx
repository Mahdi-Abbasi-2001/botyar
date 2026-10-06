"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Icon, Stamp, fa } from "../ui";
import { BLOCK_KIND, blockTitle, parseQuestions, toSteps, type ChatMsg, type Spec, type TestRes } from "./model";

const NEW_EXAMPLES = [
  "برای کلینیک دندانپزشکی‌ام یک ربات نوبت‌دهی می‌خواهم. شنبه ساعت ۹ صبح و دوشنبه ساعت ۵ عصر، هر کدام با ظرفیت ۸ نفر. نام و شماره‌ی موبایل بیمار را بگیرد و هر نوبت که ثبت شد به من خبر بدهد.",
  "برای کافه‌ام یک ربات سفارش می‌خواهم با لاته، اسپرسو و کیک. هر سفارش که ثبت شد به من اطلاع بدهد.",
];
const CHANGE_EXAMPLES = ["وقتی ظرفیت پر شد، لیست انتظار داشته باشد", "پیام خوش‌آمد صمیمی‌تر شود", "یک سؤال «سن» هم به فرم اضافه شود"];

type Props = {
  spec: Spec | null;
  tests: TestRes[];
  chat: ChatMsg[];
  events: string[];
  running: boolean;
  lastCost: number | null;
  stamped: boolean;
  input: string;
  setInput: (s: string) => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  onSend: (text: string) => void;
  botId: string;
  catalog: { total: number; sample: boolean } | null;  // the product table, when the bot has one
  onImport: () => void;                                 // opens «محصولات»
};

// Height left for the chat once the header, tab bar and page padding are drawn.
const PANEL_H = "h-[calc(100dvh-11rem)] min-h-[480px]";

export function BuilderTab(p: Props) {
  const lastQ = !p.running && p.chat.length ? parseQuestions(p.chat[p.chat.length - 1].content) : null;
  const scroller = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const gliding = useRef(false);  // a smooth scroll we started is under way: its in-between positions are not the owner scrolling up
  const ready = useRef(false);    // the first paint jumps straight to the end; after that every move glides
  const [unseen, setUnseen] = useState(false);

  const toBottom = (smooth = true) => {
    const el = scroller.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 2) return;
    gliding.current = smooth;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    setUnseen(false);
  };
  const follow = () => {
    toBottom(ready.current);
    // the history arrives after mount: stay instant until there is something to scroll through
    const el = scroller.current;
    if (el && el.scrollHeight > el.clientHeight + 4) ready.current = true;
  };

  // Stay pinned to the latest message whenever the content grows (messages loading in, new progress
  // steps, cards expanding) — unless the owner scrolled up to read something.
  const content = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current, inner = content.current;
    if (!el || !inner) return;
    let last = inner.offsetHeight;
    const ro = new ResizeObserver(() => {
      const grew = inner.offsetHeight > last;
      last = inner.offsetHeight;
      if (atBottom.current) follow();
      else if (grew) setUnseen(true);
    });
    ro.observe(inner);
    return () => ro.disconnect();
  }, []);
  // and directly after each new message / progress step (doesn't wait for a rendering frame)
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (atBottom.current) follow();
    else setUnseen(true);
  }, [p.chat.length, p.events.length, !!lastQ]); // eslint-disable-line react-hooks/exhaustive-deps
  // sending a message always brings you back down
  useEffect(() => {
    if (p.running) { atBottom.current = true; toBottom(); }
  }, [p.running]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-wrap items-start gap-5">
      <section className={`relative flex min-w-0 flex-[1_1_360px] flex-col overflow-hidden rounded-[20px] border border-line bg-ink ${PANEL_H}`}>
        <div ref={scroller} onScroll={(e) => {
          const el = e.currentTarget;
          const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          if (gliding.current) { if (near) gliding.current = false; return; }
          atBottom.current = near;
          if (near) setUnseen(false);
        }} onWheel={() => { gliding.current = false; }} onTouchStart={() => { gliding.current = false; }}
          className="flex-1 overflow-y-auto overscroll-contain">
        <div ref={content} className="flex flex-col gap-3.5 p-3.5">
        {p.chat.length === 0 && !p.running && (
          <div className="flex flex-col gap-3 rounded-2xl border border-line bg-panel p-4">
            <span className="text-sm leading-7 text-fg-2">{p.spec ? "هر تغییری می‌خواهید همین‌جا بنویسید. بات‌یار آن را اعمال می‌کند و همه‌ی تست‌ها را دوباره اجرا می‌کند." : "ربات خود را مثل یک پیام معمولی توضیح دهید؛ برای نمونه:"}</span>
            <div className="flex flex-col gap-2">
              {(p.spec ? CHANGE_EXAMPLES : NEW_EXAMPLES).map((x) => (
                <button key={x} onClick={() => { p.setInput(x); p.inputRef.current?.focus(); }}
                  className="min-h-11 rounded-xl border border-line-2 bg-raised px-3.5 py-2 text-right text-[13px] leading-7 text-fg-2 hover:border-saffron hover:text-fg">{x}</button>
              ))}
            </div>
          </div>
        )}

        {p.chat.map((m, i) => {
          const qs = m.role === "assistant" ? parseQuestions(m.content) : null;
          if (qs && i === p.chat.length - 1 && lastQ) return <QuestionCards key={i} questions={qs} onSend={p.onSend} />;
          if (qs) return <PastQuestions key={i} questions={qs} />;
          // something the agent can't build: the whole request (declined), or a detail a finished build left out.
          // Either way the owner can send it to the team as a support ticket.
          if (m.role === "assistant" && m.content.includes(DECLINE_MARK)) {
            const asked = p.chat.slice(0, i).reverse().find((x) => x.role === "user")?.content ?? "";
            if (m.content.startsWith(DECLINE_MARK)) {
              const why = m.content.slice(DECLINE_MARK.length);
              return <TicketOffer key={i} botId={p.botId} message={`🚧 ${why}`} context={why} request={asked} />;
            }
            const [built, missing] = m.content.split("\n" + DECLINE_MARK);
            return <TicketOffer key={i} botId={p.botId} message={built} missing={missing} context={missing} request={`${missing}\n\nدرخواست اصلی: ${asked}`} />;
          }
          return m.role === "user" ? (
            <div key={i} className="anim-rise max-w-[92%] self-start whitespace-pre-line rounded-[14px_14px_4px_14px] bg-raised px-3.5 py-3 text-sm leading-8">{m.content}</div>
          ) : (
            <div key={i} className="anim-rise flex max-w-[94%] gap-2 self-end">
              <span className="max-w-full whitespace-pre-line rounded-[14px_14px_14px_4px] border border-line bg-panel px-3.5 py-3 text-sm leading-8">{m.content}</span>
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] bg-saffron text-sm font-black text-ink">ب</span>
            </div>
          );
        })}

        {(p.running || (p.events.length > 0 && !lastQ)) && <Timeline events={p.events} running={p.running} />}
        {p.lastCost !== null && !p.running && <span className="text-xs text-dim">هزینه‌ی هوش مصنوعی این درخواست: <span dir="ltr">${p.lastCost.toFixed(4)}</span></span>}
        {/* the shop was built with invented demo products (so it can be tested): the owner's real list is the next step */}
        {p.catalog?.sample && !p.running && !lastQ && (
          <div className="anim-rise flex flex-col gap-2.5 rounded-2xl border border-amber-line bg-amber-bg p-4 text-sm leading-7">
            <strong className="text-amber-fg">قدم بعد: فهرست واقعی محصولات</strong>
            <span className="text-fg-2">
              ربات با {fa(p.catalog.total)} محصول نمونه ساخته شد تا بتوانید همین حالا امتحانش کنید. فهرست محصولات فروشگاه خود را
              از فایل اکسل یا CSV، یک جدول کپی‌شده یا عکس فهرست قیمت وارد کنید تا جای نمونه‌ها را بگیرد.
            </span>
            <button type="button" onClick={p.onImport} className="min-h-11 self-start rounded-xl bg-saffron px-5 font-bold text-ink hover:bg-saffron-hi">وارد کردن محصولات</button>
          </div>
        )}
        </div>
        </div>

        {unseen && (
          <button onClick={() => toBottom()} className="anim-rise absolute bottom-24 left-1/2 flex min-h-10 -translate-x-1/2 items-center gap-1.5 rounded-full border border-saffron bg-panel px-4 text-[13px] text-saffron shadow-lg shadow-black/40">
            پیام‌های تازه <span aria-hidden>↓</span>
          </button>
        )}

        {!lastQ && (
          <form onSubmit={(e) => { e.preventDefault(); p.onSend(p.input); }} className="m-2.5 mt-0 flex shrink-0 items-end gap-2 rounded-2xl border border-line-2 bg-panel p-2">
            <label htmlFor="agent-in" className="sr-only">{p.spec ? "تغییر بعدی" : "توضیح ربات"}</label>
            <textarea id="agent-in" ref={p.inputRef} value={p.input} rows={2} disabled={p.running}
              onChange={(e) => p.setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); p.onSend(p.input); } }}
              placeholder={p.running ? "بات‌یار در حال کار است…" : p.spec ? "تغییر بعدی را بنویسید…" : "ربات خود را توضیح دهید…"}
              className="min-w-0 flex-1 resize-none bg-transparent px-2.5 py-2 text-sm leading-7 outline-none placeholder:text-dim disabled:opacity-60" />
            <button disabled={p.running || p.input.trim().length < 2} className="min-h-11 rounded-xl bg-saffron px-4 text-sm font-extrabold text-ink hover:bg-saffron-hi disabled:opacity-40">ارسال</button>
          </form>
        )}
      </section>

      <MiniMap spec={p.spec} tests={p.tests} running={p.running} stamped={p.stamped} catalog={p.catalog} />
    </div>
  );
}

function Timeline({ events, running }: { events: string[]; running: boolean }) {
  const steps = toSteps(events);
  return (
    <div className="flex flex-col rounded-2xl border border-line bg-panel p-4">
      <div className="flex items-center gap-2 pb-2.5 text-[13px] text-mute">
        <span className={`h-2 w-2 rounded-full ${running ? "anim-live bg-saffron" : "bg-mint"}`} />
        {running ? "بات‌یار در حال کار است" : "کار بات‌یار تمام شد"}
      </div>
      {steps.map((s, i) => {
        const active = running && i === steps.length - 1;
        const ring = s.fail ? "border-bad bg-bad" : active ? "border-saffron" : "border-mint bg-mint";
        return (
          <div key={i} className="anim-rise flex gap-3">
            <div className="flex flex-col items-center">
              <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 text-xs font-black text-ink ${ring}`}>{s.fail ? "!" : active ? "" : "✓"}</span>
              {i < steps.length - 1 && <span className="min-h-3.5 w-0.5 flex-1 bg-line" />}
            </div>
            <div className="flex min-w-0 flex-col gap-1.5 pb-3">
              <span className={`text-sm ${s.fail ? "text-bad-fg" : active ? "font-bold text-fg" : "text-fg-2"}`}>{fa(s.text)}</span>
              {s.subs.map((x, j) => (
                <span key={j} className="anim-shake rounded-[10px] border border-bad-line bg-bad-bg px-2.5 py-2 text-[13px] leading-7 text-bad-fg">✗ {x}</span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function QuestionCards({ questions, onSend }: { questions: string[]; onSend: (t: string) => void }) {
  const [answers, setAnswers] = useState<string[]>(() => questions.map(() => ""));
  const filled = answers.filter((a) => a.trim()).length;
  const submit = (fill: boolean) => {
    const a = answers.map((x) => x.trim() || (fill ? "هر طور صلاح می‌دانی" : ""));
    onSend(questions.map((q, i) => `${fa(i + 1)}. ${q}\nجواب: ${a[i]}`).join("\n"));
  };
  return (
    <div className="anim-rise flex flex-col gap-3">
      <div className="flex gap-2 self-end">
        <span className="rounded-[14px_14px_14px_4px] border border-line bg-panel px-3.5 py-2.5 text-sm leading-7">پیش از ساخت، {fa(questions.length)} سؤال کوتاه دارم.</span>
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] bg-saffron text-sm font-black text-ink">ب</span>
      </div>
      {questions.map((q, i) => {
        const active = i === answers.findIndex((a) => !a.trim());
        return (
          <label key={i} className={`flex flex-col gap-2.5 rounded-2xl border bg-panel p-3.5 ${active ? "border-saffron" : "border-line"}`}>
            <span className="flex gap-2"><span className="shrink-0 text-xs text-mute">{fa(i + 1)} از {fa(questions.length)}</span><span className="text-[15px] font-bold leading-7">{q}</span></span>
            <input value={answers[i]} onChange={(e) => setAnswers((a) => a.map((x, j) => (j === i ? e.target.value : x)))}
              placeholder="پاسخ شما…" className="min-h-11 rounded-xl border border-line-2 bg-ink px-3 text-sm outline-none placeholder:text-dim focus:border-saffron" />
          </label>
        );
      })}
      <button onClick={() => submit(false)} disabled={filled < questions.length}
        className="min-h-[52px] rounded-2xl bg-saffron font-extrabold text-ink hover:bg-saffron-hi disabled:bg-raised disabled:text-mute">
        {filled < questions.length ? `${fa(questions.length - filled)} سؤال باقی مانده` : "ساخت با همین پاسخ‌ها"}
      </button>
      <button onClick={() => submit(true)} className="min-h-11 text-[13px] text-mute hover:text-fg">بقیه را به انتخاب بات‌یار بگذار</button>
    </div>
  );
}

function PastQuestions({ questions }: { questions: string[] }) {
  return (
    <div className="max-w-[94%] self-end rounded-[14px_14px_14px_4px] border border-line bg-panel px-3.5 py-3 text-sm leading-8 text-fg-2">
      <span className="text-xs text-mute">بات‌یار پرسید:</span>
      <ol className="m-0 list-inside list-decimal p-0">{questions.map((q, i) => <li key={i}>{q}</li>)}</ol>
    </div>
  );
}

function MiniMap({ spec, tests, running, stamped, catalog }: { spec: Spec | null; tests: TestRes[]; running: boolean; stamped: boolean; catalog: Props["catalog"] }) {
  const passed = tests.filter((t) => t.passed).length;
  return (
    <section className={`bp relative flex min-w-0 flex-[1.3_1_420px] flex-col gap-3.5 overflow-y-auto overscroll-contain rounded-[20px] border border-line bg-ink-2 p-5 lg:max-h-[calc(100dvh-11rem)]`}>
      <div className="flex justify-between text-[13px] text-mute">
        <span>نقشه‌ی ربات</span>
        {running && spec && <span className="text-saffron">در حال اعمال تغییر…</span>}
      </div>
      {!spec ? (
        <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 text-center text-[13px] leading-7 text-dim">
          <Icon name="tree" size={40} strokeWidth={1.4} className="text-line-3" />
          {running ? "بات‌یار در حال طراحی ساختار ربات است…" : "نقشه‌ی ربات پس از اولین ساخت اینجا نمایش داده می‌شود."}
        </div>
      ) : (
        <div className={`flex flex-col gap-3 transition-opacity ${running ? "opacity-60" : ""}`}>
          <div className="flex flex-col gap-2 rounded-2xl border border-line-2 bg-panel p-3.5">
            <span className="text-xs text-mute">پیام خوش‌آمد و منو</span>
            <span className="text-sm leading-7">{spec.welcome}</span>
            <div className="flex flex-wrap gap-1.5">{spec.menu.map((m) => <span key={m.label} className="rounded-lg border border-line-3 px-2.5 py-0.5 text-[13px]">{m.label}</span>)}</div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {spec.blocks.map((b) => (
              <div key={b.id} className={`flex flex-col gap-1 rounded-2xl border p-3.5 ${b.type === "admin_notify" ? "border-amber-line bg-amber-bg" : b.type === "booking" || b.type === "catalog_order" ? "border-saffron bg-panel" : "border-line-2 bg-panel"}`}>
                <span className={`text-xs ${b.type === "admin_notify" ? "text-amber-fg/80" : "text-mute"}`}>{BLOCK_KIND[b.type]}</span>
                <span className="text-sm leading-7">{blockTitle(b)}</span>
                {b.type === "faq" && <span className="text-xs text-mute">{fa(b.entries.length)} پرسش و پاسخ</span>}
                {b.type === "booking" && <span className="text-xs text-mute">{b.schedule ? `ساعت کاری · نوبت ${fa(b.schedule.duration_minutes)} دقیقه${b.schedule.staff.length ? ` · ${fa(b.schedule.staff.length)} نفر` : ""}` : `${fa(b.slots.length)} زمان${b.waitlist ? " · لیست انتظار" : ""}`}</span>}
                {b.type === "catalog_order" && (
                  b.source === "table"
                    ? <span className={`text-xs ${catalog?.sample ? "text-amber-fg" : "text-mute"}`}>{catalog ? `${fa(catalog.total)} محصول${catalog.sample ? " نمونه" : ""}` : "فهرست محصولات"}</span>
                    : <span className="text-xs text-mute">{fa(b.items.length)} آیتم</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      {tests.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="text-[13px] text-mute">سناریوهای تست نسخه‌ی فعلی · {fa(passed)} از {fa(tests.length)} موفق</span>
          {tests.map((t) => (
            <div key={t.name} className={`flex items-center gap-2.5 rounded-[10px] border bg-panel px-3 py-2 text-[13px] ${t.passed ? "border-line" : "border-bad-line"}`}>
              <span className={`h-2 w-2 shrink-0 rounded-full ${t.passed ? "bg-mint" : "bg-bad"}`} />
              <span className="flex-1">{t.name}</span>
              <span className={`font-bold ${t.passed ? "text-mint" : "text-bad-soft"}`}>{t.passed ? "قبول" : "ناموفق"}</span>
            </div>
          ))}
        </div>
      )}
      {stamped && <Stamp settle sub={`${fa(passed)} از ${fa(tests.length)} · قبول`} size={156} className="absolute left-7 top-16" />}
    </section>
  );
}

const DECLINE_MARK = "🚧 ";  // api/app/agent.py: starts a declined request, or the line of a build listing what was left out

/** The agent can't build something the owner asked for (`missing`: one detail of an otherwise finished bot);
 *  the owner can hand it to the Botyar team as a support ticket in one step. */
function TicketOffer({ botId, message, missing, context, request }: { botId: string; message: string; missing?: string; context: string; request: string }) {
  const [writing, setWriting] = useState(false);
  const [text, setText] = useState(request);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const t = await api<{ id: number }>("/tickets", { body: { kind: "unsupported", text, bot_id: Number(botId), context } });
      setDone(t.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="anim-rise flex max-w-[94%] gap-2 self-end">
      <div className="flex min-w-0 flex-col gap-3 rounded-[14px_14px_14px_4px] border border-line bg-panel px-3.5 py-3 text-sm leading-8">
        <span className="whitespace-pre-line">{message}</span>
        <div className="flex flex-col gap-2.5 rounded-xl border border-line-2 bg-raised p-3">
          {missing && <span><b className="text-amber-fg">هنوز پشتیبانی نمی‌شود:</b> {missing}</span>}
          {done !== null ? (
            <span className="text-mint-fg">
              درخواست شما با شماره‌ی {fa(done)} برای تیم بات‌یار ثبت شد. پاسخ را در <Link href="/support/" className="font-bold underline">پشتیبانی</Link> می‌بینید.
            </span>
          ) : writing ? (
            <>
              <label htmlFor="decline-request" className="text-xs text-mute">این درخواست برای تیم بات‌یار ارسال می‌شود؛ اگر لازم است کامل‌ترش کنید:</label>
              <textarea id="decline-request" autoFocus rows={3} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)}
                className="resize-y rounded-xl border border-line-2 bg-ink p-2.5 leading-7 outline-none focus:border-saffron" />
              {error && <span className="text-bad-soft">{error}</span>}
              <div className="flex gap-2">
                <button type="button" disabled={busy || text.trim().length < 5} onClick={submit} className="min-h-10 rounded-xl bg-saffron px-4 font-bold text-ink hover:bg-saffron-hi disabled:opacity-50">
                  {busy ? "در حال ثبت…" : "ثبت درخواست"}
                </button>
                <button type="button" onClick={() => setWriting(false)} className="min-h-10 rounded-xl border border-line-2 px-4 text-fg-2 hover:text-fg">انصراف</button>
              </div>
            </>
          ) : (
            <>
              <span className="text-fg-2">{missing ? "ربات بدون این مورد ساخته شد. اگر برای کسب‌وکارتان مهم است" : "اگر این نوع ربات برای کسب‌وکارتان مهم است"}، درخواستتان را برای تیم بات‌یار بفرستید تا بررسی شود؛ پاسخ را در بخش «پشتیبانی» می‌بینید.</span>
              <button type="button" onClick={() => setWriting(true)} className="min-h-10 self-start rounded-xl border border-saffron px-4 font-bold text-saffron hover:bg-saffron/10">ثبت درخواست برای تیم بات‌یار</button>
            </>
          )}
        </div>
      </div>
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] bg-saffron text-sm font-black text-ink">ب</span>
    </div>
  );
}
