# Botyar — Final test sheet

One pass over every kind of bot the agent builds. For each type: **owner prompt** (paste into «گفت‌وگوی ساخت»), **customer steps** (in the phone preview first, then once on real Bale), and **edge cases** (the ones most likely to break).

How to run it: make one new bot per section, answer the agent's questions with the shortest reasonable answer, wait for «همه‌ی تست‌ها موفق بودند», then walk through the customer steps in the phone preview («امتحان بات»). Tick the real-Bale column only for the ones marked ★.

General rules to check in **every** bot:
- «بازگشت به منو» exists on every screen that offers choices (not on yes/no questions).
- Typing «منو» or «/start» at any step returns to the main menu.
- Typing «انصراف» cancels the current step and shows the menu.
- Buttons read naturally (1–3 words, no «و» joining two ideas).
- After a finished action the menu appears again.
- Pressing a button **replaces its own message** (no pile of old menus): menu → screen → «بازگشت به منو» all happen in one message. Finished actions (booking confirmed, order placed, cancelled, thanks) arrive as new messages followed by the menu. Typed answers always get a new message.
- Persian digits, Arabic digits and English digits are all accepted in numbers and phone numbers.

---

## 1. Information bot (message + menu + links + hours)
**Prompt:** «برای کافه‌ام یک ربات اطلاع‌رسانی بساز: آدرس (خیابان ولیعصر، پلاک ۱۲)، ساعت کاری (هر روز ۸ تا ۲۲)، لینک اینستاگرام (instagram.com/cafe) و شماره تماس ۰۲۱۱۲۳۴۵۶۷۸.»
**Customer:** open each menu button; tap the Instagram link button.
**Expect:** every button answers; the link button opens the link; no «ثبت‌های من» button (nothing to cancel).
**Edge:** write a very long description (2000 characters) → the bot still answers or the agent shortens it; ask for a location pin («موقعیت روی نقشه») and a photo → both are sent.

## 2. Form / lead bot (form)
**Prompt:** «ربات ثبت‌نام مشتری بساز که نام، شماره موبایل، شهر (تهران، شیراز، مشهد) و توضیحات را بگیرد و به من اطلاع بدهد.»
**Customer:** fill every field, finish.
**Expect:** owner gets a notification in the owner's chat; record appears in «مدیریت».
**Edge:** phone «۰۹۱۲» (too short) → asks again; phone in Persian digits «۰۹۱۲۳۴۵۶۷۸۹» → accepted; type free text where the city buttons are → asked to choose; send only spaces as the name → asked again; go back with «منو» halfway, start again → no half-saved record; two customers fill at the same time → two records.

## 3. Fixed-time booking (classes, workshops: booking with slots) ★
**Prompt:** «برای باشگاه یوگا ربات ثبت‌نام بساز. کلاس شنبه ساعت ۱۸ و دوشنبه ساعت ۱۹، هر کدام ظرفیت ۸ نفر. لیست انتظار داشته باشد و مشتری بتواند لغو کند.»
**Customer:** register for Saturday; check «ثبت‌نام‌های من» (or «نوبت‌های من» if you call it نوبت); cancel; register again.
**Expect:** capacity counts per date; remaining places shown; after cancelling the place is free.
**Edge:** fill all 8 places with 8 different customers (use several accounts or the test records) → 9th gets the waitlist; cancel one confirmed → first waiting customer is promoted and told; same customer books the same class twice → refused or asked; cancel after the deadline → refused with a clear reason; reschedule («🔄 تغییر زمان») → old place freed only after the new one is confirmed.

## 4. Appointment calendar (dentist, salon: booking with schedule) ★
**Prompt:** «برای کلینیک دندانپزشکی ربات نوبت‌دهی بساز. شنبه تا چهارشنبه ۹ تا ۱۳ و ۱۶ تا ۲۰، هر نوبت ۳۰ دقیقه، ناهار ۱۳ تا ۱۶ تعطیل. دو پزشک: دکتر احمدی و دکتر رضایی. خدمات: ویزیت ۳۰ دقیقه، جراحی ۶۰ دقیقه. یادآوری یک روز قبل.»
**Customer:** pick service → doctor → day → time → name → phone → confirm.
**Expect:** only free times shown; booking appears for the right doctor; the owner and that doctor are notified; reminder appears in «مدیریت»/scheduled.
**Edge:** book the 60-minute service and check the next 30-minute time is no longer offered (overlap); book the last time of the day; day with no free time is hidden; «بازگشت به انتخاب روز» works; a time that was taken while the customer was typing → asked again with a fresh list; owner marks time off («مرخصی») → those times disappear; cancel and rebook; «تغییر زمان» keeps the doctor.

## 5. Shop with a fixed product list (catalog_order, inline items)
**Prompt:** «برای کافه ربات سفارش بساز: اسپرسو ۷۰ هزار تومان، لاته ۹۵ هزار (شیر معمولی یا بادام)، کیک شکلاتی ۱۱۰ هزار. هزینه‌ی ارسال ۲۰ هزار تومان، پرداخت در محل. به من اطلاع بده.»
**Customer:** add 2 espressos + 1 latte (almond) + 1 cake, view cart, remove one, checkout with name/phone/address.
**Expect:** cart total is right, delivery fee added, order shows in «مدیریت» with status; the customer is messaged when the owner marks «در حال آماده‌سازی» and «آماده».
**Edge:** empty cart then checkout → refused; quantity 0 / negative / «abc» → asked again; quantity 999 → limited or refused; cancel an order after the cancellation window → refused; cancel inside it → cancelled and stock returns; change cart then «انصراف» → cart cleared.

## 6. Shop with a product table (clothing store: catalog, photos) ★
**Prompt:** «برای فروشگاه لباس ربات سفارش بساز. محصولات را بعداً وارد می‌کنم. پرداخت کارت‌به‌کارت، تحویل با پیک و پست، کد تخفیف.»
Then in «محصولات»: add 3 products one by one (the new form), import a pasted table, add a photo to one.
**Customer:** browse categories → product → options/size → quantity → cart → code → checkout.
**Expect:** photo is sent with the product; stock decreases; with card-to-card the customer is shown the card number and asked for a receipt.
**Edge:** product with stock 1 → second customer gets «موجود نیست»; stock 0 → offered «خبرم کن»; search for a product («🔍») with and without results; category list when there is only one category (no pointless step); import a table with a wrong column / empty rows / Persian prices («۱,۲۵۰,۰۰۰») → preview shows warnings, nothing saved until confirmed; publishing with only sample products → blocked with the warning (tick «فقط برای آزمایش» to bypass); long product names wrap in the table.

## 7. Discount codes and delivery zones (inside type 5/6)
**Prompt (change request):** «کد تخفیف YALDA با ۱۰٪ تخفیف برای خریدهای بالای ۲۰۰ هزار تومان و حداکثر ۵ بار استفاده اضافه کن. ارسال به تهران ۱۰۰ هزار و به شهرستان ۲۰۰ هزار، تحویل حضوری رایگان.»
**Customer:** menu shows «کدهای تخفیف»; at checkout the code appears as a button.
**Expect:** discount applied only above the minimum; zone fee added.
**Edge:** wrong code, expired/used-up code, lowercase `yalda`, Persian digits in a code, private code (visible off) is not listed but works when typed; one customer uses the same code twice.

## 8. Online payment (Bale wallet) ★ (real Bale only)
Publish with **your own bot**, add the wallet token in «پرداخت آنلاین».
**Expect:** invoice appears; paying marks the order paid; unpaid orders expire after the time set for the shop and stock returns.
**Edge:** shared bot → only the test token works (no money moves); cancel a paid order → told to contact the owner; pay twice (press the invoice again) → one payment only.

## 9. FAQ bot
**Prompt:** «ربات پاسخ به سؤال‌های متداول برای آموزشگاه زبان بساز با ۱۰ سؤال: شهریه، ساعت کلاس، آدرس، ثبت‌نام، تخفیف، آزمون تعیین سطح، کلاس آنلاین، مدرک، لغو ثبت‌نام، تماس.»
**Customer:** open the list; ask in your own words («چقدر باید پول بدم؟», «کی کلاس دارید؟»), with typos, and with an off-topic question.
**Expect:** the right owner answer; unknown question → polite «پاسخ پیدا نشد» + a way to reach the owner; never an invented answer.
**Edge:** very short query («قیمت»), English query, two topics in one sentence, empty message, pagination when more than 8 questions, topics/categories list and back.

## 10. Contact / feedback / rating
**Prompt:** «بعد از هر ثبت‌نام نظر مشتری را با امتیاز ۱ تا ۵ بگیر و اگر امتیاز کمتر از ۳ بود شماره‌اش را بگیر تا تماس بگیریم. یک بخش «پیام به مدیر» با موضوع‌های فروش و شکایت هم داشته باشد.»
**Customer:** rate 5 (ends), rate 2 (asks for a phone), send a message to the owner with a topic.
**Expect:** low score notifies the owner with the phone; message arrives in the owner's chat and «صندوق»; the owner can reply from the panel and the customer receives it.
**Edge:** skip button after a low score; 6 ratings in a day → limit message; empty/very long message; the owner replies after the customer left the conversation.

## 11. Quiz
**Prompt:** «یک آزمون ۴ سؤالی چهارگزینه‌ای از اطلاعات عمومی بساز، نمره‌ی قبولی ۶۰٪، پاسخ درست بعد از هر سؤال نشان داده شود.»
**Expect:** score at the end, pass/fail text; one attempt option works when requested.
**Edge:** answer by typing instead of pressing; leave halfway and return with «منو» then restart → a clean restart; shuffle on → each question once.

## 11b. Question bank for quizzes («سؤال‌ها» tab)
**Prompt:** «یک آزمون ۳۰ سؤالی از تاریخ ایران بساز، هر بار ۱۰ سؤال تصادفی نشان بده، نمره‌ی قبولی ۷۰٪.» → the bot is built with a few sample questions and the agent says the rest is added from «سؤال‌ها».
**In the tab:** add one question by hand (the circle marks the right option); paste a table with columns «سؤال / گزینه ۱..۴ / پاسخ» (answer as 1-4 or الف/ب/ج/د) → preview, then save; paste plain text and upload a photo or PDF of questions → read by the model, check every answer; «ساخت سؤال از روی موضوع» with 10 questions → review, drop the wrong ones with ✕, save; edit and delete saved questions; «بازگشت به سؤال‌های داخل ربات».
**Customer:** take the quiz in the phone preview: 10 random questions each time, different on the next attempt; result and pass/fail text; the same question never appears twice in one attempt.
**Edge:** a table row with a missing answer or only one option (reported and skipped); the same question imported twice (reported as duplicate); a pass mark with fewer questions in the bank than `pick`; delete a question while a customer is mid-quiz (the customer is reset politely); another owner's bot (404); more than 500 questions (refused); the daily import cap.

## 12. Referral / invite (growth)
**Prompt:** «برنامه‌ی دعوت دوستان بساز: هر کس ۳ نفر را دعوت کند یک قهوه‌ی رایگان بگیرد.»
**Customer:** get the personal link; open it from a second account.
**Expect:** counter increases for the inviter; reward message at the goal.
**Edge:** use your own link (no credit), the same friend twice (counted once), a bad code.

## 13. Sub-menus and several features in one bot
**Prompt:** «ربات یک فروشگاه با منوی «خرید»، «پشتیبانی» (شامل سؤال‌های متداول و پیام به مدیر) و «درباره‌ی ما»، بساز.»
**Expect:** sub-menu shows its items and «‹ بازگشت»; nested levels return one level at a time; «بازگشت به منو» returns to the top.

## 14. Anonymous chat ★ (Bale/Telegram only)
**Prompt:** «چت ناشناس بین مشتری‌ها بساز.»
**Edge:** one person alone in the queue (waits, can cancel), two people matched, links/phone numbers blocked by the filter, more than 20 messages a minute, report → conversation ends and the owner gets the last messages, banned customer cannot re-enter.

## 15b. Content behind a channel join ★ (real Bale/Telegram only)
**Prompt:** «ربات جوین اجباری بساز: مشتری با لینک بیاید، برای گرفتن فایل آموزش PDF باید در کانال‌های @channel_one و @channel_two عضو شود و بعد فایل و لینک دانلود را بگیرد.»
Then upload the PDF in «فایل‌ها», make the bot **admin of both channels**, publish, and copy the per-content link from «انتشار».
**Customer:** open the content link → locked message with one button per channel and «✅ عضو شدم، بررسی کن» → press it before joining → still-missing list → join one → press → only the other is listed → join both → press → file + link arrive, then the menu.
**Edge:** open the link from a second account that is already in both channels (content at once); bot not admin of a channel (customer is let through: fix by making the bot admin); a channel name typo (let through); another content block stays free; typing text while locked repeats the lock message; Telegram uses `t.me/<channel>` buttons; the shared bot's link has the form `?start=CODE-<block id>`, an own bot's `?start=go-<block id>`.
Unconfirmed on real Bale: what `getChatMember` returns for someone who is NOT a member (a «left» status, or an error). If it is an error, the customer would be let through: tell me.

## 15. Channel / group tools ★ (real Bale only)
Forced join (customers must join a channel first), post forwarding, group moderation. See `docs/real-bale-checklist.md` section C first: this only works if Bale delivers channel/group messages to bots.
**Edge:** bot not an admin of the channel → clear message; the join check fails because of an outage → fails open (customer is let in).

---

## Agent behaviour (the builder itself)
1. **Vague request:** «یک ربات برای کسب‌وکارم بساز» → the agent asks what the business is; it does not build blind.
2. **Suggestions:** for each bot type above the agent suggests only related features (a café: delivery and discount, not quizzes) and never re-asks what you already said.
3. **Unsupported:** «ربات با پرداخت بیت‌کوین بساز» → says clearly what it cannot do and builds the rest; no mention of unrelated unsupported features.
4. **Change request:** «ظرفیت کلاس شنبه را ۱۲ کن» → a diff in plain Persian, regression tests run, a new version appears; old version can be opened.
5. **Failing test:** ask for something that makes a test fail → the agent repairs it and says so; if it cannot, the bot is not publishable.
6. **Button names:** no «ثبت‌های من» as a menu item written by the agent (the engine adds the right one), no names longer than 3–4 words.
7. **Persian copy:** «شما», standard written Persian, no slogans.

## Publishing and operations
- Publish with the **shared bot** (trial): open the link, `/start`, use the bot; stop publishing → the bot stops answering; republish.
- «تبدیل به ربات اختصاصی»: switch with your own token; old records and customers remain; the old link no longer works.
- Publish to **Telegram** (only if the relay is up).
- Send an announcement to customers; schedule one for 2 minutes later.
- Change a bot while a customer is mid-flow → the customer is reset politely, no crash.
- Plans: free plan blocks the 4th bot and 2nd live bot with a clear upgrade message; «ارتقا» (demo payment) activates a plan.
- Outages can't be staged by hand; check only that the delivery warning banner shows in the panel when a send has failed (use the real-Bale checklist, section on outages).

## Security quick pass
- Open `/bot/?id=<another user's bot id>` → refused.
- Open `/api/bots/1` without login → 401.
- A customer typing `<script>`, SQL text or 5000 characters in any field → bot keeps working, text is shown as plain text in the panel.

## Visual / usability pass (one screenshot per item)
Landing page (desktop + phone width), login, bots list, builder, tests tab, products tab (long names), publish tab (Bale and Telegram cards), manage tab, pricing, account. Look for overlapping text, cut-off text, and buttons that go off the page.
