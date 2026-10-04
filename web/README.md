# Botyar web (frontend)

Persian, right-to-left UI for Botyar. See the [root README](../README.md) for what the product does and how to run the
whole thing.

- **Next.js 16, static export** (`output: "export"` in `next.config.ts`). There is no server rendering: every page is
  a client component that calls the FastAPI backend, which also serves the exported files from `api/static`.
- **Same origin in production.** API calls go to `/api/...` (`lib/api.ts`); the login token is kept in `localStorage`.
- **Design:** "night workshop" — ink background, saffron for actions, mint for "tested/OK". Colours are Tailwind 4 theme
  tokens in `app/globals.css`; shared pieces (logo, stamp, test bar, icons, Persian digits) live in `components/ui.tsx`.
  Font: Vazirmatn, self-hosted.

| Route | File |
|---|---|
| `/` landing | `app/page.tsx`, `components/TypingHero.tsx` |
| `/login/` | `app/login/page.tsx` |
| `/bots/` my bots | `app/bots/page.tsx` |
| `/bot/?id=N` workspace | `app/bot/page.tsx`, `components/workspace/*` |

## Develop

```bash
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev   # backend must be running on :8000
```

## Build

From the repo root, `./build.sh` runs `next build` and copies `web/out` into `api/static`.
