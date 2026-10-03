"""Single entry point for every LLM call: Luna only (cost decision), always logged with cost."""
import time

from openai import OpenAI
from sqlalchemy.orm import Session

from .config import settings
from .models import LlmCall

MODEL = "gpt-6-luna"  # the ONLY model this app uses (owner decision: Sol/others are too expensive)
PRICE_IN, PRICE_CACHED, PRICE_OUT = 0.10 / 1e6, 0.01 / 1e6, 0.50 / 1e6  # USD per token, verified 2026-10-03

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key or None, base_url=settings.openai_base_url, timeout=90, max_retries=2)
    return _client


def cost_of(input_tokens: int, cached: int, output_tokens: int) -> float:
    return (input_tokens - cached) * PRICE_IN + cached * PRICE_CACHED + output_tokens * PRICE_OUT


def call(db: Session, *, bot_id: int, run_id: int, step: str, instructions: str, input: str, schema, effort: str = "low", max_out: int = 8000):
    t = time.time()
    r = client().responses.parse(model=MODEL, instructions=instructions, input=input, text_format=schema,
                                 reasoning={"effort": effort}, max_output_tokens=max_out)
    u = r.usage
    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
    db.add(LlmCall(bot_id=bot_id, run_id=run_id, step=step, model=MODEL, input_tokens=u.input_tokens, cached_tokens=cached,
                   output_tokens=u.output_tokens, cost_usd=cost_of(u.input_tokens, cached, u.output_tokens), seconds=time.time() - t))
    db.commit()
    if r.output_parsed is None:
        raise RuntimeError(f"{step}: model returned no parsable output (status={r.status})")
    return r.output_parsed
