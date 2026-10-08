"use client";
import { useRef, useState } from "react";
import { apiUpload } from "@/lib/api";
import { fa } from "../ui";

export type DatasetAsk = { kind: string; title: string; note: string };
export type Row = Record<string, string>;
export type Payload = Record<string, Record<string, unknown>[]>;

type Col = { key: string; label: string; w?: string; numeric?: boolean; list?: string[]; required?: boolean; placeholder?: string };
const WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];

/** The columns of each table the agent can ask for (the same kinds as `app/datasets.py`). */
export const KINDS: Record<string, { cols: Col[]; hint: string; canFile: boolean; max: number }> = {
  menu_items: {
    cols: [{ key: "name", label: "نام", w: "min-w-40 flex-[2]", required: true }, { key: "price", label: "قیمت (تومان)", w: "w-32", numeric: true, required: true, placeholder: "۷۰۰۰۰" },
           { key: "options", label: "گزینه‌ها (اختیاری)", w: "min-w-48 flex-[2]", placeholder: "سایز: معمولی، بزرگ (+۳۰۰۰۰)" }],
    hint: "گزینه‌ها را این‌طور بنویسید: سایز: معمولی، بزرگ (+۳۰۰۰۰)؛ شیر: معمولی، بادام", canFile: true, max: 40,
  },
  quiz_questions: {
    cols: [{ key: "question", label: "سؤال", w: "min-w-52 flex-[3]", required: true }, { key: "o1", label: "گزینه ۱", w: "min-w-28 flex-1", required: true }, { key: "o2", label: "گزینه ۲", w: "min-w-28 flex-1", required: true },
           { key: "o3", label: "گزینه ۳", w: "min-w-28 flex-1" }, { key: "o4", label: "گزینه ۴", w: "min-w-28 flex-1" }, { key: "correct", label: "درست", w: "w-16", numeric: true, required: true, placeholder: "۱" }],
    hint: "ستون «درست» شمارهٔ گزینه‌ی درست است (۱ تا ۴)", canFile: true, max: 20,
  },
  sessions: {
    cols: [{ key: "label", label: "عنوان", w: "min-w-36 flex-[2]", required: true }, { key: "when", label: "روز یا تاریخ", w: "w-40", list: WEEKDAYS, required: true, placeholder: "پنجشنبه یا ۱۴۰۵/۰۷/۲۲" },
           { key: "time", label: "ساعت", w: "w-24", required: true, placeholder: "۱۸:۰۰" }, { key: "capacity", label: "ظرفیت", w: "w-20", numeric: true, required: true }, { key: "price", label: "قیمت", w: "w-28", numeric: true }],
    hint: "روز هفته یعنی «هر هفته»؛ تاریخ شمسی یعنی «فقط همان روز»", canFile: false, max: 20,
  },
  faq_entries: {
    cols: [{ key: "question", label: "سؤال", w: "min-w-52 flex-[2]", required: true }, { key: "answer", label: "پاسخ", w: "min-w-64 flex-[3]", required: true }],
    hint: "پاسخ همان متنی است که مشتری عیناً می‌بیند", canFile: false, max: 40,
  },
  services: {
    cols: [{ key: "name", label: "نام خدمت", w: "min-w-40 flex-[2]", required: true }, { key: "duration_minutes", label: "مدت (دقیقه)", w: "w-28", numeric: true, required: true }, { key: "price", label: "قیمت (تومان)", w: "w-32", numeric: true }],
    hint: "برای هر خدمت مدت و قیمت جدا بنویسید", canFile: false, max: 20,
  },
};

const empty = (kind: string): Row => Object.fromEntries(KINDS[kind].cols.map((c) => [c.key, ""]));
const complete = (kind: string, r: Row) => KINDS[kind].cols.every((c) => !c.required || r[c.key].trim());
const blank = (kind: string, r: Row) => KINDS[kind].cols.every((c) => !r[c.key].trim());

/** Rows as the API wants them (quiz options become a list). */
export function toPayload(kind: string, rows: Row[]): Record<string, unknown>[] {
  return rows.filter((r) => !blank(kind, r)).map((r) =>
    kind === "quiz_questions" ? { question: r.question.trim(), options: [r.o1, r.o2, r.o3, r.o4].map((x) => x.trim()).filter(Boolean), correct: r.correct }
      : Object.fromEntries(Object.entries(r).map(([k, v]) => [k, v.trim()])));
}

export function fromApi(kind: string, items: Record<string, any>[]): Row[] {
  return items.map((it) => {
    if (kind === "quiz_questions") return { question: it.question ?? "", o1: it.options?.[0] ?? "", o2: it.options?.[1] ?? "", o3: it.options?.[2] ?? "", o4: it.options?.[3] ?? "", correct: String(it.correct ?? "") };
    return Object.fromEntries(KINDS[kind].cols.map((c) => [c.key, it[c.key] == null ? "" : String(it[c.key])]));
  });
}

export type TableState = { rows: Row[]; later: boolean };
export const initialTable = (kind: string): TableState => ({ rows: [empty(kind), empty(kind), empty(kind)], later: false });
/** A table is settled when it has at least one complete row and no half-filled one, or the owner chose to fill it later. */
export const settled = (kind: string, t: TableState) => t.later || (t.rows.some((r) => complete(kind, r)) && t.rows.every((r) => blank(kind, r) || complete(kind, r)));

export function DatasetCard({ botId, ask, state, onChange }: { botId: string; ask: DatasetAsk; state: TableState; onChange: (s: TableState) => void }) {
  const k = KINDS[ask.kind];
  const [paste, setPaste] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const file = useRef<HTMLInputElement>(null);
  if (!k) return null;

  const setRows = (rows: Row[]) => onChange({ ...state, rows });
  const setCell = (i: number, key: string, v: string) => setRows(state.rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)));
  const merge = (incoming: Row[]) => {
    const kept = state.rows.filter((r) => !blank(ask.kind, r));
    setRows([...kept, ...incoming].slice(0, k.max).concat(kept.length + incoming.length === 0 ? [empty(ask.kind)] : []));
  };

  async function importFrom(form: FormData) {
    setBusy(true);
    setMsg("");
    try {
      form.append("kind", ask.kind);
      const r = await apiUpload<{ rows: Record<string, any>[]; warnings: string[] }>(`/bots/${botId}/datasets/import`, form);
      merge(fromApi(ask.kind, r.rows));
      setMsg((r.rows.length ? `${fa(r.rows.length)} ردیف خوانده شد. ` : "") + r.warnings.join(" "));
      setPaste(""); setOpen(false);
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  }
  const importText = () => {
    // plain tab/comma cells are cut here (no model call); the server reads free text and tables with unknown columns
    const lines = paste.split(/\r?\n/).filter((l) => l.trim());
    const cells = lines.map((l) => l.split("\t"));
    if (cells.length && cells.every((c) => c.length >= k.cols.filter((x) => x.required).length) && !k.canFile) {
      merge(cells.map((c) => Object.fromEntries(k.cols.map((col, i) => [col.key, (c[i] ?? "").trim()]))));
      setPaste(""); setOpen(false);
      return;
    }
    const f = new FormData();
    f.append("text", paste);
    importFrom(f);
  };

  const done = settled(ask.kind, state);
  return (
    <section className={`flex flex-col gap-3 rounded-2xl border bg-panel p-3.5 ${state.later ? "border-line opacity-80" : done ? "border-mint-line" : "border-saffron"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[15px] font-bold leading-7">📋 {ask.title}</span>
        <label className="flex min-h-9 cursor-pointer items-center gap-2 text-xs text-mute">
          <input type="checkbox" checked={state.later} onChange={(e) => onChange({ ...state, later: e.target.checked })} className="size-4 accent-[var(--color-saffron)]" />
          بعداً وارد می‌کنم؛ فعلاً نمونه بساز
        </label>
      </div>
      {ask.note && <p className="m-0 text-xs leading-6 text-mute">{ask.note}. {k.hint}.</p>}
      {!state.later && (
        <>
          <div className="flex flex-col gap-2">
            {state.rows.map((r, i) => (
              <div key={i} className="grid grid-cols-2 gap-2 rounded-xl border border-line-2 p-2">
                <div className="col-span-2 flex items-center justify-between text-[11px] text-mute">
                  <span>ردیف {fa(i + 1)}</span>
                  <button type="button" onClick={() => setRows(state.rows.length > 1 ? state.rows.filter((_, j) => j !== i) : [empty(ask.kind)])} aria-label="حذف ردیف" className="size-6 hover:text-bad">✕</button>
                </div>
                {k.cols.map((c) => (
                  <label key={c.key} className={`flex min-w-0 flex-col gap-1 text-[11px] text-mute ${c.w?.includes("flex-[") ? "col-span-2" : ""}`}>
                    {c.label}
                    <input value={r[c.key]} list={c.list ? `${ask.kind}-${c.key}` : undefined} inputMode={c.numeric ? "numeric" : undefined}
                      onChange={(e) => setCell(i, c.key, e.target.value)} placeholder={c.placeholder ?? ""} aria-label={`${c.label}، ردیف ${i + 1}`}
                      className={`min-h-10 min-w-0 rounded-lg border bg-ink px-2.5 text-sm text-fg outline-none focus:border-saffron ${!blank(ask.kind, r) && c.required && !r[c.key].trim() ? "border-bad/60" : "border-line-2"}`} />
                  </label>
                ))}
              </div>
            ))}
            {k.cols.filter((c) => c.list).map((c) => <datalist key={c.key} id={`${ask.kind}-${c.key}`}>{c.list!.map((x) => <option key={x} value={x} />)}</datalist>)}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <button type="button" disabled={state.rows.length >= k.max} onClick={() => setRows([...state.rows, empty(ask.kind)])} className="min-h-10 rounded-lg border border-line-2 px-3 hover:border-saffron disabled:opacity-40">+ ردیف</button>
            <button type="button" onClick={() => setOpen(!open)} className="min-h-10 rounded-lg border border-line-2 px-3 hover:border-saffron">جای‌گذاری از اکسل یا متن</button>
            {k.canFile && (
              <>
                <input ref={file} type="file" accept=".csv,.xlsx,.xlsm,.txt,.pdf,image/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) { const fd = new FormData(); fd.append("files", f); importFrom(fd); } }} />
                <button type="button" disabled={busy} onClick={() => file.current?.click()} className="min-h-10 rounded-lg border border-line-2 px-3 hover:border-saffron disabled:opacity-50">فایل یا عکس</button>
              </>
            )}
            {busy && <span className="text-xs text-mute">در حال خواندن…</span>}
          </div>
          {open && (
            <div className="flex flex-col gap-2">
              <textarea value={paste} onChange={(e) => setPaste(e.target.value)} rows={4} placeholder="جدول را از اکسل کپی و اینجا بچسبانید، یا متن را بنویسید…"
                className="rounded-xl border border-line-2 bg-ink p-2.5 text-sm outline-none focus:border-saffron" />
              <button type="button" disabled={busy || paste.trim().length < 3} onClick={importText} className="min-h-10 self-start rounded-lg bg-raised px-4 text-sm hover:bg-line-2 disabled:opacity-50">افزودن به جدول</button>
            </div>
          )}
          {msg && <p role="status" className="m-0 text-xs leading-6 text-saffron">{msg}</p>}
          {!done && <p className="m-0 text-xs text-mute">هر ردیف را کامل کنید یا خالی بگذارید؛ حداقل یک ردیف کامل لازم است.</p>}
        </>
      )}
    </section>
  );
}
