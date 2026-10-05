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
- **Price per unit, read from a bot's own «پرداخت» (payment) calculator on 2026-10-05 (nothing was bought)** **[dashboard]**:
  - **1 diamond = 20 Toman** (1,000 → 20,000; 100,000 → 2,000,000: linear, no volume discount visible).
  - **1 point = 3 Toman** (10,000 → 30,000).
  - **VAT 10% on top** (e.g. 20,000 → +2,000 = 22,000). Online payment minimum 1,000 Toman; can also pay from account credit.
  - Preset buttons buy the bot's daily diamond use for 10 / 20 / 30 / 60 / 90 / 180 days; custom amounts allowed.
  - The bot page shows remaining diamonds/points, today's consumption, future consumption and an expiry date computed from them. A bot whose diamonds run out expires.
- The panel auto-computes the bot's daily diamond use and a projected date when you will need to top up **[doc]**.

Selected diamond costs (per day) **[doc table]**: default bridge 20 · database 30 · each searchable column 5 · each product/post 1 · product payment message 2 · each sub-process in a simple menu 2 · in a form 3 · Bale/Telegram/Rubika/Soroush bridge (GetUpdates) 50 · own-account GetUpdates for Bale or Telegram 200 · "Sahbot in Bale/Telegram/Rubika/iGap" 40 · WhatsApp (self) 80 · shop/blog process 40 · cron sub-process 40 · group-post transfer 500 · group manager 30 · data export 40 · each plugin 2 · advanced-process blocks 1–40 each (API connection 20, sanctioned API 40, Excel search 5, loops 8).
Selected point costs **[doc table]**: send or receive a message 1 · file 5 · one-time password 300 · DB export 150 · API call 2 (sanctioned API 3) · stored message 4/day.

**Real benchmarks: SahBot's own four sample bots** (their payment pages show today's diamond use and the price) **[dashboard]**:
| Sample bot | Diamonds/day | Price per day | ≈ per 30 days (before VAT) |
|---|---|---|---|
| API connections demo | 246 | 4,920 Toman | ~148,000 Toman |
| Intro + payment + registration (7 processes: menus, 4 payment flows, a form) | 366 | 7,320 Toman | ~220,000 Toman |
| Forced-join + message-to-admin + anonymous chat | 390 | 7,800 Toman | ~234,000 Toman |
So a *typical real bot costs roughly 150–235 thousand Toman a month in diamonds*, plus 10% VAT, **plus points** (3 Toman each; 1 point per message sent/received, so 1,000 messages a day ≈ 2,000 points ≈ 6,000 Toman a day on top — **[inference]** my arithmetic from the table). Messages are therefore a real cost driver for busy bots.
**[inference] The free gift** (2,000 diamonds + 6,000 points) is worth about 40,000 + 18,000 = 58,000 Toman, i.e. roughly 5–8 days of a typical bot's diamonds.
*My earlier estimate of ~165 diamonds/day for a café bot was too low compared with their own samples (246–390).*
Compare AradBot's flat plans: 183,000–609,000 Toman/month (pricing-research.md). SahBot lands in the same range for a typical bot but is metered per feature and per message.

## 3b. Inventory seen inside the dashboard (account 'mahdiabbasi', draft bot created for research)
- Company: **شرکت دانش‌بنیان داده‌پردازان هماگستر صهبا (sahbaa.com), site footer "since 1396 (2017)"**; panel version **0.8.3**; the product is registered as knowledge-based since 1401.
- **Bridge types** (create-bridge dropdown): Bale, iGap, Eitaa interactive bot, Eitaa sender bot, Telegram, Rubika, Soroush, Telegram (GetUpdates), Web, Sms.ir panel, Sms.ir quick-send. Each new bot already has the free "Sahbot" web bridge.
- **Process types** (dropdown): simple menu, data-collection form, post transfer, group manager, custom code, cron job, blog/shop, advanced, path builder.
- **Payment gateways** for shops (account level): **Mellat bank gateway and ZarinPal** only.
- **Condition types:** compare two values, combined condition. **Auto-edit rule type:** text replace (+ others listed in docs).
- **Bot sections:** info, processes (with labels and a default command), bridges (per-bridge files, messages, bulk message to its users), payment, databases, users (advanced search by 8 fields, user groups, bulk send, bulk delete), conditions, auto-edit rules, collections, items, carts (filter by cart id, only completed carts, transaction id/status), files (with labels, keep-more-than-24h costs points), Sahbot-files (uploaded files, per-MB storage costs points), messages (sent/received with 12-field search; storing messages costs points per day), logs, panel managers (delegate access; the person must first send /start to the bot), global variables, statistics (diamond/point use, plugins used), export/import (ZIP or JSON, "official backup" with their signature valid for 15 days, import history, a draft export without signature).
- Account area: **tickets** with departments (e.g. orders), fields for mobile and Telegram/Eitaa/Bale usernames; announcements feed; chat page (/c) for talking to bot users; usage chart on the desk; docs/tutorial links; a "support" icon for build requests, bug reports and transaction issues.
- Four **sample bots** the user can open read-only: intro+payment+registration, invite-link generator, API connections, forced-join + admin messaging + anonymous chat.
- Onboarding friction: creating a bot needs an address that **must end in "bot"** (the form fails silently otherwise — found while creating the draft), a title, description and an access level.

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
- Price anchor: SahBot's own samples cost ~150–235k Toman/month in diamonds + VAT + points; AradBot flat plans are 183k–609k Toman/month; freelancer builds are 2–30M Toman one-off. A flat Botyar price in the low hundreds of thousands per month would be in-market, but the number must still come from owner conversations.
- Roadmap items SahBot already proves demand for: more messengers (Eitaa, Telegram, Rubika), mass messaging (we have manual announcements), scheduled messages (we have booking reminders only), bank-gateway shop payments, group moderation (skip), API/AI connections (skip: customers never talk to an LLM in our design).
- Risks: a big incumbent could add an AI "describe your bot" front-end; our answer is the tested deterministic engine and the owner dashboard.

## 7. Still unknown
- ~~Rials per diamond / point~~ — **found:** 20 and 3 Toman (+10% VAT).
- Their user numbers, revenue, funding, and team size: not on any page read.
- Whether they have any AI/natural-language assistant (nothing on the pages read).

## 8. Decisions taken after this research (2026-10-05)
Built because SahBot proves demand and our target owners need them: **photo/file sending**, **map pin**, **scheduled announcements** (their cron jobs), **customers list with export** (their "users" section), **sub-menus** (their nested menus), **quizzes** (their quiz forms), **enforced plans + a public pricing page** (their paid model, but flat).
Considered and deliberately NOT built: *forced channel join* (feasible with Bale's `getChatMember`, but it needs the bot to be admin of the owner's channel, which the shared bot cannot be; fits channel owners rather than shops/clinics); *invite/referral links* (Bale's docs do not mention `start` deep-link parameters); *anonymous chat*, *group moderation*, *post forwarding between channels*, *poster/image composition*, *AI chat connection*, *custom code* (different customer or against our "customers never talk to an LLM" design); *more messengers* (Eitaa/Rubika/iGap/WhatsApp: a roadmap item, each needs its own adapter).
