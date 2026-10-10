// Botyar Telegram relay for Cloudflare Workers: the same fixed-destination reverse proxy as main.ts (Deno Deploy).
//
//   POST /bot<token>/<method>   from our backend (header x-relay-key)  ->  https://api.telegram.org/bot<token>/<method>
//   POST /hook/<path>           from Telegram (webhooks)                ->  ${UPSTREAM}/api/tghook/<path>
// Nothing else is forwarded: no other hosts, no other paths. The webhook path carries the backend's own secret.
//
// Variables (Worker -> Settings -> Variables and Secrets): RELAY_KEY (secret; the same value as TELEGRAM_RELAY_KEY on the
// backend) and UPSTREAM (e.g. https://botyar.mahdidev.ir).

const TELEGRAM = "https://api.telegram.org";
const MAX_BODY = 1_000_000; // Bot API calls and updates are small; refuse anything bigger

function sameSecret(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function forward(target, req, timeoutMs) {
  const body = await req.text();
  if (body.length > MAX_BODY) return new Response("too large", { status: 413 });
  try {
    const r = await fetch(target, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
      signal: AbortSignal.timeout(timeoutMs),
    });
    return new Response(r.body, { status: r.status, headers: { "content-type": r.headers.get("content-type") ?? "application/json" } });
  } catch (e) {
    console.error("forward failed", target.split("/bot")[0], e instanceof Error ? e.name : e);
    return new Response(JSON.stringify({ ok: false, description: "relay: upstream unreachable" }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }
}

export default {
  async fetch(req, env) {
    const key = env.RELAY_KEY ?? "";
    const upstream = (env.UPSTREAM ?? "").replace(/\/+$/, "");
    const { pathname } = new URL(req.url);
    if (req.method === "GET" && pathname === "/") return new Response("ok");
    if (req.method !== "POST") return new Response("not found", { status: 404 });

    // our backend calling the Telegram Bot API
    const api = pathname.match(/^\/bot(\d{5,}:[A-Za-z0-9_-]{20,})\/([A-Za-z]{3,40})$/);
    if (api) {
      if (!sameSecret(req.headers.get("x-relay-key") ?? "", key)) return new Response("forbidden", { status: 403 });
      return forward(`${TELEGRAM}/bot${api[1]}/${api[2]}`, req, 60_000);
    }

    // Telegram delivering an update to our backend
    const hook = pathname.match(/^\/hook\/((?:shared|own\/\d{1,12})\/[A-Za-z0-9]{16,64})$/);
    if (hook && upstream) return forward(`${upstream}/api/tghook/${hook[1]}`, req, 20_000);

    return new Response("not found", { status: 404 });
  },
};
