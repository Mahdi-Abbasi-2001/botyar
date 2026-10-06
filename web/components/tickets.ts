/** Support tickets (api/app/support.py), shared by the «پشتیبانی» page and the builder's decline card. */
export type TicketKind = "unsupported" | "problem" | "question" | "idea";
export type Ticket = {
  id: number; kind: TicketKind; text: string; context: string; status: "open" | "answered" | "closed"; reply: string;
  bot_id: number | null; bot_name: string | null; created_at: string; replied_at: string | null; new_reply: boolean; username?: string;
};

export const KIND_LABEL: Record<TicketKind, string> = {
  unsupported: "ربات یا امکانی که هنوز نیست",
  problem: "چیزی درست کار نمی‌کند",
  question: "سؤال دارم",
  idea: "پیشنهاد",
};

export const STATUS_LABEL: Record<Ticket["status"], [string, string]> = {
  open: ["در انتظار پاسخ", "border border-amber-line text-amber-fg"],
  answered: ["پاسخ داده شد", "bg-mint-bg text-mint-fg"],
  closed: ["بسته شد", "border border-line-3 text-mute"],
};
