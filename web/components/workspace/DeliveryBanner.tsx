"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fa } from "@/components/ui";

type Health = { messenger: string; status: "ok" | "degraded" | "down" | "unknown"; error: string };
type Info = { messengers: Health[]; outbox: { pending: number; sent_24h: number; failed_24h: number } };
const NAME: Record<string, string> = { bale: "بله", tg: "تلگرام" };

/** Shown only when a messenger the bot is published on is unreachable, or messages are waiting / were lost. */
export function DeliveryBanner({ botId }: { botId: string }) {
  const [info, setInfo] = useState<Info | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => api<Info>(`/bots/${botId}/delivery`).then((d) => alive && setInfo(d)).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [botId]);
  if (!info) return null;
  const bad = info.messengers.filter((m) => m.status === "down" || m.status === "degraded");
  const { pending, failed_24h } = info.outbox;
  if (bad.length === 0 && pending === 0 && failed_24h === 0) return null;
  return (
    <div role="status" className="flex flex-col gap-1 rounded-2xl border border-amber-line bg-saffron/10 p-3 text-sm leading-7 text-amber-fg">
      {bad.map((m) => (
        <span key={m.messenger}>
          ⚠ {NAME[m.messenger] ?? m.messenger} {m.status === "down" ? "در حال حاضر در دسترس نیست" : "ناپایدار است"}؛ پیام‌ها در صف می‌مانند و پس از برقراری ارتباط، خودکار ارسال می‌شوند. اگر پیامی به مشتری نرسید، مشکل از ربات شما نیست.
        </span>
      ))}
      {pending > 0 && <span>{fa(pending)} پیام در صف ارسال مجدد است.</span>}
      {failed_24h > 0 && <span>{fa(failed_24h)} پیام در ۲۴ ساعت گذشته پس از چند بار تلاش ارسال نشد؛ برای مثال چون مشتری ربات را مسدود کرده یا پیام‌رسان مدت زیادی قطع بوده است.</span>}
    </div>
  );
}
