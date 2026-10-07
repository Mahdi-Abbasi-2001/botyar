"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiUpload } from "@/lib/api";
import { fa } from "@/components/ui";

type Q = { id: number | null; question: string; options: string[]; correct: number };
type Bank = { blocks: { id: string; title: string }[]; block: string | null; total: number; questions: Q[]; source: "bank" | "inline" };
type Preview = { kind: "table" | "text" | "vision" | "generated"; total: number; questions: Omit<Q, "id">[]; warnings: string[] };

const card = "rounded-2xl border border-line-2 bg-panel p-4";
const btn = "min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50";
const ghost = "min-h-11 rounded-xl border border-line-2 px-4 hover:border-saffron disabled:opacity-50";
const field = "min-h-11 w-full rounded-xl border border-line-2 bg-ink px-3";
const digits = (s: string) => s.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)));

/** One question as a form: used to add a new one and to edit a saved one. */
function QuestionForm({ initial, onSave, onCancel, busy, label }: { initial?: Omit<Q, "id">; onSave: (q: Omit<Q, "id">) => void; onCancel?: () => void; busy: boolean; label: string }) {
  const [question, setQuestion] = useState(initial?.question ?? "");
  const [options, setOptions] = useState<string[]>(initial?.options ?? ["", "", "", ""]);
  const [correct, setCorrect] = useState(initial?.correct ?? 0);
  const [err, setErr] = useState("");
  function submit() {
    const filled = options.map((o, i) => ({ o: o.trim(), i })).filter((x) => x.o);
    if (question.trim().length < 3) return setErr("متن سؤال را بنویسید.");
    if (filled.length < 2) return setErr("حداقل دو گزینه لازم است.");
    if (!filled.some((x) => x.i === correct)) return setErr("گزینه‌ی درست را از بین گزینه‌های پرشده انتخاب کنید.");
    if (new Set(filled.map((x) => x.o)).size !== filled.length) return setErr("گزینه‌ها نباید تکراری باشند.");
    setErr("");
    onSave({ question: question.trim(), options: filled.map((x) => x.o), correct: filled.findIndex((x) => x.i === correct) });
    if (!initial) { setQuestion(""); setOptions(["", "", "", ""]); setCorrect(0); }
  }
  return (
    <div className="flex flex-col gap-3">
      <label className="text-sm">متن سؤال<textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={2} maxLength={300} className={field + " mt-1 py-2"} /></label>
      <div className="grid gap-2 sm:grid-cols-2">
        {options.map((o, i) => (
          <label key={i} className="flex items-center gap-2 text-sm">
            <input type="radio" name={"correct-" + label} checked={correct === i} onChange={() => setCorrect(i)} aria-label={`گزینه‌ی ${i + 1} درست است`} className="size-5 shrink-0 accent-[var(--color-saffron)]" />
            <input value={o} onChange={(e) => setOptions(options.map((x, j) => (j === i ? e.target.value : x)))} maxLength={60} placeholder={`گزینه‌ی ${fa(i + 1)}${i > 1 ? " (اختیاری)" : ""}`} className={field} />
          </label>
        ))}
      </div>
      <p className="m-0 text-xs text-mute">دایره‌ی کنار هر گزینه یعنی «این گزینه درست است».</p>
      {err && <p role="alert" className="m-0 text-sm text-bad">{err}</p>}
      <div className="flex gap-3">
        <button className={btn} disabled={busy} onClick={submit}>{label}</button>
        {onCancel && <button className={ghost} onClick={onCancel}>انصراف</button>}
      </div>
    </div>
  );
}

export function QuizTab({ botId }: { botId: string }) {
  const [bank, setBank] = useState<Bank | null>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState("10");
  const [pv, setPv] = useState<Preview | null>(null);
  const [mode, setMode] = useState<"append" | "replace">("append");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try { setBank(await api<Bank>(`/bots/${botId}/quiz`)); } catch (e: any) { setError(e.message); }
  }, [botId]);
  useEffect(() => { load(); }, [load]);

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError("");
    try { return await fn(); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }
  const check = () => run(async () => {
    const f = new FormData();
    files.forEach((x) => f.append("files", x));
    if (!files.length) f.append("text", text);
    setPv(await apiUpload<Preview>(`/bots/${botId}/quiz/preview`, f));
  });
  const generate = () => run(async () => {
    const n = Math.max(1, Math.min(30, Number(digits(count)) || 10));
    setPv(await api<Preview>(`/bots/${botId}/quiz/generate`, { body: { topic: topic.trim(), count: n } }));
  });
  const commit = (questions: Omit<Q, "id">[], m: "append" | "replace") => run(async () => {
    await api(`/bots/${botId}/quiz/commit`, { body: { block: bank?.block, mode: m, questions } });
    setPv(null); setFiles([]); setText("");
    await load();
  });
  const remove = (q: Q) => run(async () => {
    if (q.id === null || !confirm("این سؤال حذف شود؟")) return;
    await api(`/bots/${botId}/quiz/questions/${q.id}`, { method: "DELETE" });
    await load();
  });
  const saveEdit = (q: Q, v: Omit<Q, "id">) => run(async () => {
    await api(`/bots/${botId}/quiz/questions/${q.id}`, { method: "PATCH", body: v });
    setEditing(null);
    await load();
  });
  const backToBot = () => run(async () => {
    if (!confirm("بانک سؤال‌ها پاک شود و ربات به سؤال‌هایی که در خودش نوشته شده برگردد؟")) return;
    await api(`/bots/${botId}/quiz`, { method: "DELETE" });
    await load();
  });

  if (!bank) return <p className="text-mute">{error || "در حال بارگذاری…"}</p>;
  if (!bank.block) return <p className={card + " text-mute"}>این ربات آزمونی با سؤال‌های چهارگزینه‌ای ندارد. اگر لازم دارید، در «گفت‌وگوی ساخت» بنویسید که یک آزمون اضافه شود.</p>;
  const inline = bank.source === "inline";

  return (
    <div className="flex flex-col gap-4">
      {error && <p role="alert" className="rounded-xl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{error}</p>}
      {inline && (
        <p className="rounded-xl border border-saffron/50 bg-saffron/10 p-3 text-sm leading-7">
          این {fa(bank.total)} سؤال را بات‌یار موقع ساخت ربات نوشته است. با اولین افزودن یا واردسازی، همه‌ی آن‌ها به بانک سؤال‌های شما منتقل می‌شوند و ربات از بانک استفاده می‌کند.
          برای اینکه هر نفر فقط بخشی از سؤال‌ها را ببیند (مثلاً ۱۰ سؤال تصادفی از بانک)، در «گفت‌وگوی ساخت» بنویسید.
        </p>
      )}

      <div className={card}>
        <h3 className="mb-1 font-bold">افزودن سؤال</h3>
        <p className="mb-3 text-sm text-mute">سؤال‌ها را یکی‌یکی بنویسید، یا فهرست آماده را وارد کنید، یا از روی یک موضوع بسازید.</p>
        <QuestionForm label="افزودن سؤال" busy={busy} onSave={(q) => commit([q], "append")} />
      </div>

      <div className={card}>
        <h3 className="mb-1 font-bold">وارد کردن فهرست آماده</h3>
        <p className="mb-3 text-sm leading-7 text-mute">
          فایل اکسل یا CSV، جدول کپی‌شده، متن سؤال‌ها، عکس یا PDF. در جدول، ستون‌ها این‌ها باشند: «سؤال»، چند «گزینه» و «پاسخ» (شماره‌ی گزینه، یا الف/ب/ج/د). متن و عکس را بات‌یار می‌خواند و پیش از ذخیره به شما نشان می‌دهد.
        </p>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <input ref={input} type="file" multiple accept=".csv,.xlsx,.xlsm,.txt,.pdf,image/*" className="hidden" onChange={(e) => { setFiles(Array.from(e.target.files ?? []).slice(0, 4)); e.target.value = ""; }} />
          <button className={ghost} onClick={() => input.current?.click()}>انتخاب فایل یا عکس</button>
          {files.map((f) => <span key={f.name} className="rounded-lg bg-raised px-2 py-1 text-xs">{f.name} <button className="mr-1 text-mute hover:text-bad" onClick={() => setFiles(files.filter((x) => x !== f))} aria-label="حذف فایل">✕</button></span>)}
        </div>
        {!files.length && <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} placeholder="یا جدول یا متن سؤال‌ها را اینجا جای‌گذاری کنید…" className={field + " mb-3 py-2"} />}
        <button className={btn} disabled={busy || (!files.length && text.trim().length < 5)} onClick={check}>{busy && !pv ? "در حال خواندن…" : "بررسی"}</button>
      </div>

      <div className={card}>
        <h3 className="mb-1 font-bold">ساخت سؤال از روی موضوع</h3>
        <p className="mb-3 text-sm leading-7 text-mute">موضوع و تعداد را بنویسید؛ بات‌یار سؤال می‌نویسد و شما پیش از ذخیره همه را می‌بینید و می‌توانید نادرست‌ها را کنار بگذارید. درستی پاسخ‌ها را همیشه خودتان بررسی کنید.</p>
        <div className="mb-3 grid gap-3 sm:grid-cols-[1fr_8rem]">
          <label className="text-sm">موضوع<input value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={200} placeholder="مثلاً تاریخ ایران باستان، یا زیست‌شناسی پایه‌ی نهم" className={field + " mt-1"} /></label>
          <label className="text-sm">تعداد (تا ۳۰)<input value={count} onChange={(e) => setCount(e.target.value)} inputMode="numeric" className={field + " mt-1"} /></label>
        </div>
        <button className={btn} disabled={busy || topic.trim().length < 3} onClick={generate}>{busy && !pv ? "در حال ساختن…" : "ساخت سؤال"}</button>
      </div>

      {pv && (
        <div className={card + " border-saffron/60"}>
          <h3 className="mb-2 font-extrabold">{fa(pv.total)} سؤال پیدا شد
            {pv.kind !== "table" && <span className="text-sm font-normal text-mute"> ({pv.kind === "generated" ? "نوشته‌شده توسط بات‌یار" : "خوانده‌شده از متن یا تصویر"}؛ لطفاً با دقت بررسی کنید)</span>}</h3>
          {pv.warnings.map((n, i) => <p key={i} className="mb-1 text-sm text-saffron">⚠️ {n}</p>)}
          <ol className="my-3 flex max-h-96 list-none flex-col gap-2 overflow-auto p-0">
            {pv.questions.map((q, i) => (
              <li key={i} className="rounded-xl border border-line-2 p-3 text-sm leading-7">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-bold">{fa(i + 1)}. {q.question}</span>
                  <button className="shrink-0 text-mute hover:text-bad" aria-label="کنار گذاشتن" onClick={() => setPv({ ...pv, total: pv.total - 1, questions: pv.questions.filter((_, j) => j !== i) })}>✕</button>
                </div>
                <div className="flex flex-wrap gap-x-4 text-mute">{q.options.map((o, j) => <span key={j} className={j === q.correct ? "font-bold text-mint" : ""}>{j === q.correct ? "✓ " : ""}{o}</span>)}</div>
              </li>
            ))}
          </ol>
          <div className="mb-3 flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="radio" checked={mode === "append"} onChange={() => setMode("append")} />افزودن به سؤال‌های فعلی</label>
            <label className="flex items-center gap-2"><input type="radio" checked={mode === "replace"} onChange={() => setMode("replace")} />جایگزینی همه‌ی سؤال‌های فعلی</label>
          </div>
          <div className="flex gap-3">
            <button className={btn} disabled={busy || pv.total === 0} onClick={() => commit(pv.questions, mode)}>{busy ? "در حال ذخیره…" : `تأیید و ذخیره (${fa(pv.total)} سؤال)`}</button>
            <button className={ghost} onClick={() => setPv(null)}>انصراف</button>
          </div>
        </div>
      )}

      <div className={card}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-bold">سؤال‌های آزمون ({fa(bank.total)}){bank.total > bank.questions.length && <span className="text-sm font-normal text-mute"> · {fa(bank.questions.length)} مورد اول در این فهرست</span>}</h3>
          {!inline && <button className="text-sm text-mute underline hover:text-bad" onClick={backToBot} disabled={busy}>بازگشت به سؤال‌های داخل ربات</button>}
        </div>
        <ol className="m-0 flex list-none flex-col gap-2 p-0">
          {bank.questions.map((q, i) => (
            <li key={q.id ?? i} className="rounded-xl border border-line-2 p-3 text-sm leading-7">
              {editing === q.id && q.id !== null ? (
                <QuestionForm label="ذخیره‌ی تغییر" initial={q} busy={busy} onSave={(v) => saveEdit(q, v)} onCancel={() => setEditing(null)} />
              ) : (
                <>
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-bold">{fa(i + 1)}. {q.question}</span>
                    {!inline && q.id !== null && (
                      <span className="flex shrink-0 gap-3 text-mute">
                        <button className="hover:text-fg" onClick={() => setEditing(q.id)}>ویرایش</button>
                        <button className="hover:text-bad" onClick={() => remove(q)} aria-label="حذف">✕</button>
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-4 text-mute">{q.options.map((o, j) => <span key={j} className={j === q.correct ? "font-bold text-mint" : ""}>{j === q.correct ? "✓ " : ""}{o}</span>)}</div>
                </>
              )}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
