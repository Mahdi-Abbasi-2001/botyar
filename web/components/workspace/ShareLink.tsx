"use client";
import { useEffect, useState } from "react";
import QRCode from "qrcode";

/** How customers reach a published bot: a link to share and a QR code to print. Dark-on-white so every phone scans it. */
export function ShareLink({ url, fileName, hint, brand }: { url: string; fileName: string; hint?: string; brand?: boolean }) {
  const [svg, setSvg] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    QRCode.toString(url, { type: "svg", margin: 1, color: { dark: "#0B0D12", light: "#FFFFFF" } }).then(setSvg).catch(() => setSvg(""));
  }, [url]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked: the link is still selectable */
    }
  }

  async function download() {
    const png = await QRCode.toDataURL(url, { width: 1024, margin: 2, color: { dark: "#0B0D12", light: "#FFFFFF" } });
    const a = document.createElement("a");
    a.href = png;
    a.download = `${fileName}-qr.png`;
    a.click();
  }

  return (
    <div className="flex flex-wrap items-center gap-4">
      {svg ? (
        <div role="img" aria-label="کد QR لینک ربات" className="h-32 w-32 shrink-0 overflow-hidden rounded-xl bg-white p-1.5 [&>svg]:h-full [&>svg]:w-full"
          dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <div className="h-32 w-32 shrink-0 rounded-xl bg-raised" />
      )}
      <div className="flex min-w-0 flex-[1_1_220px] flex-col gap-2">
        {hint && <span className="text-sm leading-7 text-mute">{hint}</span>}
        <a href={url} target="_blank" rel="noreferrer" dir="ltr" className="break-all text-left font-bold text-[var(--brand,var(--color-saffron))] underline">{url.replace(/^https:\/\//, "")}</a>
        <div className="flex flex-wrap gap-2">
          <button onClick={copy} className={`min-h-11 rounded-xl px-4 text-sm font-bold ${brand ? "bg-[var(--brand-deep)] text-white" : "bg-saffron text-ink"}`}>{copied ? "کپی شد ✓" : "کپی لینک"}</button>
          <button onClick={download} className="min-h-11 rounded-xl border border-line-2 px-4 text-sm hover:border-[var(--brand,var(--color-saffron))]">دریافت کد QR برای چاپ</button>
        </div>
      </div>
    </div>
  );
}


/** One link per piece of content that sits behind a channel join: a post, story or ad can send people straight to it. */
export function ContentLinks({ items, link }: { items: { id: string; title: string; channels: string[] }[]; link: (id: string) => string }) {
  const [copied, setCopied] = useState("");
  if (!items.length) return null;
  async function copy(id: string) {
    try {
      await navigator.clipboard.writeText(link(id));
      setCopied(id);
      setTimeout(() => setCopied(""), 1800);
    } catch {
      /* clipboard blocked: the link is still selectable */
    }
  }
  return (
    <div className="mt-4 rounded-xl border border-line-2 p-4 text-sm leading-7">
      <p className="m-0 font-bold">لینک اختصاصی هر محتوا</p>
      <p className="m-0 mb-2 text-mute">مشتری با این لینک مستقیم به همان محتوا می‌رسد و ربات اول عضویت او را در کانال‌ها بررسی می‌کند. ربات را مدیر هر کانال کنید، وگرنه عضویت قابل بررسی نیست.</p>
      <div className="flex flex-col gap-2">
        {items.map((c) => (
          <div key={c.id} className="flex flex-wrap items-center gap-2 rounded-xl bg-raised px-3 py-2">
            <span className="font-bold">{c.title}</span>
            <span dir="ltr" className="text-xs text-mute">{c.channels.join("  ")}</span>
            <span dir="ltr" className="min-w-0 flex-1 truncate text-left text-xs text-fg-2">{link(c.id).replace(/^https:\/\//, "")}</span>
            <button type="button" onClick={() => copy(c.id)} className="min-h-9 rounded-lg border border-line-3 px-3 hover:border-saffron">{copied === c.id ? "کپی شد ✓" : "کپی لینک"}</button>
          </div>
        ))}
      </div>
    </div>
  );
}
