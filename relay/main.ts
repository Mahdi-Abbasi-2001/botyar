// Botyar Telegram relay — a fixed-destination reverse proxy on Deno Deploy.
//
// Telegram is unreachable from Iranian servers, so the Botyar backend (on Liara) talks to Telegram through this:
//   POST /bot<token>/<method>   from our backend (header x-relay-key)  ->  https://api.telegram.org/bot<token>/<method>
//   POST /hook/<path>           from Telegram (webhooks)                ->  ${UPSTREAM}/api/tghook/<path>
// Nothing else is forwarded: no other hosts, no other paths. The webhook path carries the backend's own secret.
//
// Environment: RELAY_KEY (same value as TELEGRAM_RELAY_KEY on the backend), UPSTREAM (e.g. https://botyar.liara.run).

const KEY = Deno.env.get("RELAY_KEY") ?? "";
const UPSTREAM = (Deno.env.get("UPSTREAM") ?? "").replace(/\/+$/, "");
const TELEGRAM = "https://api.telegram.org";
const MAX_BODY = 1_000_000; // Bot API calls and updates are small; refuse anything bigger

function sameSecret(a: string, b: string): boolean {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function forward(target: string, req: Request, timeoutMs: number): Promise<Response> {
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

Deno.serve(async (req) => {
  const { pathname } = new URL(req.url);
  if (req.method === "GET" && pathname === "/") return new Response("ok");
  if (req.method !== "POST") return new Response("not found", { status: 404 });

  // our backend calling the Telegram Bot API
  const api = pathname.match(/^\/bot(\d{5,}:[A-Za-z0-9_-]{20,})\/([A-Za-z]{3,40})$/);
  if (api) {
    if (!sameSecret(req.headers.get("x-relay-key") ?? "", KEY)) return new Response("forbidden", { status: 403 });
    return forward(`${TELEGRAM}/bot${api[1]}/${api[2]}`, req, 60_000);
  }

  // Telegram delivering an update to our backend
  const hook = pathname.match(/^\/hook\/((?:shared|own\/\d{1,12})\/[A-Za-z0-9]{16,64})$/);
  if (hook && UPSTREAM) return forward(`${UPSTREAM}/api/tghook/${hook[1]}`, req, 20_000);

  return new Response("not found", { status: 404 });
});
