# Telegram relay (Deno Deploy)

Telegram is unreachable from Iranian servers (checked from the Liara container: «No route to host»), so the backend
reaches Telegram through this small reverse proxy outside Iran, and Telegram delivers updates to the backend through
it as well:

```
Liara  ──► https://<relay>/bot<token>/<method>  ──► api.telegram.org      (needs header x-relay-key)
Telegram ──► https://<relay>/hook/<path>        ──► https://botyar.liara.run/api/tghook/<path>
```

It forwards nothing else: one destination per direction and fixed path shapes. That makes it a reverse proxy, which
Deno Deploy's acceptable use policy allows. The free plan (1M requests and 10 h of active CPU a month) is far more than
this needs: one request per Bot API call and one per incoming message. Time spent waiting on Telegram doesn't count
as CPU.

## Set it up (about 5 minutes, no CLI needed)

1. Go to https://console.deno.com → your organization → **New Playground**.
2. Replace the playground's `main.ts` with the contents of [`main.ts`](main.ts).
3. **Env Variables** (top bar):
   - `UPSTREAM` = `https://botyar.liara.run`
   - `RELAY_KEY` = the value of `TELEGRAM_RELAY_KEY` from `api/.env` (see step 5), stored as a **secret**
4. **Deploy**. Copy the playground's URL from the left of the top bar (it ends in `.deno.net`). Opening it in a browser
   should show `ok`.
5. In `api/.env` add:
   ```
   TELEGRAM_RELAY_URL=https://<your-playground>.deno.net
   TELEGRAM_SHARED_BOT_TOKEN=<token of the shared Telegram bot from @BotFather>   # optional
   ```
   Then run `./deploy.sh`. The first time, it generates `TELEGRAM_RELAY_KEY` into `api/.env` and stops: put that value
   in the playground's `RELAY_KEY`, deploy the playground again, then run `./deploy.sh` once more.

Without `TELEGRAM_SHARED_BOT_TOKEN` owners can still publish to Telegram with their own bot token. With it, the shared
Telegram bot accepts the same 6-character codes as the shared Bale bot, and `t.me/<bot>?start=<code>` links open a
bot directly.

## Check it

- `https://<relay>/` → `ok`
- A POST to `https://<relay>/bot123:abc/getMe` without the key → `403`
- In the app, the Publish tab shows the Telegram card instead of «اتصال به تلگرام روی این سرور فعال نیست».

If Deno ever becomes unreachable from Liara, the same `main.ts` runs on any host outside Iran; change
`TELEGRAM_RELAY_URL` and redeploy. Bale publishing doesn't depend on the relay.
