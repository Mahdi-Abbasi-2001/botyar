"""LLM-facing variant of BotSpec: identical shape, but a plain Union (anyOf) instead of a
discriminated union (oneOf), because OpenAI strict structured outputs reject oneOf.
Results are always re-validated against the real BotSpec."""
from typing import Union

from pydantic import BaseModel, Field

from .spec import (AdminNotifyBlock, BookingBlock, CatalogOrderBlock, FormBlock, MenuItem,
                   MessageBlock)


class LLMBotSpec(BaseModel):
    name: str
    welcome: str
    menu: list[MenuItem]
    blocks: list[Union[MessageBlock, FormBlock, BookingBlock, CatalogOrderBlock, AdminNotifyBlock]]
