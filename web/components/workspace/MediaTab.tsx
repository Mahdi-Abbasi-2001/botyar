"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiUpload } from "@/lib/api";
import { fa } from "@/components/ui";

type Slot = { block: string; text: string; kind: "image" | "document"; uploaded: boolean; filename: string; size: number };
const card = "rounded-2xl border border-line-2 bg-panel p-4";
const kb = (n: number) => `${fa((n / 1024).toFixed(n < 10240 ? 1 : 0))} کیلوبایت`;

export function MediaTab({ botId }: { botId: string }) {
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const target = useRef<Slot | null>(null);

  const load = useCallback(async () => {
    try {
      setSlots(await api<Slot[]>(`/bots/${botId}/media`));
    } catch (e: any) {
      setError(e.message);
    }
  }, [botId]);
  useEffect(() => {
    load();
  }, [load]);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    const slot = target.current;
    e.target.value = "";
    if (!f || !slot) return;
    setBusy(slot.block);
    setError("");
    try {
      const form = new FormData();
      form.append("file", f);
      await apiUpload(`/bots/${botId}/media/${slot.block}`, form, "PUT");
      await load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }
  async function remove(s: Slot) {
    setBusy(s.block);
    try {
      await api(`/bots/${botId}/media/${s.block}`, { method: "DELETE" });
      await load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="m-0 text-base">عکس و فایل‌های ربات</h3>
      <p className="m-0 text-sm leading-7 text-mute">برای هر پیامی که ایجنت «ارسال عکس/فایل» برایش گذاشته، فایل واقعی را اینجا بارگذاری کنید (عکس JPG/PNG/WEBP یا PDF، Word، Excel، PowerPoint، متن، CSV، ZIP؛ تا ۵ مگابایت). فعلاً فقط در بله ارسال می‌شود.</p>
      {error && <p role="alert" className="m-0 text-sm text-red-400">{error}</p>}
      <input ref={input} type="file" className="hidden" onChange={onPick} accept={target.current?.kind === "image" ? "image/jpeg,image/png,image/webp" : undefined} />
      {slots && slots.length === 0 && <p className={`${card} m-0 text-sm text-mute`}>هنوز هیچ پیامی فایل نمی‌خواهد. به ایجنت بگویید: «در بخش کاتالوگ، فایل PDF کاتالوگ را بفرست».</p>}
      {slots?.map((s) => (
        <section key={s.block} className={`${card} flex flex-wrap items-center justify-between gap-3`}>
          <div className="flex flex-col gap-1">
            <strong className="text-sm">{s.text}</strong>
            <span className="text-xs text-mute">{s.kind === "image" ? "یک عکس" : "یک فایل"} · {s.uploaded ? `${s.filename} (${kb(s.size)})` : "هنوز بارگذاری نشده"}</span>
          </div>
          <div className="flex gap-2">
            <button disabled={busy === s.block} onClick={() => { target.current = s; input.current?.click(); }} className="min-h-11 rounded-xl bg-saffron px-4 font-bold text-ink disabled:opacity-50">{s.uploaded ? "جایگزین کن" : "بارگذاری"}</button>
            {s.uploaded && <button disabled={busy === s.block} onClick={() => remove(s)} className="min-h-11 rounded-xl border border-line-2 px-4 disabled:opacity-50">حذف</button>}
          </div>
        </section>
      ))}
    </div>
  );
}
