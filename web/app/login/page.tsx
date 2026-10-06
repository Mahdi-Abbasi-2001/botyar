"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, setToken } from "@/lib/api";
import { ErrorNote, Logo, Stamp } from "@/components/ui";

type Mode = "login" | "register";

function LoginForm() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>(useSearchParams().get("mode") === "login" ? "login" : "register");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<{ text: string; taken?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const isReg = mode === "register";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ token: string }>(`/auth/${mode}`, { body: { username: username.trim(), password } });
      setToken(r.token);
      router.push("/bots/");
    } catch (err: any) {
      const taken = isReg && /گرفته شده|ثبت شده/.test(err.message);
      setError({ text: taken ? "این نام کاربری قبلاً گرفته شده؛ یکی دیگر انتخاب کن، یا اگر حساب خودت است:" : err.message, taken });
    } finally {
      setBusy(false);
    }
  }

  const field = (bad: boolean) =>
    `min-h-13 rounded-xl border bg-panel px-3.5 text-left text-base text-fg outline-none focus:border-saffron ${bad ? "border-bad" : "border-line-2"}`;

  return (
    <form onSubmit={submit} className="mx-auto flex w-full max-w-[420px] flex-col gap-5">
      <Logo />
      <h1 className="m-0 text-[32px] font-black leading-snug">{isReg ? "یک حساب بساز، ربات اولت منتظر است." : "خوش برگشتی."}</h1>

      <div role="tablist" className="grid grid-cols-2 rounded-2xl border border-line bg-panel p-1">
        {(["register", "login"] as Mode[]).map((m) => (
          <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => { setMode(m); setError(null); }}
            className={`min-h-11 rounded-xl text-[15px] font-bold ${mode === m ? "bg-saffron text-ink" : "text-fg-2 hover:text-fg"}`}>
            {m === "register" ? "ثبت‌نام" : "ورود"}
          </button>
        ))}
      </div>

      <label className="flex flex-col gap-2">
        <span className="text-sm text-fg-2">نام کاربری</span>
        <input dir="ltr" type="text" required autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false}
          maxLength={isReg ? 32 : 255} pattern={isReg ? "[A-Za-z][A-Za-z0-9_.]{2,31}" : undefined}
          title={isReg ? "۳ تا ۳۲ حرف: حروف انگلیسی، عدد، _ یا نقطه؛ با یک حرف شروع شود" : undefined}
          placeholder={isReg ? "مثلاً cafe_nimkat" : ""} value={username} onChange={(e) => setUsername(e.target.value)} className={field(!!error)} />
        <span className="text-[13px] leading-6 text-mute">
          {isReg ? "حروف انگلیسی، عدد، _ یا نقطه · ۳ تا ۳۲ حرف" : "اگر قبلاً با ایمیل ثبت‌نام کرده‌ای، همان ایمیل را بنویس."}
        </span>
      </label>
      <label className="flex flex-col gap-2">
        <span className="text-sm text-fg-2">رمز عبور</span>
        <input dir="ltr" type="password" required minLength={6} autoComplete={isReg ? "new-password" : "current-password"} value={password}
          onChange={(e) => setPassword(e.target.value)} className={field(!!error && !error.taken)} />
        {isReg && <span className="text-[13px] text-mute">حداقل ۶ حرف</span>}
      </label>

      {error && (
        <ErrorNote>
          {error.text}{" "}
          {error.taken && <button type="button" onClick={() => { setMode("login"); setError(null); }} className="font-bold text-saffron underline">وارد شو</button>}
        </ErrorNote>
      )}

      <button disabled={busy} className="flex min-h-[54px] items-center justify-center gap-2.5 rounded-xl bg-saffron text-[17px] font-extrabold text-ink hover:bg-saffron-hi disabled:bg-[#B98330]">
        {busy && <span className="h-[18px] w-[18px] animate-spin rounded-full border-[3px] border-ink/30 border-t-ink" />}
        {busy ? (isReg ? "در حال ساخت حساب…" : "در حال ورود…") : isReg ? "ساخت حساب" : "ورود"}
      </button>
      <span className="text-center text-[13px] leading-7 text-dim">بعد از ورود، مستقیم سراغ ساخت ربات می‌روی.</span>
    </form>
  );
}

export default function Login() {
  return (
    <main className="flex min-h-screen flex-wrap">
      <div className="flex flex-[1_1_480px] flex-col justify-center px-4 py-12 sm:px-6">
        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
      <div className="bp hidden flex-[1_1_520px] items-center justify-center border-r border-line bg-ink-2 px-6 py-12 md:flex">
        <div className="relative flex w-[460px] max-w-full flex-col gap-3.5">
          <span className="text-[30px] font-black leading-[1.5]">«بگو چی می‌خوای،<br />ربات رو <span className="text-saffron">می‌سازم.</span>»</span>
          <div className="rounded-2xl border border-line-2 bg-panel px-4 py-3.5 text-sm">سلام! به کلینیک دندانپزشکی خوش آمدید.</div>
          <div className="flex flex-col gap-1.5 rounded-2xl border border-saffron bg-panel px-4 py-3.5 text-sm">
            <div className="flex justify-between"><span>شنبه ساعت ۹ صبح</span><span className="text-saffron">۸ جا</span></div>
            <div className="flex justify-between"><span>دوشنبه ساعت ۵ عصر</span><span className="text-saffron">۸ جا</span></div>
          </div>
          <div className="rounded-2xl border border-mint-line bg-mint-bg px-4 py-3.5 text-sm font-bold text-mint-fg">۶ از ۶ تست قبول</div>
          <Stamp size={130} className="absolute -bottom-8 -left-2.5" />
        </div>
      </div>
    </main>
  );
}
