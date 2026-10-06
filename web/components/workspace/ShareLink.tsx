"use client";
import { useEffect, useState } from "react";
import QRCode from "qrcode";

/** How customers reach a published bot: a link to share and a QR code to print. Dark-on-white so every phone scans it. */
export function ShareLink({ url, fileName, hint }: { url: string; fileName: string; hint?: string }) {
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
        <a href={url} target="_blank" rel="noreferrer" dir="ltr" className="break-all text-left font-bold text-saffron underline">{url.replace(/^https:\/\//, "")}</a>
        <div className="flex flex-wrap gap-2">
          <button onClick={copy} className="min-h-11 rounded-xl bg-saffron px-4 text-sm font-bold text-ink">{copied ? "کپی شد ✓" : "کپی لینک"}</button>
          <button onClick={download} className="min-h-11 rounded-xl border border-line-2 px-4 text-sm hover:border-saffron">دریافت کد QR برای چاپ</button>
        </div>
      </div>
    </div>
  );
}
