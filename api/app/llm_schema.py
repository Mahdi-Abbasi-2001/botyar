"""LLM-facing variant of BotSpec: identical shape, but a plain Union (anyOf) instead of a
discriminated union (oneOf), because OpenAI strict structured outputs reject oneOf.
Results are always re-validated against the real BotSpec."""
from typing import Union

from pydantic import BaseModel, Field

from .spec import (JoinGate, AdminNotifyBlock, BookingBlock, CatalogOrderBlock, ContactBlock, FaqBlock, FeedbackBlock, FormBlock, MenuBlock, MenuItem, QuizBlock, ReferralBlock, AnonChatBlock,
                   MessageBlock, ProductIn)


class LLMBotSpec(BaseModel):
    name: str
    welcome: str
    menu: list[MenuItem]
    blocks: list[Union[MessageBlock, FormBlock, BookingBlock, CatalogOrderBlock, FaqBlock, ContactBlock, FeedbackBlock, MenuBlock, QuizBlock, ReferralBlock, AnonChatBlock, AdminNotifyBlock]]
    gate: JoinGate | None  # forced channel join, or null
    sample_products: list[ProductIn]  # only for catalog_order with source="table"; otherwise []
