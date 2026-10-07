from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # lower-case; accounts made before usernames keep their old email here
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Bot(Base):
    __tablename__ = "bots"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BotVersion(Base):
    __tablename__ = "bot_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    spec: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Record(Base):
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    collection: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    sandbox: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    state: Mapped[dict] = mapped_column(JSON)


class BuilderMessage(Base):
    __tablename__ = "builder_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BuilderRun(Base):
    __tablename__ = "builder_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="running")  # running | needs_input | done | failed
    events: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LlmCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(Integer, index=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    step: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    seconds: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VersionTests(Base):
    __tablename__ = "version_tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    scenarios: Mapped[list] = mapped_column(JSON)
    results: Mapped[list] = mapped_column(JSON)


class Publication(Base):
    """A bot published to Bale: either via the shared Botyar bot (code) or the owner's own bot token."""
    __tablename__ = "publications"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(8))  # shared | own
    version: Mapped[int] = mapped_column(Integer)  # the published (live) version
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)  # customers send this to the shared bot
    admin_code: Mapped[str] = mapped_column(String(16), unique=True)  # owner sends "/admin <code>" to get notifications
    token_enc: Mapped[str] = mapped_column(Text, default="")  # own mode only, encrypted
    hook_secret: Mapped[str] = mapped_column(String(64), default="")
    bot_username: Mapped[str] = mapped_column(String(64), default="")
    admin_chat_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChatLink(Base):
    """Which published bot a Bale chat is talking to on the shared bot."""
    __tablename__ = "chat_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    pub_id: Mapped[int] = mapped_column(ForeignKey("publications.id"), index=True)


class BotListing(Base):
    """Owner's choice to keep a bot OUT of the shared bots' directory (no row = listed). Separate table: no migrations."""
    __tablename__ = "bot_listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), unique=True, index=True)
    hidden: Mapped[bool] = mapped_column(default=False)


class TgPublication(Base):
    """The same bot published to Telegram (separate table: a bot can be live on Bale and Telegram at once, and the
    app has no migrations, so the Bale tables are never altered). Fields mean the same as in Publication."""
    __tablename__ = "tg_publications"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(8))  # shared | own
    version: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    admin_code: Mapped[str] = mapped_column(String(16), unique=True)
    token_enc: Mapped[str] = mapped_column(Text, default="")
    hook_secret: Mapped[str] = mapped_column(String(64), default="")
    bot_username: Mapped[str] = mapped_column(String(64), default="")
    admin_chat_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TgChatLink(Base):
    """Which published bot a Telegram chat is talking to on the shared Telegram bot."""
    __tablename__ = "tg_chat_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    pub_id: Mapped[int] = mapped_column(ForeignKey("tg_publications.id"), index=True)


class Product(Base):
    """One row of a store's catalog (a catalog_order block with source='table')."""
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    block_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(120), default="")
    price: Mapped[int] = mapped_column(Integer, default=0)  # toman
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    options: Mapped[list] = mapped_column(JSON, default=list)  # [{"name","choices":[...]}]
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)  # agent-made demo rows, replaced on first import
    has_photo: Mapped[bool] = mapped_column(Boolean, default=False)  # the photo itself is a BotFile with block_id "product:<id>"


class QuizQuestionRow(Base):
    """One question of a quiz's imported bank (the owner's «سؤال‌ها» tab). While a quiz has rows here, they replace the spec's own questions."""
    __tablename__ = "quiz_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    block_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(String(300))
    options: Mapped[list] = mapped_column(JSON, default=list)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)


class VersionFixture(Base):
    """Frozen product list the version's tests run against (tests stay hermetic when the live catalog changes)."""
    __tablename__ = "version_fixtures"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    catalog: Mapped[list] = mapped_column(JSON)


class FaqIndex(Base):
    """One searchable phrasing of one FAQ entry: the question itself plus LLM-written informal variants, with its embedding."""
    __tablename__ = "faq_index"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    block_id: Mapped[str] = mapped_column(String(64), index=True)
    entry_hash: Mapped[str] = mapped_column(String(40), index=True)  # sha1(question + answer): an edited entry gets re-indexed
    doc: Mapped[str] = mapped_column(Text)
    vector: Mapped[bytes] = mapped_column(LargeBinary)  # float16, L2-normalised
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Broadcast(Base):
    """An announcement the owner sent to every customer who has talked to the bot."""
    __tablename__ = "broadcasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    audience: Mapped[int] = mapped_column(Integer, default=0)
    segment_label: Mapped[str] = mapped_column(String(200), default="")  # who it went to, when not everyone
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PaymentConfig(Base):
    """The owner's Bale wallet token for taking payments in their bot (encrypted). Money goes to the wallet behind this token, never to Botyar."""
    __tablename__ = "payment_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), unique=True, index=True)
    token_enc: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Subscription(Base):
    """Which plan an account is on (no row = free). Activated by an admin after the owner's upgrade request."""
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(16), default="free")
    note: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class UpgradeRequest(Base):
    __tablename__ = "upgrade_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TimeOff(Base):
    """Hours the owner closed on one date (afternoon off, a staff member's leave): no booking can fall inside them."""
    __tablename__ = "time_off"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    block_id: Mapped[str] = mapped_column(String(64))
    date: Mapped[str] = mapped_column(String(10))   # ISO (Gregorian)
    start: Mapped[str] = mapped_column(String(5))   # "HH:MM"
    end: Mapped[str] = mapped_column(String(5))
    staff: Mapped[str] = mapped_column(String(40), default="")  # "" = everyone
    note: Mapped[str] = mapped_column(String(100), default="")


class SavedReply(Base):
    """A reply the owner reuses in the inbox («سفارش شما فردا ارسال می‌شود»)."""
    __tablename__ = "saved_replies"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    text: Mapped[str] = mapped_column(Text)


class StaffLink(Base):
    """A staff member of an appointment calendar who links their own chat («/staff CODE») to hear about their bookings."""
    __tablename__ = "staff_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    name: Mapped[str] = mapped_column(String(40))  # as written in schedule.staff
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    messenger: Mapped[str] = mapped_column(String(8), default="")  # bale | tg, once linked
    chat_id: Mapped[str] = mapped_column(String(32), default="")


class OwnerDigest(Base):
    """The owner's morning summary of a bot (sent at 8:00 Tehran to their linked chat): on by default."""
    __tablename__ = "owner_digests"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sent: Mapped[str] = mapped_column(String(10), default="")  # ISO date of the last summary (one per day)


class SupportTicket(Base):
    """An owner's message to the Botyar team: a bot type the agent can't build yet, a problem, a question or an idea."""
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bots.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # unsupported | problem | question | idea
    text: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text, default="")  # e.g. the agent's explanation when it declined the request
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | answered | closed
    reply: Mapped[str] = mapped_column(Text, default="")
    user_seen: Mapped[bool] = mapped_column(Boolean, default=True)  # false once the team replies, until the owner opens «پشتیبانی»
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerSeen(Base):
    """Everyone who has written to a live bot (Bale chats): feeds the customers tab and the plan's monthly customer cap."""
    __tablename__ = "customers_seen"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)  # "bale:<chat id>"
    name: Mapped[str] = mapped_column(String(80), default="")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    messages: Mapped[int] = mapped_column(Integer, default=0)


class BotFile(Base):
    """A photo or document the owner attached to a message block; sent to customers as a file."""
    __tablename__ = "bot_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    block_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(10))  # image | document
    filename: Mapped[str] = mapped_column(String(120))
    mime: Mapped[str] = mapped_column(String(80), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ScheduledBroadcast(Base):
    """An announcement to send later (once) or every day at a fixed Tehran time."""
    __tablename__ = "scheduled_broadcasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(8))  # once | daily
    hhmm: Mapped[str] = mapped_column(String(5), default="")  # Tehran time of day (daily)
    next_run: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # UTC
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReferralCode(Base):
    """A customer's personal invite code (their link is the bot's link plus this code)."""
    __tablename__ = "referral_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))  # referrer customer key, "bale:<id>" / "tg:<id>"
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)


class ReferralJoin(Base):
    """A brand-new customer who arrived through someone's invite link (each customer counts once, for one referrer)."""
    __tablename__ = "referral_joins"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    referrer_key: Mapped[str] = mapped_column(String(64), index=True)
    invited_key: Mapped[str] = mapped_column(String(64))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)  # False until the friend's first order/booking (count_after="order")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LinkToken(Base):
    """A one-time code the owner posts as `/link CODE` in a group or channel to attach that chat to their bot (valid 15 minutes)."""
    __tablename__ = "link_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class ChatBinding(Base):
    """A group or channel (on Bale or Telegram) that belongs to a business's bot."""
    __tablename__ = "chat_bindings"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    ch: Mapped[str] = mapped_column(String(8))  # bale | tg
    chat_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # group | channel
    title: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ForwardRule(Base):
    """Posts published in the source channel are copied to the destination chat."""
    __tablename__ = "forward_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("chat_bindings.id"), index=True)
    dest_id: Mapped[int] = mapped_column(ForeignKey("chat_bindings.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    forwarded: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(200), default="")


class GroupRule(Base):
    __tablename__ = "group_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    binding_id: Mapped[int] = mapped_column(ForeignKey("chat_bindings.id"), unique=True, index=True)
    delete_links: Mapped[bool] = mapped_column(Boolean, default=True)
    delete_forwards: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_words: Mapped[list] = mapped_column(JSON, default=list)
    max_warnings: Mapped[int] = mapped_column(Integer, default=3)  # 0 = only delete, never ban
    welcome_text: Mapped[str] = mapped_column(String(500), default="")
    deleted: Mapped[int] = mapped_column(Integer, default=0)
    banned: Mapped[int] = mapped_column(Integer, default=0)


class GroupWarning(Base):
    __tablename__ = "group_warnings"
    id: Mapped[int] = mapped_column(primary_key=True)
    binding_id: Mapped[int] = mapped_column(ForeignKey("chat_bindings.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(Integer, default=0)


class AnonQueue(Base):
    """Customers waiting for an anonymous chat partner."""
    __tablename__ = "anon_queue"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    block_id: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(64))
    topic: Mapped[str] = mapped_column(String(40), default="")  # the topic room (empty = the block has no rooms)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AnonPair(Base):
    """Two customers chatting anonymously. `log` keeps only the last few messages, so that a report can be reviewed; it is cleared when the chat ends normally."""
    __tablename__ = "anon_pairs"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    block_id: Mapped[str] = mapped_column(String(64))
    a_key: Mapped[str] = mapped_column(String(64), index=True)
    b_key: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    log: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BannedCustomer(Base):
    __tablename__ = "banned_customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PlanPayment(Base):
    """A plan purchase. In the demo app these are SIMULATED (no money moves); the row exists so the account page can show an invoice history."""
    __tablename__ = "plan_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(Integer, default=0)  # Toman
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OutboxMessage(Base):
    """A customer/owner message that could not be sent because the messenger was unreachable; retried for a while, then given up.
    Holds no token: the bot's token is looked up again when the message is retried."""
    __tablename__ = "outbox_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    ch: Mapped[str] = mapped_column(String(8))
    chat_id: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(8), default="pending", index=True)  # pending | sent | failed
    next_try: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
