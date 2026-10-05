# Competitor deep-dive: SahBot (صهبات) — researched 2026-10-05

Sources: sahbot.com home page, sahbot.com/doc.html (full documentation, ~100k characters, read in the browser), sahbot.com/tutorial.html, and the logged-in dashboard web.sahbot.com (dashboard, top-up page, bots page, payment-gateways page) using the user's own account. Everything marked **[doc]** is quoted/paraphrased from those pages; **[inference]** is my reading, not SahBot's statement. No bot was created and nothing was bought.

## 1. What it is
- Iranian no-code **bot-builder platform**, a **knowledge-based (دانش‌بنیان) product registered since 1401 (2022)** with the Vice-Presidency for Science and Technology **[doc]**. Marketed with "Persian support, Persian UI, understanding Iranian users' needs" **[doc]**.
- One bot is built once and **bridged** («پل ارتباطی») to several messengers at the same time **[doc]**.
- Messengers: **Bale, Telegram, Eitaa (interactive bot or "sender" bot), iGap, Rubika, Soroush Plus, WhatsApp, SMS (via Sms.ir)** **[doc]**. Every account also gets a free built-in web chat ("Sahbot bridge") so a bot works without any messenger **[doc]**.
- Honest caveat on their own site: internet/network problems in Iran can break links to some messengers, so ask support before building **[doc]**.

## 2. How a user builds (the product experience)
Dashboard (web.sahbot.com) has four main areas: **میزکار (desk/home), ربات‌ها (bots), گفتگوها (chats), درگاه‌های پرداخت (payment gateways)** plus tickets, top-up, docs, tutorials **[doc]**. The desk shows balance (in **rials**), bots, tickets, today's diamond use, announcements and a usage chart (exportable as svg/png/csv).

Per bot: info, bridges, **processes (فرآیندها)**, users, databases, conditions, auto-edit rules, shopping cart, managers, collections/items, files, global variables, export/import (ZIP backup), statistics, payment **[doc]**.

**Process types** (the building blocks) **[doc]**:
| Process | What it does |
|---|---|
| Simple menu | text/files/location/contact/sticker + buttons that jump to other processes; can ask for phone/location; scheduled send/delete, pin, edit-previous-message options |
| Data-collection form | registration, surveys, **quiz forms**; stored in a database, exported to **Excel/HTML** |
| Post transfer | copy posts between channels/messengers (Telegram→Bale, Bale→Eitaa…); needs bot as admin; rewrite rules, watermark on images |
| Custom code | their engineers add bespoke features ("sometimes very cheap or free"; quoted after a request) |
| Cron job | run a process at a time/interval, e.g. daily/monthly messages to a channel or to bot users |
| Blog / shop | online shop inside the bot: products, nested categories, group pricing, **cart, bank payment gateways**, file selling, instant order message to admin |
| Advanced | **Scratch-like block programming**: loops, conditions, variables, lists, math, JSON, Excel lookup, **API connections** (incl. AI chatbots, currency prices, IBAN lookup), ~20 block categories |
| Group manager | moderation in groups: delete links/media, mute/ban by commands, whitelist/blacklist, clean-up |
| Path builder (مسیرساز) | route logic, e.g. **forced channel join** |

Other features **[doc]**: plugins/templating tags (`<peer>`, `<date>`, `<msg>`, `<dbentry>`, `<gvar>`, `<if>`, `<math>`…) with filters; databases with *searchable columns* (each costs diamonds); conditions; **mass messaging to bot users** (announced 1404/01/18); invite links with tracking and rewards; anonymous chat; image composition/posters; managers with delegated access; "sample bots" to learn from (intro+payment+registration, invite links, API connection, forced-join + anonymous chat).

Education: a **video course** (5 sessions: first bot, plugins & filters, cost calculation, forms+database, advanced process), short videos per feature, per-bridge setup videos, a live Q&A webinar; support groups on Bale, Eitaa and Telegram; ticket system for requests, bug reports and "please build my bot".

Service offer: **"Can Sahbot build the bot for us?" — yes**, in the panel or on a dedicated server **[doc]**.

## 3. Pricing model (usage-based, two in-app units)
- **Diamonds (الماس)** = *capability cost, charged per day*: you pay daily for each feature your bot has. **Points (امتیاز)** = *resource use*: deducted as messages/files/etc. are processed **[doc]**.
- Free gift with the first bot: **2,000 diamonds + 6,000 points** **[doc]**.
- Account wallet is in **rials**; top-up presets: 10,000 / 50,000 / 100,000 / 500,000 / 1,000,000 / 5,000,000 rials, or a custom amount (minimum shown: 10,000 rials = 1,000 Toman) **[doc, top-up page]**. The page shows no diamond price.
- **Rials per diamond / per point are NOT shown** on the public site, docs or the empty-account dashboard; they appear on a bot's own «پرداخت» (payment) screen, where you buy diamonds/points "for a chosen number of days" **[doc]**. → *Open item; needs a bot to exist (see below).*
- The panel auto-computes the bot's daily diamond use and a projected date when you will need to top up **[doc]**.

Selected diamond costs (per day) **[doc table]**: default bridge 20 · database 30 · each searchable column 5 · each product/post 1 · product payment message 2 · each sub-process in a simple menu 2 · in a form 3 · Bale/Telegram/Rubika/Soroush bridge (GetUpdates) 50 · own-account GetUpdates for Bale or Telegram 200 · "Sahbot in Bale/Telegram/Rubika/iGap" 40 · WhatsApp (self) 80 · shop/blog process 40 · cron sub-process 40 · group-post transfer 500 · group manager 30 · data export 40 · each plugin 2 · advanced-process blocks 1–40 each (API connection 20, sanctioned API 40, Excel search 5, loops 8).
Selected point costs **[doc table]**: send or receive a message 1 · file 5 · one-time password 300 · DB export 150 · API call 2 (sanctioned API 3) · stored message 4/day.

**[inference] Worked example** (my arithmetic from the table, not theirs): a café bot with a Bale bridge (40), 10 menu sub-processes (20), a 5-question form (15), a shop process (40) and 50 products (50) ≈ **165 diamonds per day**, so the free 2,000 diamonds would last roughly 12 days. Whether that is cheap or expensive depends on the rial price per diamond, which we do not have yet.

## 4. Strengths to respect
1. **Breadth**: 8 channels, group moderation, channel post-forwarding, cron jobs, mass messaging, API/AI connections, custom code. Botyar covers a small slice of this.
2. **Shop with bank payment gateways** and file selling (Botyar's payment is the Bale wallet only).
3. **Credibility**: knowledge-based certification since 2022; a video course; sample bots; support groups.
4. **Free start** (2,000 diamonds + 6,000 points) with no stated card requirement.
5. **Done-for-you service** and custom code.

## 5. Weaknesses / openings for Botyar (honest)
1. **Learning curve**: plugin tag syntax, Scratch-like advanced blocks, and a diamonds/points calculation that has its own tutorial session. A café owner will not self-serve this. Botyar's promise is "describe it in Persian".
2. **No natural-language building, no automatic testing, no repair loop** seen in their docs/home page **[inference: absent from everything read; not proof they have none]**.
3. **Opaque pricing**: no public Toman price; costs depend on ~35 line items and daily metering. Owners cannot predict a monthly bill. A flat monthly price per bot is a clear difference (note AradBot already sells flat plans: see pricing-research.md).
4. **Daily metering of features** punishes adding features (each plugin, column, product costs diamonds).
5. Their "quiz/survey/registration" is built by hand in forms; Botyar builds, tests and explains it from one sentence.

## 6. What this means for our business plan and pitch
- Position Botyar as **"the fastest way for a small business owner to get a working, tested Bale bot"**, not as a SahBot clone. Do not claim we have more features; claim **time-to-bot and confidence (tests)**.
- Price anchor: AradBot flat plans (183k–609k Toman/month) and freelancer builds (2–30M Toman). SahBot's real price per diamond is still unknown.
- Roadmap items SahBot already proves demand for: more messengers (Eitaa, Telegram, Rubika), mass messaging (we have manual announcements), scheduled messages (we have booking reminders only), bank-gateway shop payments, group moderation (skip), API/AI connections (skip: customers never talk to an LLM in our design).
- Risks: a big incumbent could add an AI "describe your bot" front-end; our answer is the tested deterministic engine and the owner dashboard.

## 7. Still unknown
- Rials per diamond and per point (visible only on a bot's payment screen). To read it, a bot must be created in the account — this uses up the account's one-time free gift; ask the account owner first.
- Their user numbers, revenue, funding, and team size: not on any page read.
- Whether they have any AI/natural-language assistant (nothing on the pages read).
