"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api<{ token: string }>(`/auth/${mode}`, { body: { email, password } });
      setToken(r.token);
      router.push("/bots/");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-5">
      <h1 className="mb-1 text-center text-2xl font-extrabold text-indigo-700">بات‌ساز</h1>
      <p className="mb-6 text-center text-sm text-slate-500">{mode === "register" ? "ساخت حساب جدید" : "ورود به حساب"}</p>
      <form onSubmit={submit} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <input dir="ltr" type="email" required placeholder="ایمیل" value={email} onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-left outline-none focus:border-indigo-500" />
        <input dir="ltr" type="password" required minLength={6} placeholder="رمز عبور (حداقل ۶ کاراکتر)" value={password}
          onChange={(e) => setPassword(e.target.value)} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-left outline-none focus:border-indigo-500" />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button disabled={busy} className="w-full rounded-lg bg-indigo-600 py-2.5 font-bold text-white hover:bg-indigo-700 disabled:opacity-60">
          {busy ? "..." : mode === "register" ? "ثبت‌نام" : "ورود"}
        </button>
      </form>
      <button onClick={() => setMode(mode === "register" ? "login" : "register")} className="mt-4 text-sm text-indigo-700 hover:underline">
        {mode === "register" ? "حساب دارید؟ وارد شوید" : "حساب ندارید؟ ثبت‌نام کنید"}
      </button>
    </main>
  );
}
