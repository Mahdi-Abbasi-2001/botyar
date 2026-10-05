# Real-Bale / Telegram test checklist (things automated tests CANNOT prove)

The automated tests use a fake messenger. Everything below must be tried once on a real phone before it is shown to judges. For each item: what to do, what you should see, and what a failure tells us. Use two phones or two accounts where noted. After each pass or fail, tell me and I will fix or reword.

## A. Setup
1. Deploy, then log in at https://botyar.liara.run with a fresh account. (`ADMIN_EMAILS` is only needed if you set `BILLING_DEMO=false`.)
2. Build one bot with the agent (for example a café with a menu), run its tests, publish it on Bale, open the link, and send `/admin <code>` from your own Bale to receive notifications.

## B. Already-built features that were never tested on a phone
| # | Do | Expected | If it fails |
|---|---|---|---|
| B1 | Customer places an order; owner changes status in the panel | owner gets the order message; customer gets «در حال آماده‌سازی» etc. | Bale `sendMessage` to the customer failing, or `/admin` link missing |
| B2 | «پیام به مدیر» → type a message → reply from the panel's «پیام‌ها» tab | reply arrives as «✉️ پاسخ مدیر» | inbox delivery path |
| B3 | Reminders: book an appointment tomorrow with `reminder_hours` set | a reminder one hour/day before | scheduler not running in production (needs PUBLIC_BASE_URL) |
| B4 | Announcement from the «اطلاعیه» tab; then `/stop` from the customer | customer receives it; after `/stop` no more | audience/opt-out logic |
| B5 | Payment: in «انتشار» save the TEST wallet token `WALLET-TEST-1111111111111111`, order from a bot with `payment: online`, pay the invoice | invoice appears, after paying the owner is notified | Bale invoice API (sendInvoice / pre_checkout / successful_payment) |
| B6 | Photo/file: ask the agent for «دکمه دریافت کاتالوگ که فایل PDF بفرسته», upload a PDF in «فایل‌ها», tap the button | the PDF arrives in the chat | multipart `sendDocument` format Bale expects |
| B7 | Map pin: a message with coordinates | a map pin arrives | `sendLocation` |
| B8 | Quiz, sub-menu, random message | as designed | (engine only, low risk) |

## C. Channel and group features (HIGH risk: Bale's docs do not promise that bots receive these updates)
Prerequisite: create a test Bale channel and a test Bale group, add the bot to both and make it ADMIN (give it «delete messages» and «ban users» in the group).
| # | Do | Expected | If it fails |
|---|---|---|---|
| C1 | Panel tab «کانال و گروه» → «دریافت کد اتصال» → post `/link CODE` in the channel | the bot answers «✅ …وصل شد» in the channel and the `/link` post disappears; the channel shows up in the panel | **Bale does not deliver channel posts to bots** (then channel linking, post forwarding and anything channel-side cannot work on Bale; Telegram would still work) |
| C2 | Post `/link CODE` (new code) as a group admin in the group | group linked, appears in the panel | **Bale does not deliver group messages to bots** (moderation cannot work on Bale) |
| C3 | Link two channels, add a forward rule A → B, post in A | the post is copied to B | `copyMessage` between channels, or bot not admin in B |
| C4 | In the group, as a normal member send a message with a link | the bot deletes it | bot lacks the delete right, or message older than 48 h |
| C5 | Same member sends 3 link messages | after the third, the member is removed from the group | `banChatMember` right missing (mute is NOT possible on Bale) |
| C6 | As group admin reply to a message with `/warns`, `/ban`, `/unban` | answers / bans / unbans | admin detection via `getChatMember` |
| C7 | Add a new member | welcome text if configured | `new_chat_members` not delivered |

## D. Forced channel join
| # | Do | Expected | If it fails |
|---|---|---|---|
| D1 | Ask the agent: «…مشتری‌ها باید اول عضو کانال @yourchannel بشن» (use your real test channel), publish, make the bot ADMIN of the channel; open «کانال و گروه» and press «بررسی دوباره» | green ✓ «ربات ادمین کانال است» | `getChatMember` for a channel not allowed; wrong @username |
| D2 | A second Bale account that is NOT in the channel opens the bot | gate message with «عضویت در کانال» and «✅ عضو شدم»; nothing else works | check message and URL button rendering |
| D3 | That account joins and presses «✅ عضو شدم» | the bot continues to the welcome/menu | membership status names differ on Bale |
| D4 | Remove the bot from channel admins and try again | customers are let in (fail open) and you get one warning message | |

## E. Invite links
| # | Do | Expected | If it fails |
|---|---|---|---|
| E1 | Ask for an invite-friends bot; as customer A open «دعوت دوستان» | a personal link `https://ble.ir/<bot>?start=r…` | username missing |
| E2 | A second NEW account opens that link | lands in the business's bot; A receives «🎉 یک نفر با لینک اختصاصی شما وارد شد» | **Bale does not pass the `start` value** after the link (the shared-bot business links use the same mechanism, so this is likely fine) |
| E3 | The same account opens the link again, or A opens their own link | no second count | |

## F. Anonymous chat (needs two accounts)
| # | Do | Expected | If it fails |
|---|---|---|---|
| F1 | Both accounts open the anonymous-chat button and tap «پیدا کردن شریک» | both get «شریک گفتگو پیدا شد» | pairing |
| F2 | Send text both ways; send a link or phone number | text arrives as «👤 …»; link/number is refused | |
| F3 | «🚫 گزارش تخلف» | a «reported» record with the last messages appears in «ثبت‌ها»; ban button works | |
| F4 | Ban the reported customer in «مشتریان» | that account sees «دسترسی شما مسدود شده است» | |

## G. Plans
Open `/pricing/` and `/account/`; try creating a 4th bot on the free plan (expect a clear message); press «پرداخت آزمایشی و فعال‌سازی» (a simulated payment: the plan activates at once), check the limits change and the payment history row, then cancel back to free.

## H. Telegram (through the relay)
1. Open the relay's address in a browser: it must show `ok`.
2. After a deploy with `TELEGRAM_SHARED_BOT_TOKEN` set, open the shared Telegram bot: it must show the directory of businesses (`/start`), and a business link `t.me/<bot>?start=CODE` must open that bot.
3. Repeat B1–B2, B4 and E on Telegram. Expected differences: no payment button, files are replaced by a short note, everything else the same.
4. For C on Telegram the bot must be admin; channel posts are delivered because the webhook asks for `channel_post` updates.

## I. Outage drill (optional, 5 minutes)
1. Publish a bot, send a message to it from a customer account, confirm the reply.
2. Break the connection on purpose (for example set a wrong `TELEGRAM_RELAY_URL` and redeploy, or block the server's access to the messenger).
3. Send messages to the bot: the panel should show an amber banner (messenger down, messages waiting) after three failed calls.
4. Restore the connection: within a few minutes the waiting messages should arrive in order and the banner should disappear.
