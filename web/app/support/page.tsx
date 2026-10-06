"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { ErrorNote, fa } from "@/components/ui";
import { AppHeader } from "@/components/AppHeader";
import { PageTransition } from "@/components/PageTransition";
import { KIND_LABEL, STATUS_LABEL, type Ticket, type TicketKind } from "@/components/tickets";

const card = "rounded-2xl border border-line-2 bg-panel p-4";
const day = (iso: string) => fa(new Date(iso).toLocaleDateString("fa-IR", { month: "long", day: "numeric" }));

export default function Support() {
  const router = useRouter();
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [bots, setBots] = useState<{ id: number; name: string }[]>([]);
  const [admin, setAdmin] = useState(false);
  const [kind, setKind] = useState<TicketKind>("question");
  const [botId, setBotId] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState("");

  const load = useCallback(async () => {
    try {
      setTickets(await api<Ticket[]>("/tickets"));
      setAdmin((await api<{ admin_open: number | null }>("/tickets/unread")).admin_open !== null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    if (!getToken()) return void router.replace("/login/");
    load();
    api<{ id: number; name: string }[]>("/bots").then(setBots).catch(() => {});
  }, [router, load]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const t = await api<Ticket>("/tickets", { body: { kind, text, bot_id: botId ? Number(botId) : null } });
      setText("");
      setSent(`درخواست شما با شماره‌ی ${fa(t.id)} ثبت شد. پاسخ تیم بات‌یار همین‌جا نمایش داده می‌شود.`);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageTransition>
      <div className="min-h-screen">
        <AppHeader />
        <main className="mx-auto flex max-w-[860px] flex-col gap-5 px-4 py-8 sm:px-6">
          <div className="flex flex-col gap-2">
            <h1 className="m-0 text-2xl font-black">پشتیبانی</h1>
            <p className="m-0 text-sm leading-7 text-fg-2">سؤال، مشکل، یا ربات و امکانی که بات‌یار هنوز نمی‌سازد؟ برای تیم بات‌یار بنویسید؛ پاسخ را همین‌جا می‌بینید.</p>
          </div>

          <form onSubmit={send} className={`${card} flex flex-col gap-4`}>
            <fieldset className="m-0 flex flex-wrap gap-2 border-0 p-0">
              <legend className="mb-2 text-sm text-fg-2">موضوع</legend>
              {(Object.keys(KIND_LABEL) as TicketKind[]).map((k) => (
                <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}
                  className={`min-h-11 rounded-full border px-4 text-sm ${kind === k ? "border-saffron bg-saffron/10 font-bold text-fg" : "border-line-2 text-fg-2 hover:text-fg"}`}>
                  {KIND_LABEL[k]}
                </button>
              ))}
            </fieldset>
            {bots.length > 0 && (
              <label className="flex flex-col gap-2 text-sm text-fg-2">
                درباره‌ی کدام ربات؟ (اختیاری)
                <select value={botId} onChange={(e) => setBotId(e.target.value)} className="min-h-11 rounded-xl border border-line-2 bg-raised px-3 text-fg">
                  <option value="">ربات خاصی نیست</option>
                  {bots.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              </label>
            )}
            <label className="flex flex-col gap-2 text-sm text-fg-2">
              توضیح
              <textarea required minLength={5} maxLength={2000} rows={4} value={text} onChange={(e) => setText(e.target.value)}
                placeholder={kind === "unsupported" ? "برای مثال: رباتی می‌خواهم که فیش واریزی مشتری را بخواند و سفارش را تأیید کند." : "هر چه لازم است بدانیم بنویسید."}
                className="resize-y rounded-xl border border-line-2 bg-ink p-3 text-base leading-8 text-fg outline-none placeholder:text-dim focus:border-saffron" />
            </label>
            {error && <ErrorNote>{error}</ErrorNote>}
            {sent && <p className="m-0 rounded-xl border border-mint-line bg-mint-bg p-3 text-sm leading-7 text-mint-fg">{sent}</p>}
            <button disabled={busy || text.trim().length < 5} className="min-h-11 self-start rounded-xl bg-saffron px-5 font-bold text-ink hover:bg-saffron-hi disabled:opacity-50">
              {busy ? "در حال ارسال…" : "ارسال برای تیم بات‌یار"}
            </button>
          </form>

          <section className="flex flex-col gap-3">
            <h2 className="m-0 text-lg font-extrabold">درخواست‌های شما</h2>
            {tickets === null && !error && <p className="m-0 text-sm text-mute">در حال بارگذاری…</p>}
            {tickets?.length === 0 && <p className={`${card} m-0 text-sm text-mute`}>هنوز درخواستی ثبت نکرده‌اید.</p>}
            {tickets?.map((t) => <TicketCard key={t.id} t={t} />)}
          </section>

          {admin && <AdminTickets />}
        </main>
      </div>
    </PageTransition>
  );
}

function TicketCard({ t, children }: { t: Ticket; children?: React.ReactNode }) {
  const [label, cls] = STATUS_LABEL[t.status];
  return (
    <article className={`${card} flex flex-col gap-2.5 text-sm leading-7`}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-mute">
        <span className={`rounded-full px-2.5 py-0.5 ${cls}`}>{label}</span>
        <span>{KIND_LABEL[t.kind]}</span>
        {t.bot_name && <span>· {t.bot_name}</span>}
        {t.username && <span dir="ltr">· {t.username}</span>}
        <span className="mr-auto">شماره‌ی {fa(t.id)} · {day(t.created_at)}</span>
      </div>
      <p className="m-0 whitespace-pre-line">{t.text}</p>
      {t.context && <p className="m-0 border-r-2 border-line-3 pr-3 text-xs leading-6 text-mute">پاسخ بات‌یار در گفت‌وگوی ساخت: {t.context}</p>}
      {t.reply && (
        <div className="flex flex-col gap-1 rounded-xl border border-mint-line bg-mint-bg/60 p-3">
          <span className="flex items-center gap-2 text-xs font-bold text-mint-fg">
            پاسخ تیم بات‌یار{t.replied_at && <span className="font-normal">· {day(t.replied_at)}</span>}
            {t.new_reply && !t.username && <span className="rounded-full bg-mint px-2 text-ink">تازه</span>}
          </span>
          <p className="m-0 whitespace-pre-line">{t.reply}</p>
        </div>
      )}
      {children}
    </article>
  );
}

/** For the Botyar team (admins): every owner's tickets, open ones first, answered from here. */
function AdminTickets() {
  const [all, setAll] = useState<Ticket[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const load = useCallback(() => { api<Ticket[]>("/admin/tickets").then(setAll).catch((e) => setError(e.message)); }, []);
  useEffect(load, [load]);

  async function answer(t: Ticket, status: "answered" | "closed") {
    try {
      await api(`/admin/tickets/${t.id}`, { body: { reply: drafts[t.id] ?? "", status } });
      setDrafts((d) => ({ ...d, [t.id]: "" }));
      load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <section className="flex flex-col gap-3 border-t border-line pt-6">
      <h2 className="m-0 text-lg font-extrabold">درخواست‌های کاربران (مدیر) · {fa(all.filter((t) => t.status === "open").length)} باز</h2>
      {error && <ErrorNote>{error}</ErrorNote>}
      {all.length === 0 && <p className="m-0 text-sm text-mute">درخواستی وجود ندارد.</p>}
      {all.map((t) => (
        <TicketCard key={t.id} t={t}>
          {t.status !== "closed" && (
            <div className="flex flex-col gap-2">
              <textarea aria-label="پاسخ" rows={2} maxLength={4000} value={drafts[t.id] ?? ""} onChange={(e) => setDrafts((d) => ({ ...d, [t.id]: e.target.value }))}
                placeholder="پاسخ برای کاربر…" className="rounded-xl border border-line-2 bg-raised p-2.5 outline-none focus:border-saffron" />
              <div className="flex gap-2">
                <button type="button" disabled={!(drafts[t.id] ?? "").trim()} onClick={() => answer(t, "answered")} className="min-h-10 rounded-xl bg-saffron px-4 font-bold text-ink disabled:opacity-50">ارسال پاسخ</button>
                <button type="button" onClick={() => answer(t, "closed")} className="min-h-10 rounded-xl border border-line-2 px-4">بستن</button>
              </div>
            </div>
          )}
        </TicketCard>
      ))}
    </section>
  );
}
