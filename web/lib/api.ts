const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export type Button = { text: string; data: string };
export type Action =
  | { type: "send"; text: string; buttons: Button[]; edit?: boolean }
  | { type: "notify_admin"; text: string }
  | { type: "notify_customer"; cust: string; text: string }
  | { type: "media"; block: string; kind: "image" | "document"; uploaded?: boolean; filename?: string }
  | { type: "location"; latitude: number; longitude: number };

/** sessionStorage key for a description typed on /bots, sent to the agent when the workspace opens. */
export const PENDING_KEY = (id: number | string) => `botyar:pending:${id}`;

export const getToken =() => (typeof window === "undefined" ? null : localStorage.getItem("token"));
export const setToken = (t: string | null) => (t ? localStorage.setItem("token", t) : localStorage.removeItem("token"));

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = getToken();
  const init: RequestInit = {
    method: opts.method ?? (opts.body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  };
  // Transient network failures ("Failed to fetch") are common on unstable links: retry a few times.
  let res: Response | null = null;
  for (let attempt = 1; attempt <= 3 && !res; attempt++) {
    try {
      res = await fetch(BASE + "/api" + path, init);
    } catch {
      if (attempt === 3) throw new Error("ارتباط با سرور برقرار نشد. اینترنت را بررسی کنید و دوباره تلاش کنید.");
      await new Promise((r) => setTimeout(r, 700 * attempt));
    }
  }
  if (!res) throw new Error("ارتباط با سرور برقرار نشد.");
  if (res.status === 401 && token && !path.startsWith("/auth")) {
    setToken(null);
    window.location.href = "/login/";
    throw new Error("نیاز به ورود");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const err = new Error(typeof d === "string" ? d : "خطایی رخ داد");
    if (res.status === 402) (err as PlanLimitError).planLimit = true;
    throw err;
  }
  return data as T;
}

/** 402 from the backend: a plan limit (bots, live bots, agent requests). The UI shows it with a way to upgrade. */
export type PlanLimitError = Error & { planLimit?: boolean };
export const isPlanLimit = (e: unknown): boolean => !!(e as PlanLimitError)?.planLimit;

/** multipart upload (catalog import); same auth and Persian error handling as api(). */
export async function apiUpload<T = any>(path: string, form: FormData, method: "POST" | "PUT" = "POST"): Promise<T> {
  const token = getToken();
  let res: Response | null = null;
  for (let attempt = 1; attempt <= 2 && !res; attempt++) {
    try {
      res = await fetch(BASE + "/api" + path, { method, headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form });
    } catch {
      if (attempt === 2) throw new Error("ارتباط با سرور برقرار نشد. اینترنت را بررسی کنید و دوباره تلاش کنید.");
      await new Promise((r) => setTimeout(r, 800));
    }
  }
  if (!res) throw new Error("ارتباط با سرور برقرار نشد.");
  if (res.status === 401) {
    setToken(null);
    window.location.href = "/login/";
    throw new Error("نیاز به ورود");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "خطایی رخ داد");
  return data as T;
}

/** Download an authenticated file (CSV/XLSX export): a plain link cannot send the Authorization header. */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const token = getToken();
  const res = await fetch(BASE + "/api" + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(typeof d.detail === "string" ? d.detail : "دریافت فایل ممکن نشد");
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
