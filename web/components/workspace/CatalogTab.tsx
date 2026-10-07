"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiBlob, apiUpload } from "@/lib/api";
import { fa } from "@/components/ui";
import { ExportButtons } from "@/components/workspace/ExportButtons";

type Opt = { name: string; choices: string[] };
type Prod = { id: number; name: string; category: string; price: number; stock: number | null; options: Opt[]; description: string; is_sample: boolean; photo: boolean };
type Cat = { blocks: { id: string; title: string }[]; block: string | null; total: number; products: Prod[]; categories: string[]; sample: boolean };
type Preview = { kind: "table" | "vision"; total: number; products: Omit<Prod, "id" | "is_sample" | "photo">[]; warnings: string[]; notes: string[]; cost_usd: number };

const card = "rounded-2xl border border-line-2 bg-panel p-4";
const btn = "min-h-11 rounded-xl bg-saffron px-5 font-bold text-ink disabled:opacity-50";
const money = (n: number) => fa(n.toLocaleString("en-US"));
/** Phone photos are several MB: shrink to 1024px JPEG in the browser before upload. */
async function shrink(file: File): Promise<Blob> {
  const img = await createImageBitmap(file);
  const k = Math.min(1, 1024 / Math.max(img.width, img.height));
  const c = document.createElement("canvas");
  c.width = Math.round(img.width * k);
  c.height = Math.round(img.height * k);
  c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
  return new Promise((ok, no) => c.toBlob((b) => (b ? ok(b) : no(new Error("خواندن عکس ممکن نشد."))), "image/jpeg", 0.85));
}

function PhotoCell({ botId, p, onChange, onError }: { botId: string; p: Prod; onChange: () => void; onError: (m: string) => void }) {
  const [src, setSrc] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pick = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!p.photo) { setSrc(null); return; }
    let url = "";
    apiBlob(`/bots/${botId}/catalog/products/${p.id}/photo`).then((b) => { if (b) { url = URL.createObjectURL(b); setSrc(url); } }).catch(() => {});
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [botId, p.id, p.photo]);
  async function upload(f: File | undefined) {
    if (!f) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", await shrink(f), "photo.jpg");
      await apiUpload(`/bots/${botId}/catalog/products/${p.id}/photo`, form, "PUT");
      onChange();
    } catch (e: any) { onError(e.message); } finally { setBusy(false); }
  }
  async function drop() {
    try { await api(`/bots/${botId}/catalog/products/${p.id}/photo`, { method: "DELETE" }); onChange(); } catch (e: any) { onError(e.message); }
  }
  return (
    <div className="flex items-center gap-1">
      <input ref={pick} type="file" accept="image/*" className="hidden" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
      {src ? (
        <>
          <button onClick={() => pick.current?.click()} title="تغییر عکس"><img src={src} alt="" className="size-10 rounded-lg object-cover" /></button>
          <button onClick={drop} className="text-xs text-mute hover:text-bad" aria-label="حذف عکس">✕</button>
        </>
      ) : (
        <button onClick={() => pick.current?.click()} disabled={busy} className="size-10 rounded-lg border border-dashed border-line-2 text-xs text-mute hover:border-saffron disabled:opacity-50">{busy ? "…" : "+ عکس"}</button>
      )}
    </div>
  );
}

const optSummary = (o: Opt[]) => o.map((g) => `${g.name}: ${g.choices.slice(0, 5).join("، ")}${g.choices.length > 5 ? "…" : ""}`).join(" · ");


const field = "min-h-11 w-full rounded-xl border border-line-2 bg-ink px-3 disabled:opacity-50";

/** One product at a time: the same «append» save the import uses, so sample rows are replaced by the first real product. */
function AddProduct({ botId, block, categories, onDone, onError }: { botId: string; block: string; categories: string[]; onDone: () => void; onError: (m: string) => void }) {
  const [f, setF] = useState({ name: "", category: "", price: "", stock: "", options: "", description: "" });
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  async function add() {
    const price = Number(f.price.replace(/[,،٬\s]/g, "").replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))));
    if (!f.name.trim()) return onError("نام محصول را بنویسید.");
    if (!Number.isFinite(price) || price < 0 || f.price.trim() === "") return onError("قیمت را به تومان و با عدد بنویسید.");
    const stock = f.stock.trim() === "" ? null : Number(f.stock.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))));
    if (stock !== null && (!Number.isInteger(stock) || stock < 0)) return onError("موجودی باید یک عدد صحیح باشد، یا خالی بماند تا نامحدود شود.");
    // «سایز: S، M، L» per line
    const options = f.options.split("\n").map((l) => l.split(":")).filter((x) => x.length > 1 && x[0].trim()).map(([n, ...r]) => ({ name: n.trim(), choices: r.join(":").split(/[،,]/).map((c) => c.trim()).filter(Boolean), prices: [] as number[] })).filter((o) => o.choices.length);
    setBusy(true);
    onError("");
    try {
      await api(`/bots/${botId}/catalog/commit`, { body: { block, mode: "append", products: [{ name: f.name.trim(), category: f.category.trim(), price, stock, options, description: f.description.trim() }] } });
      setF({ ...f, name: "", price: "", stock: "", options: "", description: "" });
      onDone();
    } catch (e: any) { onError(e.message); } finally { setBusy(false); }
  }
  return (
    <div className={card}>
      <h3 className="mb-1 font-bold">افزودن یک محصول</h3>
      <p className="mb-3 text-sm text-mute">محصولات را یکی‌یکی اضافه کنید. با اولین محصول، محصولات نمونه حذف می‌شوند. عکس را بعد از افزودن، از جدول پایین می‌توانید بگذارید.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">نام محصول<input value={f.name} onChange={set("name")} maxLength={300} className={field + " mt-1"} /></label>
        <label className="text-sm">دسته<input value={f.category} onChange={set("category")} list="catalog-cats" maxLength={120} placeholder="مثلاً تی‌شرت" className={field + " mt-1"} /></label>
        <label className="text-sm">قیمت (تومان)<input value={f.price} onChange={set("price")} inputMode="numeric" className={field + " mt-1"} /></label>
        <label className="text-sm">موجودی<input value={f.stock} onChange={set("stock")} inputMode="numeric" placeholder="خالی = نامحدود" className={field + " mt-1"} /></label>
        <label className="text-sm sm:col-span-2">گزینه‌ها (هر گروه در یک خط)<textarea value={f.options} onChange={set("options")} rows={2} placeholder={"سایز: S، M، L\nرنگ: مشکی، سفید"} className={field + " mt-1 py-2"} /></label>
        <label className="text-sm sm:col-span-2">توضیح (اختیاری)<input value={f.description} onChange={set("description")} maxLength={1000} className={field + " mt-1"} /></label>
      </div>
      <datalist id="catalog-cats">{categories.map((c) => <option key={c} value={c} />)}</datalist>
      <button onClick={add} disabled={busy} className={btn + " mt-3"}>{busy ? "در حال افزودن…" : "افزودن محصول"}</button>
    </div>
  );
}

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
  if (!cat.block) return <p className={card + " text-mute"}>این ربات فهرست محصولات ندارد. اگر لازم دارید، در «گفت‌وگوی ساخت» بنویسید که یک فروشگاه با فهرست محصولات اضافه شود.</p>;

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="rounded-xl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{error}</p>}
      {cat.sample && <p className="rounded-xl border border-saffron/50 bg-saffron/10 p-3 text-sm leading-7">این‌ها محصولات <b>نمونه</b>‌اند تا بتوانید ربات را از همین حالا امتحان کنید. با وارد کردن فهرست واقعی فروشگاه، نمونه‌ها جایگزین می‌شوند.</p>}

      <div className={card}>
        <h3 className="mb-1 text-lg font-extrabold">وارد کردن محصولات</h3>
        <p className="mb-3 text-sm leading-7 text-mute">فایل اکسل یا CSV، یک جدول کپی‌شده، یا عکس یا PDF فهرست قیمت را بارگذاری کنید. بات‌یار ستون‌ها را تشخیص می‌دهد و پیش از ذخیره، نتیجه را به شما نشان می‌دهد.</p>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <input ref={input} type="file" multiple accept=".csv,.xlsx,.xlsm,.png,.jpg,.jpeg,.webp,.pdf,image/*,application/pdf" className="hidden"
            onChange={(e) => { setFiles(Array.from(e.target.files ?? []).slice(0, 4)); setPv(null); }} />
          <button onClick={() => input.current?.click()} className="min-h-11 rounded-xl border border-line-2 px-4 hover:border-saffron">انتخاب فایل یا عکس</button>
          {files.length > 0 && <span className="text-sm text-mute">{files.map((f) => f.name).join("، ")}</span>}
        </div>
        {!files.length && (
          <textarea value={text} onChange={(e) => { setText(e.target.value); setPv(null); }} rows={4} placeholder="یا جدول را اینجا جای‌گذاری کنید (ردیف اول، عنوان ستون‌ها)…"
            className="mb-3 w-full rounded-xl border border-line-2 bg-ink p-3 text-sm outline-none focus:border-saffron" />
        )}
        <button className={btn} disabled={busy || (!files.length && text.trim().length < 5)} onClick={check}>{busy && !pv ? "در حال خواندن…" : "بررسی"}</button>
      </div>

      {pv && (
        <div className={card + " border-saffron/60"}>
          <h3 className="mb-2 font-extrabold">{fa(pv.total)} محصول پیدا شد {pv.kind === "vision" && <span className="text-sm font-normal text-mute">(خوانده‌شده از تصویر؛ لطفاً با دقت بررسی کنید)</span>}</h3>
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
            <label className="flex items-center gap-2"><input type="radio" checked={mode === "replace"} onChange={() => setMode("replace")} />جایگزینی فهرست فعلی</label>
            <label className="flex items-center gap-2"><input type="radio" checked={mode === "append"} onChange={() => setMode("append")} />افزودن به فهرست فعلی</label>
          </div>
          <div className="flex gap-3">
            <button className={btn} disabled={busy || pv.total === 0} onClick={save}>{busy ? "در حال ذخیره…" : `تأیید و ذخیره (${fa(pv.total)} محصول)`}</button>
            <button className="min-h-11 rounded-xl border border-line-2 px-4" onClick={() => setPv(null)}>انصراف</button>
          </div>
        </div>
      )}

      <AddProduct botId={botId} block={cat.block} categories={cat.categories} onDone={load} onError={setError} />
      <div className={card}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-bold">محصولات ({fa(cat.total)}){cat.total > cat.products.length && <span className="text-sm font-normal text-mute"> · {fa(cat.products.length)} مورد اول در این جدول</span>}</h3>
          {cat.total > 0 && <ExportButtons path={`/bots/${botId}/export/products`} name="products" onError={setError} />}
        </div>
        {cat.products.length === 0 ? <p className="text-sm text-mute">هنوز محصولی ثبت نشده است.</p> : (
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="text-mute"><tr><th className="p-2 text-right">عکس</th><th className="p-2 text-right">نام</th><th className="p-2 text-right">دسته</th><th className="p-2 text-right">قیمت</th><th className="p-2 text-right">موجودی</th><th /></tr></thead>
              <tbody>
                {cat.products.map((p) => (
                  <tr key={p.id} className="border-t border-line-2">
                    <td className="p-2"><PhotoCell botId={botId} p={p} onChange={load} onError={setError} /></td>
                    <td className="min-w-48 max-w-80 p-2 align-middle"><span className="block break-words leading-6">{p.name}</span>{p.is_sample && <span className="mt-1 inline-block rounded bg-saffron/20 px-1.5 text-xs leading-5 text-saffron">نمونه</span>}</td>
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
