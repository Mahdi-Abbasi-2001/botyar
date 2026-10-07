"use client";
import { useState } from "react";
import { CapacityBar, Icon, Stamp, TestBar, fa } from "../ui";
import { RecordActions } from "./RecordActions";
import { TimeOffCard } from "./TimeOffCard";
import {
  blockExtras, BLOCK_KIND, FIELD_KIND, ago, blockTitle, humanizeDiff, readableInput, scheduleLines, toman, weeklyText,
  type Block, type Field, type Rec, type Spec, type TestRes, type Ver,
} from "./model";

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-2xl border border-line bg-panel p-10 text-center leading-8 text-mute">{children}</p>;
}

// ---------------- Structure ----------------
export function StructureTab({ spec, records, onEdit }: { spec: Spec; records: Rec[]; onEdit: (where: string) => void }) {
  const steps: { title: string; body: React.ReactNode; tone?: "hot" | "amber" }[] = [
    {
      title: "پیام خوش‌آمد و منو",
      body: (
        <>
          <span className="self-start rounded-[12px_12px_12px_4px] bg-raised px-3 py-2 text-sm leading-7">{spec.welcome}</span>
          <div className="flex flex-wrap gap-1.5">{spec.menu.map((m) => <span key={m.label} className="rounded-lg border border-line-3 px-3.5 py-1 text-[13px]">{m.label}</span>)}</div>
        </>
      ),
    },
    ...(spec.gate ? [{ title: `عضویت اجباری در کانال · ${spec.gate.channel}`, body: <span className="text-sm leading-7 text-fg-2">مشتری تا عضو این کانال نشود به ربات دسترسی ندارد. ربات باید مدیر (ادمین) کانال باشد؛ وضعیت آن را در بخش «کانال و گروه» ببینید.</span>, tone: "amber" as const }] : []),
    ...spec.blocks.map((b) => ({ title: `${BLOCK_KIND[b.type]} · ${blockTitle(b)}`, body: <><BlockBody b={b} spec={spec} records={records} /><Extras lines={blockExtras(b)} /></>, tone: tone(b) })),
  ];
  return (
    <div className="flex flex-col">
      <span className="pb-3.5 text-sm text-mute">ربات شما، قدم‌به‌قدم و همان‌طور که مشتری می‌بیند</span>
      {steps.map((s, i) => (
        <div key={i} className="flex gap-3.5">
          <div className="flex flex-col items-center">
            <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full bg-saffron font-black text-ink">{fa(i + 1)}</span>
            {i < steps.length - 1 && <span className="w-0.5 flex-1 bg-line-2" />}
          </div>
          <div className={`mb-3.5 flex min-w-0 flex-1 flex-col gap-2.5 rounded-2xl border p-4 ${s.tone === "hot" ? "border-saffron bg-panel" : s.tone === "amber" ? "border-amber-line bg-amber-bg" : "border-line bg-panel"}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-extrabold">{s.title}</span>
              <button onClick={() => onEdit(i === 0 ? "پیام خوش‌آمد و منو" : blockTitle(spec.blocks[i - 1]))} className="min-h-11 shrink-0 px-1 text-[13px] text-saffron hover:text-saffron-hi">تغییر</button>
            </div>
            {s.body}
          </div>
        </div>
      ))}
    </div>
  );
}

const tone = (b: Block) => (b.type === "admin_notify" ? "amber" : b.type === "booking" || b.type === "catalog_order" ? "hot" : undefined) as "hot" | "amber" | undefined;

function Fields({ fields }: { fields: Field[] }) {
  const label = (key: string) => fields.find((x) => x.key === key)?.label ?? key;
  return (
    <div className="flex flex-col gap-1.5 text-sm">
      {fields.map((f) => (
        <div key={f.key} className="flex flex-col gap-0.5 rounded-[10px] bg-raised px-3 py-2">
          <div className="flex flex-wrap justify-between gap-2">
            <span>«{f.label}»{!f.required && <span className="text-xs text-mute"> · اختیاری</span>}</span>
            <span className="text-mute">
              {f.kind === "choice" || f.kind === "multi"
                ? (f.kind === "multi" ? "چندانتخابی: " : "") + f.choices.map((c, i) => (f.scores?.length ? `${c} (${fa(f.scores[i])})` : c)).join(" / ")
                : FIELD_KIND[f.kind]}
              {f.kind === "number" && (f.min_value != null || f.max_value != null) && ` (${fa(f.min_value ?? "")}–${fa(f.max_value ?? "")})`}
            </span>
          </div>
          {f.show_if && <span className="text-xs text-mute">فقط اگر پاسخ «{label(f.show_if.field)}» {f.show_if.equals.map((v) => `«${v}»`).join(" یا ")} باشد</span>}
        </div>
      ))}
    </div>
  );
}

function Extras({ lines }: { lines: string[] }) {
  if (!lines.length) return null;
  return (
    <ul className="m-0 mt-1 flex list-none flex-col gap-1 p-0 text-xs leading-6 text-fg-2">
      {lines.map((l) => <li key={l} className="flex gap-1.5"><span className="text-saffron">•</span>{l}</li>)}
    </ul>
  );
}

function BlockBody({ b, spec, records }: { b: Block; spec: Spec; records: Rec[] }) {
  if (b.type === "message" && b.variants?.length)
    return (
      <>
        <span className="text-xs text-mute">هر بار یکی از {fa(b.variants.length)} متن زیر به‌طور تصادفی نمایش داده می‌شود و یک متن دو بار پشت سر هم تکرار نمی‌شود:</span>
        <div className="flex flex-col gap-1.5 text-sm">
          {b.variants.map((v, i) => <span key={i} className="rounded-[10px] bg-raised px-3 py-2">{v}</span>)}
        </div>
      </>
    );
  if (b.type === "message")
    return (
      <>
        <p className="m-0 whitespace-pre-line text-sm leading-7 text-fg-2">{b.text}</p>
        {b.media && b.media !== "none" && <span className="text-xs text-mute">📎 {b.media === "image" ? "عکس" : "فایل"} پیوست می‌شود؛ آن را از بخش «فایل‌ها» بارگذاری کنید.</span>}
        {b.location && <span className="text-xs text-mute">📍 موقعیت روی نقشه ({b.location.latitude}, {b.location.longitude})</span>}
      </>
    );
  if (b.type === "form") return <Fields fields={b.fields} />;
  if (b.type === "admin_notify") {
    const on = spec.blocks.find((x) => x.id === b.on);
    return <span className="text-sm leading-7 text-amber-fg">پس از هر ثبت در «{on ? blockTitle(on) : b.on}»: «{b.text}»</span>;
  }
  if (b.type === "referral")
    return <span className="text-sm leading-7 text-fg-2">هر مشتری یک لینک اختصاصی می‌گیرد و هر کاربر تازه‌ای که با آن لینک وارد شود، یک دعوت حساب می‌شود (هدف: {fa(b.goal)} دعوت). جایزه را خودتان تحویل می‌دهید؛ جدول برترین‌ها در بخش «مشتریان» است.</span>;
  if (b.type === "anon_chat")
    return <span className="text-sm leading-7 text-fg-2">دو کاربر بدون دیدن هویت یکدیگر گفت‌وگو می‌کنند (فقط متن؛ لینک و شماره تلفن ارسال نمی‌شود). گزارش‌های تخلف در بخش «ثبت‌ها» نمایش داده می‌شوند و می‌توانید کاربر متخلف را از بخش «مشتریان» مسدود کنید. این امکان فقط در بله و تلگرام کار می‌کند.</span>;
  if (b.type === "menu")
    return (
      <div className="flex flex-col gap-1.5 text-sm">
        {b.items.map((it) => {
          const t = spec.blocks.find((x) => x.id === it.block);
          return (
            <div key={it.label} className="flex justify-between gap-2 rounded-[10px] bg-raised px-3 py-2">
              <span className="font-semibold">{it.label}</span>
              <span className="text-mute">{t ? blockTitle(t) : it.block}</span>
            </div>
          );
        })}
      </div>
    );
  if (b.type === "quiz") {
    const rs = records.filter((r) => r.collection === b.id && typeof r.data.score === "number");
    const avg = rs.length ? rs.reduce((a, r) => a + (r.data.percent as number), 0) / rs.length : 0;
    return (
      <>
        <div className="flex flex-col gap-1.5 text-sm">
          {b.questions.map((q, i) => (
            <div key={i} className="flex flex-col gap-0.5 rounded-[10px] bg-raised px-3 py-2">
              <span className="font-semibold">{fa(i + 1)}. {q.question}</span>
              <span className="text-mute">
                {b.personality?.length
                  ? q.options.map((o, j) => `${o} ← ${b.personality!.find((x) => x.id === q.outcomes?.[j])?.title ?? "—"}`).join(" · ")
                  : q.options.map((o, j) => (j === q.correct ? `✅ ${o}` : o)).join(" · ")}
              </span>
              {q.media === "image" && <span className="text-xs text-mute">🖼 همراه با عکس</span>}
            </div>
          ))}
        </div>
        {b.personality?.length ? (
          <div className="flex flex-col gap-1 text-sm">
            {b.personality.map((o) => <span key={o.id}><b>{o.title}</b>: <span className="text-mute">{o.text}</span></span>)}
          </div>
        ) : (
          <span className="text-xs text-mute">{rs.length ? `${fa(rs.length)} نفر شرکت کرده‌اند و میانگین نمره ${fa(Math.round(avg))}٪ است.` : "هنوز کسی شرکت نکرده است."}</span>
        )}
      </>
    );
  }
  if (b.type === "feedback") {
    const rs = records.filter((r) => r.collection === b.id && typeof r.data.rating === "number");
    const avg = rs.length ? rs.reduce((a, r) => a + (r.data.rating as number), 0) / rs.length : 0;
    return (
      <span className="text-sm leading-7 text-fg-2">
        مشتری از ۱ تا ۵ ستاره امتیاز می‌دهد و در صورت تمایل نظرش را می‌نویسد.{" "}
        {rs.length ? `میانگین تا این لحظه: ${fa(avg.toFixed(1))} از ۵ (${fa(rs.length)} نظر).` : "هنوز نظری ثبت نشده است."}
      </span>
    );
  }
  if (b.type === "contact")
    return <span className="text-sm leading-7 text-fg-2">پیام مشتری برای شما ارسال می‌شود. پاسخ را در بخش «پیام‌ها» می‌نویسید و در همان گفت‌وگوی مشتری به دستش می‌رسد. ربات خودش به این پیام‌ها پاسخ نمی‌دهد.</span>;
  if (b.type === "faq") {
    const open = records.filter((r) => r.collection === b.id && r.data.status === "unanswered").length;
    return (
      <>
        <div className="flex flex-col gap-1.5 text-sm">
          {b.entries.map((e, i) => (
            <div key={i} className="flex flex-col gap-0.5 rounded-[10px] bg-raised px-3 py-2">
              <span className="font-semibold">{e.category && <span className="ml-2 rounded bg-line-2 px-1.5 text-xs font-normal text-mute">{e.category}</span>}{e.question}</span>
              {!!e.alternates?.length && <span className="text-xs text-dim">یا: {e.alternates.join(" · ")}</span>}
              <span className="text-mute">{e.answer}</span>
              {(e.media === "image" || e.location) && <span className="text-xs text-mute">{[e.media === "image" && "🖼 همراه با عکس (بارگذاری در «فایل‌ها»)", e.location && "📍 همراه با نقشه"].filter(Boolean).join(" · ")}</span>}
            </div>
          ))}
        </div>
        <span className="text-xs text-mute">مشتری سؤالش را با کلمات خودش می‌نویسد و یکی از همین پاسخ‌های شما را دریافت می‌کند؛ ربات پاسخی از خودش نمی‌سازد. {open ? `${fa(open)} سؤال بی‌پاسخ در انتظار شماست.` : "سؤال‌هایی که پاسخی برایشان نباشد، برای شما ثبت می‌شوند."}</span>
      </>
    );
  }
  if (b.type === "catalog_order")
    return (
      <>
        {b.source === "table" && (
          <span className="text-sm leading-7 text-fg-2">مشتری محصولات را بر اساس دسته‌بندی می‌بیند و جست‌وجو می‌کند. فهرست محصولات در بخش «محصولات» نگهداری می‌شود و از آنجا وارد یا ویرایش می‌شود.</span>
        )}
        <div className="flex flex-col gap-1.5 text-sm">
          {b.items.map((it) => (
            <div key={it.id} className="flex justify-between gap-2 rounded-[10px] bg-raised px-3 py-2">
              <span>{it.name}{it.options.length > 0 && <span className="text-mute"> · {it.options.map((o) => o.name).join("، ")}</span>}</span>
              <span className="text-saffron">{toman(it.price)}</span>
            </div>
          ))}
        </div>
        {(b.payment !== "none" || !!b.delivery_fee || !!b.delivery_zones?.length || !!b.discount_codes?.length || !!b.time_windows?.length || !!b.low_stock_alert) && (
          <div className="flex flex-col gap-1 text-sm text-fg-2">
            {b.payment === "online" && <span>پرداخت آنلاین داخل بله، مستقیم به کیف پول شما</span>}
            {b.payment === "card" && <span>کارت‌به‌کارت به <b dir="ltr">{b.card_number}</b>{b.card_holder ? ` (${b.card_holder})` : ""}: مشتری رسید را می‌فرستد و شما در «ثبت‌ها» تأیید می‌کنید · بدون رسید تا {fa(b.card_wait_minutes ?? 60)} دقیقه، سفارش لغو می‌شود</span>}
            {!!b.time_windows?.length && (
              <span>زمان تحویل: {b.time_windows.map((w) => `${fa(w.start)} تا ${fa(w.end)}`).join("، ")}{b.per_window ? ` · هر بازه حداکثر ${fa(b.per_window)} سفارش` : ""}{(b.window_days ?? 1) > 1 ? ` · تا ${fa(b.window_days!)} روز آینده` : " · فقط امروز"}</span>
            )}
            {!!b.low_stock_alert && <span>وقتی موجودی محصولی به {fa(b.low_stock_alert)} عدد برسد، به شما خبر می‌دهد</span>}
            {!!b.delivery_fee && <span>هزینه‌ی ارسال: {toman(b.delivery_fee)}{b.free_delivery_over ? ` · رایگان برای سفارش‌های بالای ${toman(b.free_delivery_over)}` : ""}</span>}
            {!!b.delivery_zones?.length && (
              <span>
                هزینه‌ی ارسال بر اساس محل (مشتری هنگام ثبت سفارش انتخاب می‌کند): {b.delivery_zones.map((z) => `${z.label} ${z.fee ? toman(z.fee) : "رایگان"}`).join(" · ")}
                {b.free_delivery_over ? ` · رایگان برای سفارش‌های بالای ${toman(b.free_delivery_over)}` : ""}
              </span>
            )}
            {b.discount_codes?.map((c) => (
              <span key={c.code}>کد <b dir="ltr">{c.code}</b>: {c.percent ? `${fa(c.percent)}٪` : toman(c.amount)} تخفیف{c.min_total ? ` · برای سفارش‌های دست‌کم ${toman(c.min_total)}` : ""}{c.max_uses ? ` · ${fa(c.max_uses)} بار` : ""}{c.visible === false ? " · خصوصی (در منو نمایش داده نمی‌شود)" : " · در دکمه‌ی «کدهای تخفیف» نمایش داده می‌شود"}</span>
            ))}
          </div>
        )}
        <span className="text-xs text-mute">حداکثر {fa(b.max_items)} قلم در هر سفارش{b.min_total ? ` · حداقل مبلغ سفارش ${toman(b.min_total)}` : ""}</span>
        <Fields fields={b.fields} />
      </>
    );
  const mine = records.filter((r) => r.collection === b.id);
  return (
    <>
      <p className="mb-2 text-xs text-mute">{b.allow_cancel ? `مشتری می‌تواند نوبتش را لغو کند${b.cancel_deadline_hours ? ` · تا ${fa(b.cancel_deadline_hours)} ساعت پیش از شروع` : ""}` : "امکان لغو توسط مشتری غیرفعال است"}{b.reminder_hours ? ` · یادآوری ${fa(b.reminder_hours)} ساعت پیش از نوبت` : ""}</p>
      {b.schedule && (
        <div className="flex flex-col gap-1 rounded-xl bg-raised p-3 text-sm">
          <span className="text-xs text-mint-fg">نوبت‌دهی بر اساس ساعت کاری؛ وقت‌های خالی خودکار ساخته می‌شوند</span>
          {scheduleLines(b.schedule).map((l, i) => <span key={i} className={i === 0 ? "" : "text-mute"}>{l}</span>)}
        </div>
      )}
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(200px,1fr))]">
        {b.slots.map((s) => {
          const weekly = weeklyText(s);
          if (weekly) {  // a weekly slot is counted per date, so a lifetime "used" bar would be misleading
            return (
              <div key={s.id} className="flex flex-col gap-1.5 rounded-xl bg-raised p-3">
                <div className="flex justify-between gap-2 text-sm"><span>{s.label}</span><span className="text-saffron">ظرفیت {fa(s.capacity)} نفر</span></div>
                <span className="text-xs text-mint-fg">{weekly}</span>
                <span className="text-xs text-mute">ظرفیت هر جلسه {fa(s.capacity)} نفر، که برای هر تاریخ جداگانه حساب می‌شود</span>
              </div>
            );
          }
          const used = mine.filter((r) => r.data.slot === s.id && r.data.status === "confirmed").length;
          return (
            <div key={s.id} className="flex flex-col gap-1.5 rounded-xl bg-raised p-3">
              <div className="flex justify-between gap-2 text-sm"><span>{s.label}</span><span className={used >= s.capacity ? "text-bad-soft" : "text-saffron"}>{used >= s.capacity ? "تکمیل" : `${fa(s.capacity - used)} جای خالی`}</span></div>
              <CapacityBar used={used} capacity={s.capacity} />
              <span className="text-xs text-mute">ظرفیت {fa(s.capacity)} نفر · {fa(used)} رزرو در پیش‌نمایش</span>
            </div>
          );
        })}
      </div>
      <div className={`flex items-center justify-between rounded-[10px] px-3 py-2 text-sm ${b.waitlist ? "bg-mint-bg" : "bg-raised"}`}>
        <span className={b.waitlist ? "text-mint-fg" : "text-mute"}>لیست انتظار برای زمان‌های تکمیل‌شده</span>
        <span className={`rounded-md px-2.5 font-extrabold ${b.waitlist ? "bg-mint text-ink" : "border border-line-3 text-mute"}`}>{b.waitlist ? "فعال" : "غیرفعال"}</span>
      </div>
      <Fields fields={b.fields} />
    </>
  );
}

// ---------------- Tests ----------------
export function TestsTab({ tests, spec, version }: { tests: TestRes[]; spec: Spec | null; version: number }) {
  if (!tests.length) return <Empty>هنوز تستی برای این نسخه اجرا نشده است. با اولین درخواست در «گفت‌وگوی ساخت»، سناریوهای تست نوشته و اجرا می‌شوند.</Empty>;
  const passed = tests.filter((t) => t.passed).length;
  const all = passed === tests.length;
  return (
    <div className="relative flex flex-col gap-7">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="flex flex-[1_1_480px] flex-col gap-2.5">
          <span className="text-[13px] text-mute">تست‌ها · نسخه‌ی {fa(version)}</span>
          <h2 className="m-0 text-3xl font-black leading-snug sm:text-[44px]">
            {fa(passed)} از {fa(tests.length)} سناریو <span className={all ? "text-mint" : "text-bad-soft"}>موفق بود</span>
          </h2>
          <p className="m-0 max-w-[620px] leading-8 text-fg-2">بات‌یار هر سناریو را مثل یک مشتری واقعی با ربات اجرا کرده است. هر کارت، متن کامل همان گفت‌وگوست.</p>
        </div>
        <div className="w-[320px] max-w-full"><TestBar passed={passed} total={tests.length} h={40} /></div>
      </div>
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(360px,1fr))]">
        {[...tests].sort((a, b) => Number(a.passed) - Number(b.passed)).map((t) => <TestCard key={t.name} t={t} spec={spec} />)}
      </div>
      {all && <Stamp sub={`${fa(passed)} از ${fa(tests.length)} · قبول`} size={150} className="absolute left-8 top-28 hidden md:flex" />}
    </div>
  );
}

function TestCard({ t, spec }: { t: TestRes; spec: Spec | null }) {
  const [open, setOpen] = useState(!t.passed);
  const lines = t.transcript.flatMap((s) => [["مشتری", readableInput(spec, s.user)], ["ربات", s.bot]] as const);
  const shown = open ? lines : lines.slice(0, 6);
  return (
    <article className={`flex flex-col overflow-hidden rounded-[18px] border bg-panel ${t.passed ? "border-line" : "border-bad-line"}`}>
      <div className="flex items-center justify-between gap-3 border-b border-line px-[18px] py-4">
        <span className="font-extrabold leading-7">{t.name}</span>
        <span className={`-rotate-[4deg] shrink-0 rounded-md border-2 px-2.5 text-[13px] font-black ${t.passed ? "border-mint text-mint" : "border-bad text-bad-soft"}`}>{t.passed ? "قبول" : "ناموفق"}</span>
      </div>
      <ol className="m-0 flex list-none flex-col gap-2 px-[18px] py-3.5 text-[13px] leading-7">
        {shown.map(([who, text], i) => (
          <li key={i} className="grid grid-cols-[52px_1fr] gap-2">
            <span className={who === "مشتری" ? "text-saffron" : "text-mute"}>{who}</span>
            <span className="whitespace-pre-line" dir="auto">{text || "—"}</span>
          </li>
        ))}
      </ol>
      {lines.length > 6 && (
        <button onClick={() => setOpen(!open)} className="min-h-11 border-t border-line text-[13px] text-mute hover:text-fg">{open ? "نمایش خلاصه" : `نمایش کامل گفت‌وگو (${fa(lines.length)} پیام)`}</button>
      )}
      {t.failures.length > 0 && (
        <div className="mt-auto flex flex-col gap-1.5 border-t border-dashed border-bad-line bg-bad-bg px-[18px] py-3 text-[13px] leading-7 text-bad-fg">
          {t.failures.map((f, i) => <span key={i}>✗ {f}</span>)}
        </div>
      )}
    </article>
  );
}

// ---------------- Versions ----------------
export function VersionsTab({ versions, spec }: { versions: Ver[]; spec: Spec | null }) {
  if (!versions.length) return <Empty>هنوز نسخه‌ای ساخته نشده است.</Empty>;
  return (
    <div className="flex flex-col gap-5">
      {versions.map((v, idx) => {
        const changes = v.diff[0]?.path === "(جدید)" ? null : humanizeDiff(v.diff, spec);
        const ok = v.tests_passed === v.tests_total;
        return (
          <article key={v.version} className={`flex flex-col gap-4 rounded-[20px] border bg-panel p-5 ${idx === 0 ? "border-mint-line" : "border-line"}`}>
            <div className="flex flex-wrap items-center gap-3">
              <span className={`flex h-6 w-6 items-center justify-center rounded-full ${idx === 0 ? "bg-mint shadow-[0_0_0_6px_rgba(79,209,181,.18)]" : "border-2 border-dim"}`} />
              <span className="text-lg font-black">نسخه‌ی {fa(v.version)}</span>
              {idx === 0 && <span className="rounded-full bg-mint-bg px-2.5 py-0.5 text-xs text-mint-fg">فعلی</span>}
              <span className="mr-auto text-[13px] text-mute">{ago(v.created_at)}</span>
            </div>
            {v.note && <p className="m-0 rounded-xl bg-raised px-3.5 py-2.5 text-[15px] leading-8">«{v.note}»</p>}

            {changes === null ? (
              <span className="text-sm text-mute">ساخت اولیه‌ی ربات</span>
            ) : changes.length === 0 ? (
              <span className="text-sm text-mute">بدون تغییر در ساختار ربات</span>
            ) : (
              <div className="flex flex-col gap-2">
                <span className="text-[13px] text-mute">تغییرات این نسخه</span>
                {changes.slice(0, 10).map((c, i) => (
                  <div key={i} className="flex flex-col gap-1.5 rounded-xl border border-line bg-ink-2 px-3.5 py-2.5 text-sm">
                    <span className="font-bold">{c.where ? `${c.where} · ` : ""}{c.field}</span>
                    {c.kind === "added" ? (
                      <span className="rounded-lg bg-mint-bg px-2.5 py-1 leading-7 text-mint-fg">+ {c.after}</span>
                    ) : c.kind === "removed" ? (
                      <span className="rounded-lg bg-bad-bg px-2.5 py-1 leading-7 text-bad-fg">− {c.before}</span>
                    ) : c.long ? (
                      <>
                        <span className="rounded-lg bg-bad-bg px-2.5 py-1 leading-7 text-bad-fg">− {c.before}</span>
                        <span className="rounded-lg bg-mint-bg px-2.5 py-1 leading-7 text-mint-fg">+ {c.after}</span>
                      </>
                    ) : (
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-mute line-through">{c.before}</span>
                        <span className="text-saffron">←</span>
                        <span className="rounded-md bg-mint px-2.5 font-extrabold text-ink">{c.after}</span>
                      </span>
                    )}
                  </div>
                ))}
                {changes.length > 10 && <span className="text-xs text-dim">و {fa(changes.length - 10)} تغییر کوچک دیگر</span>}
              </div>
            )}

            {v.tests_total > 0 && (
              <div className={`flex flex-col gap-2.5 rounded-2xl border p-4 ${ok ? "border-mint-line bg-mint-bg" : "border-bad-line bg-bad-bg"}`}>
                <div className={`flex justify-between text-sm font-extrabold ${ok ? "text-mint-fg" : "text-bad-fg"}`}>
                  <span>{changes === null ? "تست‌های این نسخه" : "همه‌ی تست‌ها دوباره اجرا شدند"}</span>
                  <span>{fa(v.tests_passed)}/{fa(v.tests_total)}</span>
                </div>
                <TestBar passed={v.tests_passed} total={v.tests_total} h={8} />
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

// ---------------- Records ----------------
const STATUS: Record<string, [string, string]> = {
  confirmed: ["ثبت شد", "border border-line-3"],
  waitlisted: ["لیست انتظار", "bg-mint text-ink font-bold"],
  new: ["سفارش جدید", "border border-saffron text-saffron"],
  cancelled: ["لغو شده", "border border-line-3 text-dim line-through"],
  no_show: ["حاضر نشد", "border border-bad/50 text-bad-soft"],
  awaiting_payment: ["در انتظار پرداخت", "border border-line-2 text-mute"],
  awaiting_transfer: ["منتظر واریز", "border border-line-2 text-mute"],
  transfer_sent: ["واریز شد · منتظر تأیید شما", "border border-saffron bg-saffron/10 text-saffron"],
  preparing: ["در حال آماده‌سازی", "border border-saffron bg-saffron/10 text-saffron"],
  ready: ["آماده", "bg-mint text-ink font-bold"],
  done: ["تحویل شد", "border border-line-3 text-mute"],
  unanswered: ["بدون پاسخ", "border border-saffron bg-saffron/10 text-saffron"],
  handled: ["رسیدگی شد", "border border-line-3 text-mute"],
  received: ["دریافت شد", "border border-saffron text-saffron"],
  reviewing: ["در حال بررسی", "border border-saffron bg-saffron/10 text-saffron"],
  accepted: ["پذیرفته شد", "bg-mint text-ink font-bold"],
  rejected: ["رد شد", "border border-line-3 text-dim"],
};
const mask = (p?: string) => (p && p.length >= 8 ? `${p.slice(0, 4)} ••• ${p.slice(-4)}` : p ?? "—");

export function RecordsTab({ records, spec, botId, onChanged }: { records: Rec[]; spec: Spec; botId: string; onChanged: () => void }) {
  const [filter, setFilter] = useState<string>("all");
  const titles = new Map(spec.blocks.map((b) => [b.id, blockTitle(b)]));
  const bookings = spec.blocks.filter((b): b is Extract<Block, { type: "booking" }> => b.type === "booking");
  const rows = records.filter((r) => filter === "all" || (filter === "waitlisted" ? r.data.status === "waitlisted" : r.collection === filter));

  const offCard = bookings.length > 0 && <TimeOffCard botId={botId} bookings={bookings.map((b) => ({ id: b.id, title: b.title, staff: b.schedule?.staff ?? [] }))} />;
  if (!records.length) return <>{offCard}<Empty>هنوز ثبتی انجام نشده است. در بخش «امتحان ربات» یک نوبت یا سفارش ثبت کنید تا اینجا نمایش داده شود.</Empty></>;

  const detail = (r: Rec) => {
    const d = r.data;
    if (d.question) return `سؤال: ${d.question}${d.note ? ` (${d.note})` : ""}${d.answer ? ` · پاسخ شما: ${d.answer}` : ""}`;
    if (d.status === "reported" && Array.isArray(d.log)) return `گزارش گفت‌وگوی ناشناس: ${d.log.map((l: any) => `${l.from}: ${l.text}`).join(" ⏎ ")}`;
    if (typeof d.score === "number" && d.total != null) return `${d.who ?? ""}: ${d.score} از ${d.total}`;  // a quiz result
    if (typeof d.rating === "number")
      return `${"⭐".repeat(d.rating)}${d.ratings ? ` (${Object.entries(d.ratings).map(([a, v]) => `${a} ${v}`).join("، ")})` : ""}${d.comment ? ` · ${d.comment}` : ""}${d.phone ? ` · تماس: ${d.phone}` : ""}`;
    if (d.slot_label)
      return d.slot_label + (d.party > 1 ? ` · ${d.party} نفر` : "") + (d.attend === "yes" ? " · ✅ حضور را تأیید کرد" : d.attend === "no" ? " · ❌ گفت نمی‌آید" : "");
    if (Array.isArray(d.items)) return `${d.items.map((i: any) => i.name).join("، ")} · ${toman(d.total ?? 0)}${d.delivery_zone ? ` · ارسال به ${d.delivery_zone}` : ""}${d.delivery_time ? ` · تحویل ${d.delivery_time}` : ""}${d.transfer_ref ? ` · پیگیری واریز: ${d.transfer_ref}` : ""}`;
    const head = typeof d.score === "number" ? `امتیاز ${fa(d.score)} · ` : "";
    const note = d.owner_note ? ` · یادداشت شما: ${d.owner_note}` : "";
    return head + (Object.entries(d).filter(([k]) => !k.startsWith("_") && !["name", "phone", "status", "score", "owner_note"].includes(k)).map(([, v]) => String(v)).join(" · ") || "—") + note;
  };

  return (
    <>
    {offCard}
    <div className="flex flex-col gap-5">
      <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]">
        {bookings.flatMap((b) => b.slots.flatMap((s) => {
          const all = records.filter((r) => r.collection === b.id && r.data.slot === s.id);
          // weekly slots: one card per date (capacity is per date); one-off slots: a single card
          const groups: [string, Rec[]][] = s.weekday == null ? [[s.label, all]]
            : all.length ? Object.entries(all.reduce<Record<string, Rec[]>>((m, r) => ((m[r.data.slot_label ?? s.label] ??= []).push(r), m), {})) : [[s.label, []]];
          return groups.map(([title, mine]) => {
          const used = mine.filter((r) => r.data.status === "confirmed").length;
          const wait = mine.filter((r) => r.data.status === "waitlisted").length;
          const gone = mine.filter((r) => r.data.status === "cancelled").length;
          return (
            <div key={b.id + s.id + title} className="flex flex-col gap-2 rounded-2xl border border-line bg-panel p-[18px]">
              <span className="text-[13px] text-mute">{title}</span>
              <span className="text-[28px] font-black">{fa(used)} از {fa(s.capacity)}</span>
              <CapacityBar used={used} capacity={s.capacity} />
              <span className={`text-[13px] ${wait ? "text-mint-fg" : "text-mute"}`}>{wait ? `+ ${fa(wait)} نفر در لیست انتظار` : `${fa(Math.max(0, s.capacity - used))} جای خالی`}{gone ? ` · ${fa(gone)} لغو شده` : ""}</span>
            </div>
          );
          });
        }))}
        <div className="flex flex-col gap-2 rounded-2xl border border-line bg-panel p-[18px]">
          <span className="text-[13px] text-mute">همه‌ی ثبت‌ها در پیش‌نمایش</span>
          <span className="text-[28px] font-black">{fa(records.length)}</span>
          <span className="text-[13px] text-mute">برای هر ثبت، یک پیام به مدیر</span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {[["all", "همه"], ...[...new Set(records.map((r) => r.collection))].map((c) => [c, titles.get(c) ?? c]),
          ...(records.some((r) => r.data.status === "waitlisted") ? [["waitlisted", "لیست انتظار"]] : [])].map(([k, label]) => (
          <button key={k} onClick={() => setFilter(k)} className={`min-h-11 rounded-full px-4 text-sm ${filter === k ? "bg-saffron font-bold text-ink" : "border border-line-2 bg-panel text-fg-2 hover:text-fg"}`}>{label}</button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-line bg-panel">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-[13px] text-mute">
              {["نام", "موبایل", "جزئیات", "وضعیت", "بخش", "زمان ثبت", "عملیات"].map((h) => <th key={h} className="whitespace-nowrap border-b border-line px-4 py-3.5 text-right font-medium">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const [label, cls] = STATUS[r.data.status] ?? ["ثبت شد", "border border-line-3"];
              return (
                <tr key={r.id} className={i === 0 ? "bg-mint-bg/60" : ""}>
                  <td className="whitespace-nowrap border-b border-line px-4 py-3.5">{r.data.name ?? "—"}</td>
                  <td className="whitespace-nowrap border-b border-line px-4 py-3.5 text-right" dir="ltr">{mask(r.data.phone)}</td>
                  <td className="border-b border-line px-4 py-3.5">{detail(r)}</td>
                  <td className="whitespace-nowrap border-b border-line px-4 py-3.5"><span className={`rounded-md px-2 py-0.5 text-xs ${cls}`}>{label}</span></td>
                  <td className="whitespace-nowrap border-b border-line px-4 py-3.5 text-mute">{titles.get(r.collection) ?? r.collection}</td>
                  <td className="whitespace-nowrap border-b border-line px-4 py-3.5 text-mute">{ago(r.created_at)}</td>
                  <td className="border-b border-line px-4 py-3.5"><RecordActions botId={botId} rec={r} onChanged={onChanged} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <span className="flex items-center gap-2 text-xs text-dim"><Icon name="shield" size={14} /> این‌ها ثبت‌های پیش‌نمایش‌اند و با «شروع دوباره» در شبیه‌ساز پاک می‌شوند.</span>
    </div>
    </>
  );
}
