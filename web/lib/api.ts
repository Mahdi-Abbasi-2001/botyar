const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export type Button = { text: string; data: string };
export type Action =
  | { type: "send"; text: string; buttons: Button[] }
  | { type: "notify_admin"; text: string };

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
    throw new Error(typeof d === "string" ? d : "خطایی رخ داد");
  }
  return data as T;
}
