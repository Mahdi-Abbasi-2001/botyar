"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiUpload } from "@/lib/api";
import { fa } from "@/components/ui";
import { ExportButtons } from "@/components/workspace/ExportButtons";

type Opt = { name: string; choices: string[] };
type Prod = { id: number; name: string; category: string; price: number; stock: number | null; options: Opt[]; description: string; is_sample: boolean };
type Cat = { blocks: { id: string; title: string }[]; block: string | null; total: number; products: Prod[]; categories: string[]; sample: boolean };
type Preview = { kind: "table" | "vision"; total: number; products: Omit<Prod, "id" | "is_sample">[]; warnings: string[]; notes: string[]; cost_usd: number };

const card = "rounded-2xl border border-line-2 bg-panel p-4";
const btn = "min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50";
const money = (n: number) => fa(n.toLocaleString("en-US"));
const optSummary = (o: Opt[]) => o.map((g) => `${g.name}: ${g.choices.slice(0, 5).join("، ")}${g.choices.length > 5 ? "…" : ""}`).join(" · ");

export function CatalogTab({ botId }: { botId: string }) {
  const [cat, setCat] = useState<Cat | null>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pv, setPv] = useState<Preview | null>(null);
  const [mode, setMode] = useState<"replace" | "append">("replace");
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setCat(await api<Cat>(`/bots/${botId}/catalog`));
    } catch (e: any) {
      setError(e.message);
    }
  }, [botId]);
  useEffect(() => {
    load();
  }, [load]);

  async function check() {
    setBusy(true);
    setError("");
    try {
      const f = new FormData();
      files.forEach((x) => f.append("files", x));
      if (!files.length) f.append("text", text);
      setPv(await apiUpload<Preview>(`/bots/${botId}/catalog/preview`, f));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!pv) return;
    setBusy(true);
    setError("");
    try {
      await api(`/bots/${botId}/catalog/commit`, { body: { block: cat?.block, mode, products: pv.products } });
      setPv(null);
      setFiles([]);
      setText("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function patch(p: Prod, body: Record<string, unknown>) {
    try {
      await api(`/bots/${botId}/catalog/products/${p.id}`, { method: "PATCH", body });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(p: Prod) {
    if (!confirm(`«${p.name}» حذف شود؟`)) return;
    await api(`/bots/${botId}/catalog/products/${p.id}`, { method: "DELETE" });
    await load();
  }

  if (!cat) return <p className="text-mute">{error || "در حال بارگذاری…"}</p>;
  if (!cat.block) return <p className={card + " text-mute"}>این ربات فهرست محصولات ندارد. از ایجنت بخواهید «فروشگاه با فهرست محصولات» بسازد.</p>;

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="rounded-xl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{error}</p>}
      {cat.sample && <p className="rounded-xl border border-saffron/50 bg-saffron/10 p-3 text-sm leading-7">این‌ها محصولات <b>نمونه</b> هستند تا ربات همین الان قابل امتحان باشد. فهرست واقعی فروشگاهتان را وارد کنید؛ نمونه‌ها جایگزین می‌شوند.</p>}

      <div className={card}>
        <h3 className="mb-1 text-lg font-extrabold">وارد کردن محصولات</h3>
        <p className="mb-3 text-sm leading-7 text-mute">فایل اکسل یا CSV، یک جدول کپی‌شده، یا عکس/PDF لیست قیمت را بدهید. ایجنت ستون‌ها را تشخیص می‌دهد و پیش از ذخیره نتیجه را نشانتان می‌دهد.</p>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <input ref={input} type="file" multiple accept=".csv,.xlsx,.xlsm,.png,.jpg,.jpeg,.webp,.pdf,image/*,application/pdf" className="hidden"
            onChange={(e) => { setFiles(Array.from(e.target.files ?? []).slice(0, 4)); setPv(null); }} />
          <button onClick={() => input.current?.click()} className="min-h-11 rounded-xl border border-line-2 px-4 hover:border-saffron">انتخاب فایل یا عکس</button>
          {files.length > 0 && <span className="text-sm text-mute">{files.map((f) => f.name).join("، ")}</span>}
        </div>
        {!files.length && (
          <textarea value={text} onChange={(e) => { setText(e.target.value); setPv(null); }} rows={4} placeholder="یا جدول را اینجا پیست کنید (ردیف اول عنوان ستون‌ها)…"
            className="mb-3 w-full rounded-xl border border-line-2 bg-ink p-3 text-sm outline-none focus:border-saffron" />
        )}
        <button className={btn} disabled={busy || (!files.length && text.trim().length < 5)} onClick={check}>{busy && !pv ? "ایجنت در حال خواندن…" : "بررسی"}</button>
      </div>

      {pv && (
        <div className={card + " border-saffron/60"}>
          <h3 className="mb-2 font-extrabold">{fa(pv.total)} محصول پیدا شد {pv.kind === "vision" && <span className="text-sm font-normal text-mute">(از روی تصویر؛ لطفاً با دقت بررسی کنید)</span>}</h3>
          {pv.notes.map((n, i) => <p key={i} className="mb-1 text-sm text-mute">ℹ️ {n}</p>)}
          {pv.warnings.map((n, i) => <p key={i} className="mb-1 text-sm text-saffron">⚠️ {n}</p>)}
          <div className="my-3 max-h-80 overflow-auto rounded-xl border border-line-2">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-ink text-mute"><tr><th className="p-2 text-right">نام</th><th className="p-2 text-right">دسته</th><th className="p-2 text-right">قیمت (تومان)</th><th className="p-2 text-right">موجودی</th><th className="p-2 text-right">گزینه‌ها</th></tr></thead>
              <tbody>
                {pv.products.slice(0, 15).map((p, i) => (
                  <tr key={i} className="border-t border-line-2"><td className="p-2">{p.name}</td><td className="p-2">{p.category || "—"}</td><td className="p-2">{money(p.price)}</td><td className="p-2">{p.stock === null ? "نامحدود" : fa(p.stock)}</td><td className="p-2 text-mute">{optSummary(p.options) || "—"}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          {pv.total > 15 && <p className="mb-2 text-xs text-mute">… و {fa(pv.total - 15)} محصول دیگر</p>}
          <div className="mb-3 flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="radio" checked={mode === "replace"} onChange={() => setMode("replace")} />جایگزین فهرست فعلی</label>
            <label className="flex items-center gap-2"><input type="radio" checked={mode === "append"} onChange={() => setMode("append")} />افزودن به فهرست فعلی</label>
          </div>
          <div className="flex gap-3">
            <button className={btn} disabled={busy || pv.total === 0} onClick={save}>{busy ? "در حال ذخیره…" : `تأیید و ذخیره (${fa(pv.total)} محصول)`}</button>
            <button className="min-h-11 rounded-xl border border-line-2 px-4" onClick={() => setPv(null)}>انصراف</button>
          </div>
        </div>
      )}

      <div className={card}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-bold">محصولات ({fa(cat.total)}){cat.total > cat.products.length && <span className="text-sm font-normal text-mute"> — {fa(cat.products.length)} مورد اول در این جدول</span>}</h3>
          {cat.total > 0 && <ExportButtons path={`/bots/${botId}/export/products`} name="products" onError={setError} />}
        </div>
        {cat.products.length === 0 ? <p className="text-sm text-mute">هنوز محصولی ثبت نشده است.</p> : (
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="text-mute"><tr><th className="p-2 text-right">نام</th><th className="p-2 text-right">دسته</th><th className="p-2 text-right">قیمت</th><th className="p-2 text-right">موجودی</th><th /></tr></thead>
              <tbody>
                {cat.products.map((p) => (
                  <tr key={p.id} className="border-t border-line-2">
                    <td className="p-2">{p.name}{p.is_sample && <span className="mr-2 rounded bg-saffron/20 px-1.5 text-xs text-saffron">نمونه</span>}</td>
                    <td className="p-2 text-mute">{p.category || "—"}</td>
                    <td className="p-2"><input type="number" defaultValue={p.price} min={0} onBlur={(e) => +e.target.value !== p.price && patch(p, { price: +e.target.value })} className="w-28 rounded-lg border border-line-2 bg-ink px-2 py-1" /></td>
                    <td className="p-2"><input type="number" defaultValue={p.stock ?? ""} min={0} placeholder="نامحدود" onBlur={(e) => {
                      const v = e.target.value; if (v === "" ? p.stock !== null : +v !== p.stock) patch(p, v === "" ? { clear_stock: true } : { stock: +v });
                    }} className="w-24 rounded-lg border border-line-2 bg-ink px-2 py-1" /></td>
                    <td className="p-2 text-left"><button onClick={() => remove(p)} className="text-mute hover:text-bad" aria-label="حذف">✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
